"""factory_lib 单测 —— 全部锚定 S2 真实链暴露过的缺陷（回归优先）。

缺陷→测试映射:
- 解析崩溃（group(0) 含 ```json 字面量）→ test_parse_fenced_* 系列
- 证据饥饿（-q 无测试名）→ test_evidence_suites_*
- 熔断边界（跨天/重置/上限）→ test_breaker_*
- 静默拒绝（#57/#59/#60 只落标签无评论）→ TestRejectReceipt
"""

import pytest

from factory_lib import (
    CircuitOpen,
    breaker_check,
    evidence_suites,
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


class TestEvidenceSuites:
    def test_backend_frontend_change_yield_suites(self):
        """回归：backend/frontend 改动必须产出证据套件——否则 holdout 只见
        -q 点号，证据饥饿永远 FAIL（S2 issue #2 首次裁决死因）。"""
        assert evidence_suites(["backend/src/trading/pipeline.py"]) == ["backend"]
        assert evidence_suites(["frontend/src/pages/Metals.tsx"]) == ["frontend"]

    def test_perimeter_change_no_suite(self):
        assert evidence_suites(["README.md", "docs/x.md", "MISSION.md"]) == []

    def test_dedup_and_sort(self):
        files = [
            "frontend/src/lib/api.ts",
            "backend/src/pipeline.py",
            "backend/tests/test_pipeline.py",
        ]
        assert evidence_suites(files) == ["backend", "frontend"]

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
        assert node_timeout("implement") == "30m"

    def test_unknown_node_defaults_15m(self):
        from factory_lib import node_timeout
        assert node_timeout("mystery") == "15m"

    def test_per_node_env_override_wins(self):
        from factory_lib import node_timeout
        env = {"FACTORY_TIMEOUT_IMPLEMENT": "45m", "FACTORY_TIMEOUT": "9m"}
        assert node_timeout("implement", env) == "45m"

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
        assert classify_task(["README.md", "docs/x.md", "notes/y.mdx"]) == "doc"

    def test_code_with_tests(self):
        from factory_lib import classify_task
        assert classify_task(["a.py", "test_a.py"]) == "code"

    def test_test_only(self):
        from factory_lib import classify_task
        assert classify_task(["test_a.py", "pkg/tests/b.py"]) == "test"

    def test_mixed(self):
        from factory_lib import classify_task
        assert classify_task(["a.py", "README.md"]) == "mixed"

    def test_md_code_test_mix(self):
        """上游 #5 round3 实际形态：md + code + test 混合 → mixed（真实回归锚点）。"""
        from factory_lib import classify_task
        assert classify_task([
            "docs/01-guide.md",
            "README.md",
            "factory/tests/test_factory_lib.py",
        ]) == "mixed"

    def test_empty(self):
        from factory_lib import classify_task
        assert classify_task([]) == "empty"

    def test_frontend_test_conventions(self):
        """前端 .test.* / .spec.* / __tests__ 约定识别为 test（PR #69 审查）。"""
        from factory_lib import classify_task
        assert classify_task(["frontend/src/__tests__/tradingPage.test.tsx"]) == "test"
        assert classify_task(["src/components/PositionsList.test.ts"]) == "test"
        assert classify_task(["vitest/foo.spec.js"]) == "test"

    def test_frontend_test_plus_src_is_code(self):
        """测试与源码并存（无 md）→ code，不因 .test. 误判为 test-only。"""
        from factory_lib import classify_task
        assert classify_task(["src/foo.ts", "src/foo.test.ts"]) == "code"

    def test_paths_with_spaces_stay_whole(self):
        """空格路径是完整单元（配 fix-issue.sh NUL 传递，PR #70 审查）。"""
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
        assert "判据c（不触周界）" in md

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

    def test_receipt_neutralizes_embedded_marker(self):
        """PR #20 评论1（security）：reason 内嵌标记（LLM 从 issue 评论
        回显）会被 state.py 标记评论通道识别为人工覆盖、永久钉死
        rejected——渲染前中和子串，语义保留；含 [[...]] 嵌套构造。"""
        md = reject_receipt({"verdict": "reject", "reasons": [
            "判据b: 不通过，评论已写 [factory:rejected] 表示异议",
            "判据c: 不通过，嵌套 [[factory:rejected]] 构造"]})
        assert "[factory:rejected]" not in md
        assert "factory:rejected" in md  # 去括号保留语义

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
