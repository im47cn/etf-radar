"""feedback.py 反哺决策层测试：契约优先，不 mock git。

候选契约（feedable = trailer ∨ bootstrap）、账本排除、cherry-pick 顺序、
漂移分类的上游侧判定、账本读写往返。CLI 子进程路径由真跑（dry-run +
首次反哺）覆盖，此处只测纯函数。
运行：python3 -m pytest .factory/test_feedback.py -o addopts= -q
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import feedback  # noqa: E402

RS = "\x1e"


def _log(*records):
    """构造 git log --format=%H%x00%s%x00%b%x1e 的输出。"""
    return "".join("%s\x00%s\x00%s%s" % (sha, subj, body, RS)
                   for sha, subj, body in records)


# ---- parse_git_log：trailer 判定 ----

def test_parse_trailer_yes_marks_feedable():
    commits = feedback.parse_git_log(_log(
        ("a" * 40, "fix(factory): 并发修复", "正文\n\nUpstream-Feedback: yes")))
    assert commits[0]["feedable"] is True


def test_parse_trailer_no_and_case_insensitive():
    assert feedback.parse_git_log(_log(
        ("a" * 40, "s", "Upstream-Feedback: no")))[0]["feedable"] is False
    assert feedback.parse_git_log(_log(
        ("a" * 40, "s", "upstream-feedback: YES")))[0]["feedable"] is True


def test_parse_trailer_not_in_body():
    assert feedback.parse_git_log(_log(
        ("a" * 40, "s", "普通正文无标记")))[0]["feedable"] is False


def test_parse_bootstrap_prefix_matches_full_sha():
    full = next(iter(feedback.BOOTSTRAP_CANDIDATES)) + "0" * 33
    assert feedback.parse_git_log(_log(
        (full, "s", "")))[0]["feedable"] is True


def test_parse_skips_malformed_records():
    commits = feedback.parse_git_log(_log(("a" * 40, "s", "b")) + "garbage\x1e")
    assert len(commits) == 1


def test_parse_empty_input():
    assert feedback.parse_git_log("") == []


# ---- 资产链判定：feedable_assets / collect_pending ----

def _c(sha, body, files):
    return {"sha": sha, "subject": "s", "feedable": "yes" in body,
            "files": files}


def test_feedable_assets_last_toucher_decides():
    # 新→旧：dispatch.sh 先被 trailer 提交泛化、后被更新的无 trailer 提交特化
    # → 最后触碰者无 trailer → 不 feedable（特化保护，整体不反哺）
    commits = [_c("e" * 40, "", {".factory/dispatch.sh"}),
               _c("f" * 40, "Upstream-Feedback: yes", {".factory/dispatch.sh"})]
    assert feedback.feedable_assets(commits) == set()
    # 反序：最后（最新）触碰者带 trailer → feedable
    commits = [_c("f" * 40, "Upstream-Feedback: yes", {".factory/dispatch.sh"}),
               _c("e" * 40, "", {".factory/dispatch.sh"})]
    assert feedback.feedable_assets(commits) == {".factory/dispatch.sh"}

def test_ledger_file_excluded_from_asset_chain():
    # 账本是运行时记录：trailer 提交触碰也不 feedable，不进反哺链
    commits = [_c("f" * 40, "Upstream-Feedback: yes",
                  {".factory/feedback-log.jsonl"})]
    assert feedback.feedable_assets(commits) == set()
    assert feedback.collect_pending(commits, set()) == []


def test_collect_pending_pulls_untrailer_toucher_into_chain():
    """断链自愈核心：feedable 资产的无 trailer 历史触碰者随链入候选。"""
    commits = [  # 新→旧
        _c("c" * 40, "Upstream-Feedback: yes", {".factory/feedback.py"}),
        _c("b" * 40, "", {".factory/feedback.py", ".factory/README.md"}),
        _c("a" * 40, "Upstream-Feedback: yes", {".factory/dispatch.sh"})]
    # README.md 最后触碰者 b 无 trailer → 不 feedable；dispatch.sh 最后
    # 触碰者 a 带 trailer → feedable；feedback.py 同理 → a、b、c 全入链
    pending = feedback.collect_pending(commits, set())
    assert [c["sha"] for c in pending] == ["a" * 40, "b" * 40, "c" * 40]


def test_collect_pending_excludes_pure_specialization():
    # 资产最后触碰者无 trailer → 其全部触碰者不进候选（特化资产不反哺）
    commits = [_c("b" * 40, "Upstream-Feedback: yes", {".factory/x.py"}),
               _c("a" * 40, "", {".factory/backend.py"})]
    pending = feedback.collect_pending(commits, set())
    assert [c["sha"] for c in pending] == ["b" * 40]


def test_collect_pending_excludes_ledger_and_keeps_cherry_pick_order():
    commits = [  # 新→旧
        _c("f" * 40, "Upstream-Feedback: yes", {".factory/a.sh"}),
        _c("e" * 40, "Upstream-Feedback: yes", {".factory/a.sh"}),
        _c("d" * 40, "", {".factory/b.py"})]
    pending = feedback.collect_pending(commits, {"e" * 40})
    assert [c["sha"] for c in pending] == ["f" * 40]


def test_collect_pending_empty_when_all_ledgered():
    commits = [_c("a" * 40, "Upstream-Feedback: yes", {".factory/a.sh"})]
    assert feedback.collect_pending(commits, {"a" * 40}) == []


# ---- 账本读写往返 ----

def test_ledger_roundtrip(tmp_path):
    ledger = tmp_path / "feedback-log.jsonl"
    assert feedback.load_ledger(ledger) == set()  # 不存在 → 空
    feedback.append_ledger(ledger, "a" * 40, "s", 7, "im47cn/awesome-rules")
    feedback.append_ledger(ledger, "b" * 40, "s2", 7, "im47cn/awesome-rules")
    assert feedback.load_ledger(ledger) == {"a" * 40, "b" * 40}


def test_load_ledger_tolerates_corrupt_line(tmp_path):
    ledger = tmp_path / "feedback-log.jsonl"
    ledger.write_text('{"sha": "%s"}\nnot-json\n' % ("a" * 40), encoding="utf-8")
    assert feedback.load_ledger(ledger) == {"a" * 40}


# ---- 漂移分类 ----

def test_classify_drift_sides_and_excludes():
    up = "/tmp/up/.factory"
    out = "\n".join([
        "Only in %s: cron-dispatch.sh" % up,
        "Only in /tmp/etf/.factory: triage-batch.sh",
        "Only in %s/artifacts: issue-2" % up,        # 运行时目录 → 排除
        "Files %s/state.py and /tmp/etf/.factory/state.py differ" % up,
        "Files %s/locks/x and /tmp/etf/.factory/locks/x differ" % up,  # 排除
    ])
    drift = feedback.classify_drift(out, up)
    assert len(drift["upstream_only"]) == 1
    assert len(drift["local_only"]) == 1
    assert len(drift["differing"]) == 1


def test_render_report_includes_counts():
    pending = [{"sha": "a" * 40, "subject": "s", "feedable": True}]
    drift = {"upstream_only": ["Only in /up: ledger.jsonl"],
             "local_only": [], "differing": []}
    text = feedback.render_report(pending, drift)
    assert "1 个" in text and "ledger.jsonl" in text and "[上游独有] 1 项" in text


def test_render_report_no_drift_marker():
    text = feedback.render_report([], {"upstream_only": [], "local_only": [],
                                       "differing": []})
    assert "（无）" in text


# ---- 状态行 ----

def test_status_line_with_and_without_pending():
    assert "3 commits" in feedback.status_line(3)
    assert "0" in feedback.status_line(0) and "无需动作" in feedback.status_line(0)


# ---- 依赖闭包（PR #18 实败防复演）----

def test_extract_refs_collects_and_dedups():
    src = ('A="$(cat "$FACTORY/prompts/feedback-adapt.md)"\n'
           'python3 "$FACTORY/feedback.py" pending\n'
           '${FACTORY}/factory_lib.py x\n'
           '$FACTORY/artifacts/fb/manifest.json\n')  # 运行时产物，不算依赖
    assert feedback.extract_factory_refs(src) == [
        "factory_lib.py", "feedback.py", "prompts/feedback-adapt.md"]


def test_closure_flags_missing_dep_pr18_replay():
    """PR #18 实败复演：只反哺 feedback-upstream.sh，引用的配套件未随行。"""
    patch = ('+PROMPT="$(cat "$FACTORY/prompts/feedback-adapt.md)"\n'
             '+python3 "$FACTORY/feedback.py" pending\n')
    cands = [{"sha": "9" * 40, "subject": "s", "feedable": True,
              "patch": patch, "files": [".factory/feedback-upstream.sh"]}]
    missing = feedback.closure_missing(cands, upstream_factory_files=[
        ".factory/dispatch.sh", ".factory/factory_lib.py"])
    assert set(missing) == {"feedback.py", "prompts/feedback-adapt.md"}
    assert missing["feedback.py"] == ["9" * 9]


def test_closure_passes_when_dep_in_candidate_files():
    patch = '+python3 "$FACTORY/feedback.py" pending\n'
    cands = [{"sha": "a" * 40, "subject": "s", "feedable": True,
              "patch": patch, "files": [".factory/x.sh", ".factory/feedback.py"]}]
    assert feedback.closure_missing(
        cands, upstream_factory_files=[".factory/dispatch.sh"]) == {}


def test_closure_passes_when_dep_upstream_has_it():
    patch = '+python3 "$FACTORY/feedback.py" pending\n'
    cands = [{"sha": "a" * 40, "subject": "s", "feedable": True,
              "patch": patch, "files": [".factory/x.sh"]}]
    assert feedback.closure_missing(
        cands, upstream_factory_files=[".factory/feedback.py"]) == {}
