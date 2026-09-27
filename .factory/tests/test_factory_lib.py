"""factory_lib 单测 —— 全部锚定 S2 真实链暴露过的缺陷（回归优先）。

缺陷→测试映射:
- 解析崩溃（group(0) 含 ```json 字面量）→ test_parse_fenced_* 系列
- 证据饥饿（-q 无测试名）→ test_evidence_suites_*
- 熔断边界（跨天/重置/上限）→ test_breaker_*
- 静默拒绝（#57/#59/#60 只落标签无评论）→ TestRejectReceipt
"""

import pytest

import factory_lib
from factory_lib import (
    CircuitOpen,
    breaker_check,
    dist_manifest_lines,
    evidence_suites,
    jfield,
    neutralize_marker,
    docstring_gate_cmd,
    main,
    node_metric_line,
    node_timeout,
    parse_agent_json,
    reject_receipt,
)



# ---- S2 issue #2 holdout 的真实输出形态（fence 包裹 + 前导文字）----
REAL_HOLDOUT = """Working...
```json
{"verdict": "PASS",
 "evidence": "TestCheckKebabCase 的 test_leading_hyphen_rejected PASSED 与诉求对应",
 "residual_risk": null}
```
"""

# ---- S2 issue #3 triage 的真实输出形态（裸 JSON，无 fence）----
REAL_TRIAGE = """{"issue": 3, "verdict": "reject", "priority": null,
 "reasons": ["判据c: 不通过——需修改 steering/，在 PERIMETER 中"]}"""


