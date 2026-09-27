"""feedback.py 反哺决策层测试：契约优先，不 mock git。

候选契约（feedable = trailer ∨ bootstrap）、账本排除、cherry-pick 顺序、
漂移分类的上游侧判定、账本读写往返。CLI 子进程路径由真跑（dry-run +
首次反哺）覆盖，此处只测纯函数。
运行：python3 -m pytest .factory/tests -q（conftest 注入 .factory 到 sys.path）
"""
import feedback

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


def test_collect_pending_patch_id_dedup_beats_sha_drift():
    """patch-id 去重：rebase/amend 后 SHA 变、内容不变 → 仍排除。
    2026-08-22 孪生 SHA 实证——SHA 去重随本地历史重写失效，已反哺内容
    重新成为候选、重复反哺（etf-radar PR#75）。"""
    reborn = dict(_c("9" * 40, "Upstream-Feedback: yes", {".factory/a.sh"}),
                  patch_id="pid-1")
    assert feedback.collect_pending([reborn], set(), {"pid-1"}) == []


def test_collect_pending_patch_id_mismatch_keeps_candidate():
    """patch-id 不同（真新内容）→ 正常入候选；无 patch_id 条目退化 SHA 匹配。"""
    new = dict(_c("7" * 40, "Upstream-Feedback: yes", {".factory/a.sh"}),
               patch_id="pid-2")
    assert [c["sha"] for c in
            feedback.collect_pending([new], set(), {"pid-1"})] == ["7" * 40]
    noid = _c("8" * 40, "Upstream-Feedback: yes", {".factory/a.sh"})
    assert [c["sha"] for c in
            feedback.collect_pending([noid], set(), {"pid-1"})] == ["8" * 40]

# ---- 账本读写往返 ----

def test_ledger_roundtrip(tmp_path):
    ledger = tmp_path / "feedback-log.jsonl"
    assert feedback.load_ledger(ledger) == []  # 不存在 → 空
    feedback.append_ledger(ledger, "a" * 40, "s", 7, "im47cn/awesome-rules")
    feedback.append_ledger(ledger, "b" * 40, "s2", 7, "im47cn/awesome-rules")
    assert {e["sha"] for e in feedback.load_ledger(ledger)} == {"a" * 40, "b" * 40}


def test_load_ledger_tolerates_corrupt_line(tmp_path):
    ledger = tmp_path / "feedback-log.jsonl"
    ledger.write_text('{"sha": "%s"}\nnot-json\n' % ("a" * 40), encoding="utf-8")
    assert {e["sha"] for e in feedback.load_ledger(ledger)} == {"a" * 40}


def test_ledger_persists_patch_id(tmp_path):
    """etf-radar PR#75：patch-id 落账本——记录时的计算结果随条目持久化。"""
    ledger = tmp_path / "feedback-log.jsonl"
    feedback.append_ledger(ledger, "a" * 40, "s", 7, "r", patch_id="pid-a")
    feedback.append_ledger(ledger, "b" * 40, "s2", 7, "r")  # None 也合法（空 diff/非资产）
    entries = feedback.load_ledger(ledger)
    assert entries[0]["patch_id"] == "pid-a" and entries[1]["patch_id"] is None


def test_stored_patch_id_survives_object_loss(tmp_path, monkeypatch):
    """etf-radar PR#75 核心：账本已有 patch_id 的条目不依赖对象重算——账本
    提交被 GC 后（重算 _patch_id 返回 None），持久化值仍参与去重。"""
    entries = [{"sha": "a" * 40, "patch_id": "pid-a"},
               {"sha": "b" * 40}]                       # 旧条目：无字段 → 重算兜底
    monkeypatch.setattr(feedback, "_patch_id", lambda sha: "pid-recalc")
    assert feedback.ledger_patch_ids(entries) == {"pid-a", "pid-recalc"}
    monkeypatch.setattr(feedback, "_patch_id", lambda sha: None)   # 对象全丢
    assert feedback.ledger_patch_ids(entries) == {"pid-a"}

def test_classify_drift_sides_and_excludes():
    up = "/tmp/up/.factory"
    out = "\n".join(
        [
            f"Only in {up}: cron-dispatch.sh",
            "Only in /tmp/etf/.factory: triage-batch.sh",
            f"Only in {up}/artifacts: issue-2",
            f"Files {up}/state.py and /tmp/etf/.factory/state.py differ",
            f"Files {up}/locks/x and /tmp/etf/.factory/locks/x differ",
        ]
    )
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


