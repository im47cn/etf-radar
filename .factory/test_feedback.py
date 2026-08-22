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


# ---- collect_pending：账本排除与顺序 ----

def test_collect_pending_excludes_ledger_and_keeps_cherry_pick_order():
    commits = feedback.parse_git_log(_log(
        ("f" * 40, "新 trailer 提交", "Upstream-Feedback: yes"),
        ("e" * 40, "已反哺 trailer 提交", "Upstream-Feedback: yes"),
        ("d" * 40, "无标记提交", ""),
        (feedback.BOOTSTRAP_CANDIDATES.__iter__().__next__() + "x" * 33,
         "bootstrap 补录", "")))
    pending = feedback.collect_pending(commits, {"e" * 40})
    # git log 新→旧；pending 必须反转为旧→新（cherry-pick 顺序）
    assert [c["sha"] for c in pending] == [
        feedback.BOOTSTRAP_CANDIDATES.__iter__().__next__() + "x" * 33,
        "f" * 40]


def test_collect_pending_empty_when_all_ledgered():
    commits = feedback.parse_git_log(_log(
        ("a" * 40, "s", "Upstream-Feedback: yes")))
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