class TestParseAgentJson:
    VERDICTS = {"PASS", "FAIL"}

    def test_parse_fenced_group1_regression(self):
        """回归：围栏形态必须只取组 1。旧 bug 用 group(0)（含 ```json 字面量）
        进 json.loads 必炸——2026-08-21 链死根因。"""
        d = parse_agent_json(REAL_HOLDOUT, self.VERDICTS)
        assert d["verdict"] == "PASS"
        assert "test_leading_hyphen_rejected" in d["evidence"]

    def test_parse_fenced_fail_verdict(self):
        text = '```json\n{"verdict": "FAIL", "evidence": "无法建立对应关系"}\n```'
        assert parse_agent_json(text, self.VERDICTS)["verdict"] == "FAIL"

    def test_parse_bare_json_fallback(self):
        """S2 issue #3 triage 真实形态：无 fence 裸 JSON 兜底路径。"""
        d = parse_agent_json(REAL_TRIAGE, {"accept", "reject"})
        assert d["verdict"] == "reject"
        assert d["issue"] == 3

    def test_parse_with_surrounding_noise(self):
        text = '思考中...\n{"verdict": "FAIL", "evidence": "x"}\n完毕'
        assert parse_agent_json(text, self.VERDICTS)["verdict"] == "FAIL"

    def test_parse_no_json_raises(self):
        with pytest.raises(ValueError, match="未找到 JSON"):
            parse_agent_json("没有任何结构化输出", self.VERDICTS)

    def test_parse_bad_verdict_fail_closed(self):
        """verdict 缺失/非法必须 fail-closed，不许坏裁决流入链。"""
        with pytest.raises(ValueError, match="verdict"):
            parse_agent_json('{"verdict": "MAYBE"}', self.VERDICTS)
        with pytest.raises(ValueError, match="verdict"):
            parse_agent_json('{"no_verdict": true}', self.VERDICTS)

    def test_parse_multiline_nested_braces(self):
        """evidence 含中文引号与嵌套花括号（贪心兜底的边界）。"""
        text = '{"verdict": "PASS", "evidence": "输出「{[1/3] OK}」对应诉求"}'
        d = parse_agent_json(text, self.VERDICTS)
        assert d["verdict"] == "PASS"

    def test_parse_duplicated_json_blobs(self):
        """#207 首次尝试实证崩形：裁决 JSON 被整段重复（Extra data:
        char 429）。旧贪心兜底从首个左花括号拼到末个右花括号再
        json.loads 必炸；逐偏移 raw_decode 取首个完整对象。"""
        blob = '{"verdict": "reject", "reasons": ["判据b: 不通过"]}'
        d = parse_agent_json(blob + blob, {"accept", "reject"})
        assert d["verdict"] == "reject"

    def test_parse_trailing_prose_with_braces(self):
        """裸 JSON 后跟含花括号尾文（fence 丢失形态）——旧贪心兜底
        同样把尾文花括号拼进来；逐偏移扫描在首个合法对象处停。"""
        text = ('{"verdict": "FAIL", "evidence": "x"}\n'
                '附注：详见 {附录A} 与 {附录B}')
        assert parse_agent_json(text, self.VERDICTS)["verdict"] == "FAIL"

    def test_parse_fence_priority_over_earlier_bare(self):
        """fence 内对象优先于正文更早出现的裸对象——fence 是 LLM
        显式结构化输出信号（#207 重写后保序语义锚）。"""
        text = ('{"verdict": "PASS", "evidence": "正文里的裸对象"}\n'
                '```json\n{"verdict": "FAIL", "evidence": "fence 裁决"}\n```')
        assert parse_agent_json(text, self.VERDICTS)["verdict"] == "FAIL"

    def test_parse_nested_verdict_not_accepted(self):
        """PR #211 Sourcery 评论1：外层 verdict 非法时，嵌套对象携带的
        合法 verdict 不具裁决资格——顶层 fail-closed 契约（防坏裁决借
        evidence/元数据嵌套混入链），整对象跳过后 ValueError。"""
        text = '{"verdict": "MAYBE", "evidence": {"verdict": "reject"}}'
        with pytest.raises(ValueError, match="verdict"):
            parse_agent_json(text, {"accept", "reject"})

    def test_parse_disallowed_outer_then_valid_sibling_recovers(self):
        """坏 verdict 顶层对象被整体跳过后继续扫后续顶层——多对象恢复
        不因嵌套封堵回退（重复块恢复的邻接形态）。"""
        text = '{"verdict": "MAYBE"} {"verdict": "reject"}'
        assert parse_agent_json(text, {"accept", "reject"})["verdict"] == "reject"

    def test_parse_all_fences_scanned_before_bare(self):
        """PR #211 CodeRabbit 评论1：fence 优先 = 穷尽全部 fence。首个
        fence 裁决非法时，正文更早出现的合法裸对象不得抢先后位合法
        fence——fence 是更强的结构化输出信号，优先级须穷尽兑现。"""
        text = ('{"verdict": "PASS", "evidence": "正文裸对象"}\n'
                '```json\n{"verdict": "MAYBE"}\n```\n'
                '```json\n{"verdict": "FAIL", "evidence": "后位 fence"}\n```')
        assert parse_agent_json(text, self.VERDICTS)["verdict"] == "FAIL"

    def test_parse_unclosed_outer_nested_verdict_rejected(self):
        """PR #211 CodeRabbit 评论2：外层对象未闭合时，解码失败不得
        落到嵌套 `{` 接受其 verdict——坏对象按字符串感知平衡范围整体
        跳过（未闭合则跳到输入末尾），fail-closed。"""
        text = '{"verdict": "MAYBE", "evidence": {"verdict": "reject"}'
        with pytest.raises(ValueError, match="verdict"):
            parse_agent_json(text, {"accept", "reject"})

    def test_parse_failed_prose_brace_skips_balanced_range(self):
        """解码失败的散文花括号按平衡范围跳过（未闭合吞到末尾的对偶
        边界）：`{附录A}` 平衡闭合后，其后合法顶层对象仍可恢复。"""
        text = '附注 {附录A}\n{"verdict": "FAIL", "evidence": "x"}'
        assert parse_agent_json(text, self.VERDICTS)["verdict"] == "FAIL"