# ---- superseded_map：SHA 语义缺口（疑似已随演化反哺） ----

def _sup_env():
    """新→旧四提交：R1 覆盖 P 并已入账；R2 更晚未入账；R3 更早已入账。"""
    p, r1, r2, r3 = "p" * 40, "1" * 40, "2" * 40, "3" * 40
    commits = [  # git log 顺序：新 → 旧
        _c(r2, "yes", [".factory/fix-issue.sh"]),          # 最新，未入账
        _c(r1, "yes", [".factory/fix-issue.sh", ".factory/factory_lib.py"]),  # 已入账
        _c(p, "yes", [".factory/fix-issue.sh"]),           # pending 候选
        _c(r3, "yes", [".factory/fix-issue.sh", ".factory/factory_lib.py"]),  # 最旧，已入账
    ]
    return commits, {"ledger": {r1, r3}, "p": p, "r1": r1}


def test_superseded_file_cover_by_later_recorded():
    commits, env = _sup_env()
    assert feedback.superseded_map(commits, env["ledger"]) == {env["p"]: env["r1"]}


def test_superseded_ignores_older_recorded():
    """更早的已反哺提交不可能携带更晚 pending 的内容（演化方向）。"""
    commits, env = _sup_env()
    ledger = {env["p"]: None}  # 占位不可用——直接构造仅含 r3 的账本
    smap = feedback.superseded_map(commits, {"3" * 40})
    assert smap == {}  # r3 更早；r2 未入账 → p 无有效 superseder


def test_superseded_ignores_unrecorded_cover():
    """文件集覆盖但未入账（r2 自己也 pending）不作数。"""
    commits, env = _sup_env()
    assert feedback.superseded_map(commits, set()) == {}


def test_superseded_prefix_ledger_sha_matches():
    """账本短 SHA 前缀匹配（历史账本存在短记录，如 dfe8a3ab）。
    r3 全量入账，r1 仅前缀入账——两者都算已反哺，pending 只剩 p/r2。"""
    commits, env = _sup_env()
    assert feedback.superseded_map(commits, {"1" * 8, "3" * 40}) == {env["p"]: env["r1"]}


# ---- adapt_manifest：适配节点输入契约（manifest.json schema） ----

def test_adapt_manifest_clean_and_conflicted_split():
    a, b = "a" * 40, "b" * 40
    items = feedback.adapt_manifest(
        "%s\tfix(factory): 并发修复\n%s\tfix: 冲突候选" % (a, b), {b})
    assert items == [
        {
            "sha": a,
            "subject": "fix(factory): 并发修复",
            "status": "clean",
            "patch": f"patches/{a[:9]}.patch",
        },
        {
            "sha": b,
            "subject": "fix: 冲突候选",
            "status": "conflicted",
            "patch": f"patches/{b[:9]}.patch",
        },
    ]


def test_adapt_manifest_takes_shell_filtered_pending_verbatim():
    # superseded 由 shell 剔除后传入（2026-08-28 下沉时的取舍）——此处不
    # 重算：重算会把被人工跳过的候选回流进适配节点
    only = "c" * 40
    items = feedback.adapt_manifest("%s\t仅存候选" % only, set())
    assert [i["sha"] for i in items] == [only]
    assert items[0]["status"] == "clean"


def test_adapt_manifest_preserves_old_to_new_order():
    shas = [c * 40 for c in "abc"]
    text = "".join("%s\ts%s\n" % (s, i) for i, s in enumerate(shas))
    assert [i["sha"] for i in feedback.adapt_manifest(text, set())] == shas

def test_gather_commits_merges_files(monkeypatch):
    """_files_by_sha 结果必须挂回 commits（feedable/pending 判定的 files 来源）。"""
    commits = [{"sha": "a" * 40, "subject": "s", "feedable": True},
               {"sha": "b" * 40, "subject": "t", "feedable": False}]
    # b 不提供映射：.get(sha, set()) 空集回退必须被测到（python#26 审查
    # 收口——夹具若给全映射，回归为直接索引 fbs[sha] 后 KeyError 不可见）
    fbs = {"a" * 40: {"factory_lib.py"}}
    monkeypatch.setattr(feedback, "_git_log_commits", lambda: commits)
    monkeypatch.setattr(feedback, "_files_by_sha", lambda: fbs)
    out = feedback._gather_commits()
    assert out[0]["files"] == {"factory_lib.py"}
    # 未触碰资产的提交 → 空集（feedable_assets/collect_pending 的 .get 契约）
    assert out[1]["files"] == set()
    assert out[1]["feedable"] is False