class TestEvidenceSuites:
    def test_skills_change_yields_suite(self):
        """回归：skills 改动必须产出证据套件——否则 holdout 只见 -q 点号，
        证据饥饿永远 FAIL（S2 issue #2 首次裁决死因）。"""
        assert evidence_suites(["skills/api-guard/scripts/api_check.py"]) == [
            "skills/api-guard/scripts"
        ]

    def test_non_skills_change_no_suite(self):
        assert evidence_suites(["README.md", "docs/x.md", "scripts/run.py"]) == []

    def test_dedup_and_sort(self):
        files = [
            "skills/doc-gen/scripts/b.py",
            "skills/api-guard/scripts/a.py",
            "skills/api-guard/tests/x.py",
        ]
        assert evidence_suites(files) == [
            "skills/api-guard/scripts",
            "skills/doc-gen/scripts",
        ]

    def test_empty(self):
        assert evidence_suites([]) == []


class TestBreakerCheck:
    FLOOR = {"max_runs_per_day": 10, "max_consecutive_failures": 3}

    @staticmethod
    def _e(day: str, exit_code: int = 0) -> dict:
        return {"ts": f"{day}T12:00:00Z", "issue": 1, "exit": exit_code, "secs": 60}

    def test_empty_ledger_passes(self):
        breaker_check(self.FLOOR, [], "2026-08-21")

    def test_daily_cap_trips(self):
        entries = [self._e("2026-08-21")] * 10
        with pytest.raises(CircuitOpen, match="今日已跑 10 次"):
            breaker_check(self.FLOOR, entries, "2026-08-21")

    def test_daily_cap_boundary_below(self):
        entries = [self._e("2026-08-21")] * 9
        breaker_check(self.FLOOR, entries, "2026-08-21")  # 9 < 10 放行

    def test_other_day_runs_not_counted(self):
        entries = [self._e("2026-08-20")] * 25
        breaker_check(self.FLOOR, entries, "2026-08-21")  # 跨天清零

    def test_consecutive_failures_trip(self):
        entries = [self._e("2026-08-21", 1)] * 3
        with pytest.raises(CircuitOpen, match="连续失败 3 次"):
            breaker_check(self.FLOOR, entries, "2026-08-21")

    def test_success_resets_streak(self):
        entries = [self._e("2026-08-20", 1), self._e("2026-08-20", 1),
                   self._e("2026-08-20", 0), self._e("2026-08-21", 1)]
        breaker_check(self.FLOOR, entries, "2026-08-21")  # 成功重置后 streak=1

    def test_streak_spans_days(self):
        """streak 是状态不是流量：昨天的失败延续到今天。"""
        entries = [self._e("2026-08-20", 1)] * 2 + [self._e("2026-08-21", 1)]
        with pytest.raises(CircuitOpen, match="连续失败"):
            breaker_check(self.FLOOR, entries, "2026-08-21")



class TestNodeTimeout:
    """分级预算：裁决器秒级节点不再挂 30m 全局预算（fail-fast 省成本）。"""

    def test_adjudicators_get_tight_budget(self):
        from factory_lib import node_timeout
        assert node_timeout("triage") == "5m"
        assert node_timeout("holdout") == "5m"

    def test_implement_gets_full_budget(self):
        from factory_lib import node_timeout
        # 2026-09-04 重校准：ok-run P95 1534s × 1.2 = 1840.8s → 31m
        assert node_timeout("implement") == "31m"

    def test_review_recalibrated_30m(self):
        from factory_lib import node_timeout
        # 2026-09-04：P95 845s×1.2 → 17m；2026-09-10：17m 撞顶（#165 r2/r3 1026/1021s 败）→ 30m
        assert node_timeout("review") == "30m"

    def test_unknown_node_defaults_15m(self):
        from factory_lib import node_timeout
        assert node_timeout("mystery") == "15m"

    def test_prime_plan_raised_20m(self):
        from factory_lib import node_timeout
        # 2026-09-10：prime 900s 撞顶（#165 r6）、plan 901s 压线（r4）→ 各升至 20m
        assert node_timeout("prime") == "20m"
        assert node_timeout("plan") == "20m"

    def test_per_node_env_override_wins(self):
        from factory_lib import node_timeout
        env = {"FACTORY_TIMEOUT_IMPLEMENT": "45m", "FACTORY_TIMEOUT": "9m"}
        assert node_timeout("implement", env) == "45m"

    def test_process_env_used_when_env_omitted(self, monkeypatch):
        from factory_lib import node_timeout
        monkeypatch.setenv("FACTORY_TIMEOUT_REVIEW", "42m")
        assert node_timeout("review") == "42m"

    def test_global_env_fallback(self):
        from factory_lib import node_timeout
        assert node_timeout("plan", {"FACTORY_TIMEOUT": "9m"}) == "9m"

    def test_hyphen_node_env_key(self):
        from factory_lib import node_timeout
        assert node_timeout("pr-review", {"FACTORY_TIMEOUT_PR_REVIEW": "3m"}) == "3m"

class TestClassifyTask:
    """任务类型分类：doc/code 预算分布分开统计的数据基础（S3 耗时分析结论）。"""

    def test_doc_only(self):
        from factory_lib import classify_task
        assert classify_task(["README.md", "docs/x.md", "share-docs/y.mdx"]) == "doc"

    def test_code_with_tests(self):
        from factory_lib import classify_task
        assert classify_task(["a.py", "test_a.py"]) == "code"

    def test_test_only(self):
        from factory_lib import classify_task
        assert classify_task(["test_a.py", "pkg/tests/b.py"]) == "test"

    def test_mixed(self):
        from factory_lib import classify_task
        assert classify_task(["a.py", "README.md"]) == "mixed"

    def test_issue5_round3_shape(self):
        """#5 round3 实际形态：md + code + test 混合 → mixed（真实回归锚点）。"""
        from factory_lib import classify_task
        assert classify_task([
            "share-docs/01-api-guard.md",
            "skills/api-guard/README.md",
            "skills/api-guard/scripts/test_api_check.py",
        ]) == "mixed"

    def test_empty(self):
        from factory_lib import classify_task
        assert classify_task([]) == "empty"
    def test_frontend_test_conventions(self):
        """前端 .test.* / .spec.* / __tests__ 约定识别为 test（etf-radar#69 审查）。"""
        from factory_lib import classify_task
        assert classify_task(["frontend/src/__tests__/tradingPage.test.tsx"]) == "test"
        assert classify_task(["src/components/PositionsList.test.ts"]) == "test"
        assert classify_task(["vitest/foo.spec.js"]) == "test"

    def test_frontend_test_plus_src_is_code(self):
        """测试与源码并存（无 md）→ code，不因 .test. 误判为 test-only。"""
        from factory_lib import classify_task
        assert classify_task(["src/foo.ts", "src/foo.test.ts"]) == "code"

    def test_paths_with_spaces_stay_whole(self):
        """空格路径是完整单元（配 fix-issue.sh NUL 传递，etf-radar#70 审查）。"""
        from factory_lib import classify_task
        assert classify_task(["docs/road map 2026.md", "src/a b/foo.test.ts"]) == "mixed"

# ---- S2 issue #60 triage 的真实 reject 形态（三判据全有前缀，b 不通过）----
REAL_REJECT = {
    "issue": 60, "verdict": "reject", "priority": None,
    "reasons": [
        "判据a: 不通过（存疑），'持续跟踪'是开放式系统级目标，未落到具体组件",
        "判据b: 不通过，无可机械判定的完成标准",
        "判据c: 存疑，无法排除触周界",
    ],
}


class TestRejectReceipt:
    def test_receipt_never_contains_state_marker(self):
        """安全不变量：回执禁止含裸标记——state.py:82 标记评论优先级最高
        且无撤销语义，链自动写入会把重投（补充上下文后重开）永久钉死在
        rejected（毒丸）。标记通道只保留给人类手动覆盖。"""
        assert "[factory:rejected]" not in reject_receipt(REAL_REJECT)

    def test_receipt_renders_all_reasons(self):
        md = reject_receipt(REAL_REJECT)
        for r in REAL_REJECT["reasons"]:
            assert f"- {r}" in md
        assert "## 工厂 triage 裁决：reject" in md
        assert "── 证据边界 ──" in md

    def test_receipt_guidance_for_failed_criteria(self):
        """不通过 / 存疑判据 → 对应重投指引；#60 形态 a/b/c 全命中。"""
        md = reject_receipt(REAL_REJECT)
        assert "判据a（使命一致）" in md
        assert "判据b（可判定）" in md
        assert "人工" in md  # #24：判据 b 指引含 doc-only 载体/人工出路
        # （PR/MR 措辞是 factory-local.json 本地化面——不作硬断言，ADR-008）

    def test_receipt_pass_criteria_get_no_guidance(self):
        """全通过措辞（通过/勉强通过）不触发指引——防噪音。"""
        md = reject_receipt({"verdict": "reject", "reasons": [
            "判据a: 通过——属文档维护", "判据b: 勉强通过（形式上）——标题可判定"]})
        assert "判据a（使命一致）" not in md
        assert "重投指引" in md  # 兜底通用行仍在

    def test_receipt_empty_reasons_fail_open(self):
        """reasons 缺失/为空 → 回执仍可渲染（评论阶段不得让链崩溃）。"""
        md = reject_receipt({"verdict": "reject"})
        assert "未给出判据明细" in md
        assert "[factory:rejected]" not in md

    def test_receipt_unprefixed_reasons_render_verbatim(self):
        """LLM 输出偏离「判据x:」前缀 → 原样渲染，无前缀解析崩溃。"""
        md = reject_receipt({"verdict": "reject", "reasons": ["与本仓库使命无关"]})
        assert "- 与本仓库使命无关" in md

    def test_receipt_nonstring_reasons_no_crash(self):
        """审查修复（PR #66 评论1）：reasons 混入非字符串元素（dict/int）
        → re.match 不抛 TypeError，回执仍渲染；指引只从字符串项提取。"""
        md = reject_receipt({"verdict": "reject", "reasons": [
            {"detail": "嵌套对象"}, 42, "判据b: 不通过——无可判定标准"]})
        assert "判据b（可判定）" in md
        assert "[factory:rejected]" not in md

    def test_receipt_renders_marker_verbatim(self):
        """出口下沉后职责分离：渲染器管内容——reason 内嵌标记（LLM 从
        issue 评论回显）原样进正文，中和统一由评论出口执行
        （issue_comment → sanitize，见 TestNeutralizeMarker）。"""
        md = reject_receipt({"verdict": "reject", "reasons": [
            "判据b: 不通过，评论已写 [factory:rejected] 表示异议"]})
        assert "[factory:rejected]" in md  # 渲染不中和——出口负责

    def test_receipt_nonlist_reasons_fail_open(self):
        """PR #20 评论2：reasons 为标量（int/str）→ 视为空渲染占位行，
        不在 list() 处抛 TypeError（标签已落，回执必须发得出去）。"""
        for scalar in (42, "判据b: 不通过"):
            md = reject_receipt({"verdict": "reject", "reasons": scalar})
            assert "未给出判据明细" in md
            assert "[factory:rejected]" not in md

    def test_receipt_has_correlation_section(self):
        """PR #20 评论3：五段式补齐「关联」段——无因果模块时显式声明，
        不静默缺位（对齐 review-report-standards.md 第 4 段）。"""
        md = reject_receipt(REAL_REJECT)
        assert "── 关联 ──" in md
        assert "── 证据边界 ──" in md  # 段序：关联在前，边界收尾


class TestNeutralizeMarker:
    """评论出口中和（唯一安全点）：fix-issue.sh issue_comment 发送前必经
    factory_lib sanitize——渲染器不各自记得，出口统一管。"""

    def test_neutralize_plain_and_nested(self):
        """去括号破坏子串、语义保留；循环替换防 [[...]] 嵌套构造
        替换一次后重组出标记（PR #20 评论1 security 回归锚点）。"""
        assert neutralize_marker("评论已写 [factory:rejected] 表示异议") == (
            "评论已写 factory:rejected 表示异议")
        assert "[factory:rejected]" not in neutralize_marker(
            "嵌套 [[factory:rejected]] 构造")

    def test_neutralize_idempotent_and_noop(self):
        """幂等（二次中和不变）且无标记时原样返回（出口可无条件调用）。"""
        once = neutralize_marker("x [factory:rejected] y")
        assert neutralize_marker(once) == once
        assert neutralize_marker("普通正文无标记") == "普通正文无标记"

    def test_neutralize_receipt_output_end_to_end(self):
        """端到端：receipt 渲染（含标记原文）→ 出口中和 → 发布正文无标记。"""
        md = reject_receipt({"verdict": "reject", "reasons": [
            "判据b: 不通过，评论已写 [factory:rejected] 表示异议",
            "判据c: 不通过，嵌套 [[factory:rejected]] 构造"]})
        published = neutralize_marker(md)
        assert "[factory:rejected]" not in published
        assert "factory:rejected" in published  # 语义保留


class TestNodeMetricLine:
    """ADR-005 下沉(2026-08-27):jsonl 渲染契约与 report 消费端同模块锁定。"""

    def test_metric_line_fields(self):
        import json
        line = node_metric_line("implement", 100, 160, "ok")
        d = json.loads(line)
        assert d == {"node": "implement", "secs": 60, "status": "ok"}

    def test_metric_line_zero_and_non_ascii(self):
        import json
        assert json.loads(node_metric_line("t", 5, 5, "fail"))["secs"] == 0
        # ensure_ascii=False：中文状态可读落盘
        assert "中文" in node_metric_line("n", 0, 1, "中文状态")


class TestJfield:
    """json_field 收口(2026-08-28):fix-issue.sh 双引号 -c 形态退役后的契约锁。

    三种 shell 调用形态逐一对齐原语义：取键/缺键给默认/缺键无默认 fail-closed。
    """

    def _write(self, tmp_path, d):
        import json
        p = tmp_path / "x.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        return str(p)

    def test_key_present(self, tmp_path, capsys):
        p = self._write(tmp_path, {"title": "修复 X", "verdict": "PASS"})
        assert jfield(p, "title") == 0
        assert capsys.readouterr().out == "修复 X\n"
        assert jfield(p, "verdict") == 0
        assert capsys.readouterr().out == "PASS\n"

    def test_missing_key_with_default(self, tmp_path, capsys):
        p = self._write(tmp_path, {"title": "t"})
        assert jfield(p, "body", "") == 0
        assert capsys.readouterr().out == "\n"  # 原 d.get("body") or "" 语义

    def test_missing_key_no_default_fail_closed(self, tmp_path, capsys):
        p = self._write(tmp_path, {"title": "t"})
        assert jfield(p, "verdict") == 1  # 空串 + 非零：shell 比较自然走向失败分支
        assert capsys.readouterr().out == ""

    def test_null_value_treated_as_missing(self, tmp_path, capsys):
        p = self._write(tmp_path, {"body": None})
        assert jfield(p, "body", "") == 0
        assert capsys.readouterr().out == "\n"

    def test_non_str_value_json_encoded(self, tmp_path, capsys):
        p = self._write(tmp_path, {"n": 3})
        assert jfield(p, "n") == 0
        assert capsys.readouterr().out == "3\n"


class TestDistManifest:
    """上游分发清单展开(2026-08-28 自 sync-from-upstream.sh heredoc 下沉)：
    真跑 git 夹具仓（conftest/gitenv 密闭环境），锚定两条曾靠 heredoc 承载的
    契约——目录项递归展开（R2-M5：跳过=tests/ 漂移永不告警）与无清单空输出。"""

    def _git(self, repo, *args):
        import subprocess
        from gitenv import git_env
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, check=True,
                              env=git_env())

    def _mk_upstream(self, tmp_path, with_manifest):
        """裸上游夹具：DISTRIBUTION.json(full: 文件+tests/ 目录, local: dict)
        → 提交 → sha；with_manifest=False 时清单缺席（版本旧形态）。"""
        import json as _json
        up = tmp_path / ("up" if with_manifest else "up-old")
        (up / ".factory" / "tests").mkdir(parents=True)
        if with_manifest:
            (up / ".factory" / "DISTRIBUTION.json").write_text(
                _json.dumps({"full": ["dispatch.py", "tests/"],
                             "local": {"README.md": "理由"}}), encoding="utf-8")
            (up / ".factory" / "dispatch.py").write_text("x", encoding="utf-8")
        (up / ".factory" / "tests" / "t.py").write_text("y", encoding="utf-8")
        for args in (("init", "-q", "-b", "main"), ("add", "-A"),
                     ("-c", "user.email=t@t", "-c", "user.name=t",
                      "commit", "-qm", "seed")):
            self._git(up, *args)
        return up, self._git(up, "rev-parse", "HEAD").stdout.strip()

    def test_expands_dirs_and_reads_upstream_object_store(self, tmp_path):
        up, sha = self._mk_upstream(tmp_path, with_manifest=True)
        lines = dist_manifest_lines(str(up), sha)
        assert set(lines) == {"full\tdispatch.py", "full\ttests/t.py",
                              "local\tREADME.md"}

    def test_missing_manifest_returns_empty_for_local_fallback(self, tmp_path, capsys):
        up, sha = self._mk_upstream(tmp_path, with_manifest=False)
        assert dist_manifest_lines(str(up), sha) == []
        assert "无 DISTRIBUTION.json" in capsys.readouterr().err

    def test_local_reason_values_not_emitted(self, tmp_path):
        # local 是 {路径: 理由}——清单行只含路径键，理由不进消费循环
        up, sha = self._mk_upstream(tmp_path, with_manifest=True)
        assert all("理由" not in l for l in dist_manifest_lines(str(up), sha))


class TestDocstringGateCmd:
    """docstring_gate_cmd（2026-08-31 新增可选门）：键缺失 → None（不启用）；
    键存在 → 与 final_gate_cmd 同规校验（非空字符串 + 禁引号/反斜杠，
    fail-closed）。锚定：可选门绝不许静默降级为无门，也不许缺失键炸链。"""

    def test_missing_key_returns_none(self, monkeypatch):
        """键缺失 = 合法省略（仓库无 docstring 门），返回 None 而非报错。"""
        monkeypatch.setattr(factory_lib, "_LOCAL_CFG", {"final_gate_cmd": "x"})
        assert factory_lib.docstring_gate_cmd() is None

    def test_valid_command_returns_verbatim(self, monkeypatch):
        monkeypatch.setattr(factory_lib, "_LOCAL_CFG",
                            {"docstring_gate_cmd": "scripts/docstring_gate.py"})
        assert factory_lib.docstring_gate_cmd() == "scripts/docstring_gate.py"

    @pytest.mark.parametrize("bad_val", [123, ["a"], {"k": "v"}, True, ""])
    def test_non_string_or_empty_fails_closed(self, monkeypatch, bad_val):
        """配置存在但损坏（非字符串/空）→ RuntimeError（fail-closed，
        禁止降级为无门）。与 _local_str 同规（PR #71 Sourcery #2）。"""
        monkeypatch.setattr(factory_lib, "_LOCAL_CFG",
                            {"docstring_gate_cmd": bad_val})
        with pytest.raises(RuntimeError, match="docstring_gate_cmd"):
            factory_lib.docstring_gate_cmd()

    @pytest.mark.parametrize("bad_val", ['sh -c "x"', "a\\ b", "a'b",
                                         "a\nb", "a\rb"])
    def test_quote_backslash_newline_fails_closed(self, monkeypatch, bad_val):
        """引号/反斜杠/换行与 final_gate_cmd 同禁（read -r -a 与 shlex 拆词
        一致性 + ADR-010 漂移锁 + ts#19 换行 argv 分歧收口）。"""
        monkeypatch.setattr(factory_lib, "_LOCAL_CFG",
                            {"docstring_gate_cmd": bad_val})
        with pytest.raises(RuntimeError, match="docstring_gate_cmd"):
            factory_lib.docstring_gate_cmd()

    def test_main_subcommand_empty_when_disabled(self, capsys, monkeypatch):
        """docstring-gate 子命令：未配置 → 空输出 + rc=0（链脚本 [ -n ]
        跳过）；绝不出 "None" 字面或非零（链侧会误判为门故障）。"""
        monkeypatch.setattr(factory_lib, "_LOCAL_CFG", {"final_gate_cmd": "x"})
        assert factory_lib.main(["factory_lib.py", "docstring-gate"]) == 0
        assert capsys.readouterr().out == ""

    def test_main_subcommand_prints_command_when_enabled(self, capsys, monkeypatch):
        monkeypatch.setattr(factory_lib, "_LOCAL_CFG",
                            {"docstring_gate_cmd": "scripts/docstring_gate.py"})
        assert factory_lib.main(["factory_lib.py", "docstring-gate"]) == 0
        assert capsys.readouterr().out == "scripts/docstring_gate.py\n"


class TestFinalGateCmdGuards:
    """final_gate_cmd 校验面锚定：TestDocstringGateCmd 声明「与
    final_gate_cmd 同规校验」，同规源头在此锚定——防两门校验面漂移分叉。"""

    @pytest.mark.parametrize("bad_val", ['sh -c "x"', "a\\ b", "a'b",
                                         "a\nb", "a\rb"])
    def test_quote_backslash_newline_fails_closed(self, monkeypatch, bad_val):
        """禁引号/反斜杠/换行（ts#19 审查收口：read -r -a 只取 here-string
        首行，shlex 多行拆词——含换行配置两侧 argv 分歧）。"""
        monkeypatch.setattr(factory_lib, "_LOCAL_CFG",
                            {"final_gate_cmd": bad_val})
        with pytest.raises(RuntimeError, match="final_gate_cmd"):
            factory_lib.final_gate_cmd()


class TestFinalGateSubcommand:
    """final-gate CLI 子命令（ADR-009 唯一取值口）：fix-issue.sh /
    validate-pr.sh read -ra 拆词消费。回归锚定：分发段曾整段丢失该
    子命令（#85 审查发现），链脚本一调即"未知子命令" rc=2 炸链。"""

    def test_main_subcommand_prints_command(self, capsys, monkeypatch):
        monkeypatch.setattr(factory_lib, "_LOCAL_CFG",
                            {"final_gate_cmd": "python3 tools/final_gate.py"})
        assert factory_lib.main(["factory_lib.py", "final-gate"]) == 0
        assert capsys.readouterr().out == "python3 tools/final_gate.py\n"

class TestSuitesNulOutput:
    """suites 子命令 NUL 分隔（PR #116 CodeRabbit）：套件名可含空格
    （skills/doc review/…），换行分隔 + shell for 词拆分（$(…) 去换行
    按 IFS 切）会把空格名拆碎、消费端静默跳过证据段；\0 让
    fix-issue.sh/validate-pr.sh 的 read -d '' 逐条保真取回。"""

    def test_space_in_suite_name_survives(self):
        """带空格目录名产出带空格套件名——NUL 形态的成因锚点：若实现
        按空白/换行切分即碎名（静默丢证据段）。"""
        assert evidence_suites(["skills/doc review/scripts/g.py"]) == [
            "skills/doc review/scripts"
        ]

    def test_single_suite_nul_terminated_no_newline(self, capsys):
        """单套件：输出恰一个 NUL 结尾条目、零换行——词拆分形态在此
        碎名/多词，read -d '' 收敛单条。"""
        assert factory_lib.main(["factory_lib.py", "suites",
                                 "skills/api-guard/scripts/api_check.py"]) == 0
        assert capsys.readouterr().out == "skills/api-guard/scripts\0"

    def test_multi_suite_roundtrip_read_d(self, capsys):
        """多条目 + 空格名：复刻消费端 read -d '' 解析逐条保真（回归
        fix-issue.sh/validate-pr.sh 消费协议，PR #116 B）。"""
        files = ["skills/api-guard/scripts/a.py",
                 "skills/doc review/scripts/g.py"]
        assert factory_lib.main(["factory_lib.py", "suites", *files]) == 0
        raw = capsys.readouterr().out
        assert raw.endswith("\0")
        assert raw[:-1].split("\0") == [
            "skills/api-guard/scripts", "skills/doc review/scripts"]
