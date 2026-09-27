"""dispatch_liveness 滞留检测负控制（第三死法：GitHub 侧滞留）。

2026-09-15 issue #165 实证：零改动轮留守 in-progress 5 天不可见。
本套件钉死三种滞留（in-progress 无租约 / rejected 无回执 / rejected
超宽限无跟进）必须进 problems（= 回归 FAIL），以及合法状态（链存活
持锁 / 有回执宽限内 / hosting 不可用）不得误报。hosting 子进程一律
monkeypatch，零网络零 git。
"""
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "regression"))
import dispatch_liveness as dl


class _FakeRun:
    def __init__(self, rc=0, stdout=""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = ""


def _mk_repo(tmp_path: Path, locks: dict = None) -> Path:
    """临时仓骨架：<repo>/.factory/{locks/leases,regression}"""
    repo = tmp_path / "r"
    (repo / ".factory" / "locks" / "leases").mkdir(parents=True)
    (repo / ".factory" / "regression").mkdir(parents=True)
    for name, content in (locks or {}).items():
        (repo / ".factory" / "locks" / "leases" / name).write_text(content)
    return repo


def _patch_hosting(monkeypatch, issues=None, unavailable=False):
    def fake_run(cmd, **kw):
        assert kw.get("cwd"), "hosting.py 须以目标仓为 cwd 运行（slug 解析）"
        if unavailable:
            return _FakeRun(rc=1)
        return _FakeRun(stdout=json.dumps(issues or []))
    monkeypatch.setattr(dl.subprocess, "run", fake_run)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- in-progress 滞留：#165 事故形态 ----------------------------------------

def test_in_progress_without_lock_fails(tmp_path, monkeypatch, capsys):
    _patch_hosting(monkeypatch, issues=[
        {"number": 165, "labels": ["factory:accepted", "factory:in-progress"],
         "updatedAt": _iso(datetime.now(timezone.utc))}])
    repo = _mk_repo(tmp_path)  # 无 issue:165.lock
    problems = []
    assert dl.check_stalled_labels(repo, 7, problems) == "ok"
    assert any("#165" in p and "in-progress" in p for p in problems), problems


def test_in_progress_with_live_lock_ok(tmp_path, monkeypatch, capsys):
    _patch_hosting(monkeypatch, issues=[
        {"number": 165, "labels": ["factory:in-progress"],
         "updatedAt": _iso(datetime.now(timezone.utc))}])
    repo = _mk_repo(tmp_path, locks={"issue:165.lock": "mid|9|123|0|900"})
    problems = []
    assert dl.check_stalled_labels(repo, 7, problems) == "ok"
    assert not problems


def test_in_progress_stale_lock_fails(tmp_path, monkeypatch, capsys):
    # 审查 minor #7：链被 SIGKILL 留下过期残锁——mtime+租期 < now 须判滞留
    import os
    _patch_hosting(monkeypatch, issues=[
        {"number": 165, "labels": ["factory:in-progress"],
         "updatedAt": _iso(datetime.now(timezone.utc))}])
    repo = _mk_repo(tmp_path, locks={"issue:165.lock": "mid|9|123|0|900"})
    lock = repo / ".factory" / "locks" / "leases" / "issue:165.lock"
    old = datetime.now().timestamp() - 2000
    os.utime(lock, (old, old))
    problems = []
    assert dl.check_stalled_labels(repo, 7, problems) == "ok"
    assert any("#165" in p for p in problems), "过期残锁被当活链（滞留漏报）"


def test_pg_mode_degrades_in_progress_check(tmp_path, monkeypatch, capsys):
    # 审查 major #2：PG 形态租约在库、本地锁文件从不存在——
    # in-progress 检测必须整体降级，否则每个存活链每天误报滞留
    _patch_hosting(monkeypatch, issues=[
        {"number": 165, "labels": ["factory:in-progress"],
         "updatedAt": _iso(datetime.now(timezone.utc))}])
    monkeypatch.setenv("SUPABASE_DB", "postgres://x")
    repo = _mk_repo(tmp_path)  # 无锁文件（PG 形态常态）
    problems = []
    assert dl.check_stalled_labels(repo, 7, problems) == "note"
    assert not problems
    assert "PG" in capsys.readouterr().out


# -- rejected 滞留：宽限阈值 --------------------------------------------------
RECEIPT_HEADING = "## 工厂 triage 裁决：reject —— 判据 b 不通过"
RECEIPT = (f"{RECEIPT_HEADING}\n"
           "<!-- factory:receipt:issue-104:rbatch -->")


def test_rejected_beyond_grace_fails(tmp_path, monkeypatch, capsys):
    old = datetime.now(timezone.utc) - timedelta(days=10)
    _patch_hosting(monkeypatch, issues=[
        {"number": 104, "labels": ["factory:rejected"],
         "updatedAt": _iso(old),
         "comments": [{"author": "im47cn", "body": RECEIPT}]}])
    repo = _mk_repo(tmp_path)
    problems = []
    assert dl.check_stalled_labels(repo, 7, problems) == "ok"
    assert any("#104" in p and "rejected" in p for p in problems), problems


def test_rejected_within_grace_ok(tmp_path, monkeypatch, capsys):
    recent = datetime.now(timezone.utc) - timedelta(days=2)
    _patch_hosting(monkeypatch, issues=[
        {"number": 104, "labels": ["factory:rejected"],
         "updatedAt": _iso(recent),
         "comments": [{"author": "im47cn", "body": RECEIPT}]}])
    repo = _mk_repo(tmp_path)
    problems = []
    assert dl.check_stalled_labels(repo, 7, problems) == "ok"
    assert not problems


def test_rejected_missing_updatedat_skips(tmp_path, monkeypatch, capsys):
    _patch_hosting(monkeypatch, issues=[
        {"number": 104, "labels": ["factory:rejected"], "updatedAt": None,
         "comments": [{"author": "im47cn", "body": RECEIPT}]}])
    repo = _mk_repo(tmp_path)
    problems = []
    dl.check_stalled_labels(repo, 7, problems)
    assert not problems

def test_rejected_no_receipt_fails_immediately(tmp_path, monkeypatch):
    """#207 事故形态：只落标无回执——链完整性违规即时 FAIL，不进宽限
    时钟（新鲜 updatedAt 否则宽限 OK），有回执才轮到滞留判定。"""
    _patch_hosting(monkeypatch, issues=[
        {"number": 207, "labels": ["factory:rejected"],
         "updatedAt": _iso(datetime.now(timezone.utc))}])
    repo = _mk_repo(tmp_path)
    problems = []
    assert dl.check_stalled_labels(repo, 7, problems) == "ok"
    assert any("#207" in p and "无回执" in p for p in problems), problems
    assert all("滞留" not in p for p in problems), problems


def test_rejected_pre_receipt_comments_do_not_count(tmp_path, monkeypatch):
    """提交讨论评论 ≠ 回执——回执判据 = 幂等 marker（issue_reject 评论
    尾埋），判据与 rejected_reconcile 同源不得漂移。"""
    _patch_hosting(monkeypatch, issues=[
        {"number": 104, "labels": ["factory:rejected"],
         "updatedAt": _iso(datetime.now(timezone.utc)),
         "comments": [{"author": "im47cn", "body": "按指引重投"}]}])
    repo = _mk_repo(tmp_path)
    problems = []
    dl.check_stalled_labels(repo, 7, problems)
    assert any("无回执" in p for p in problems), problems

def test_rejected_human_quoted_heading_not_receipt(tmp_path, monkeypatch):
    """PR #211 Sourcery 评论2：人工复述回执标题（无 marker）不算回执
    ——判据与 rejected_reconcile 同为幂等 marker，两层不得漂移。"""
    _patch_hosting(monkeypatch, issues=[
        {"number": 104, "labels": ["factory:rejected"],
         "updatedAt": _iso(datetime.now(timezone.utc)),
         "comments": [{"author": "im47cn", "body": RECEIPT_HEADING}]}])
    repo = _mk_repo(tmp_path)
    problems = []
    dl.check_stalled_labels(repo, 7, problems)
    assert any("无回执" in p for p in problems), problems


# -- 降级：hosting 不可用不误报 ----------------------------------------------

def test_hosting_unavailable_degrades_to_note(tmp_path, monkeypatch, capsys):
    _patch_hosting(monkeypatch, unavailable=True)
    repo = _mk_repo(tmp_path)
    problems = []
    assert dl.check_stalled_labels(repo, 7, problems) == "note"
    assert not problems
    assert "跳过" in capsys.readouterr().out


# -- 工具函数 ------------------------------------------------------------------

def test_updated_age_parses_and_rejects():
    now = datetime.now(timezone.utc)
    assert dl._gh_updated_age_secs(_iso(now - timedelta(hours=1))) < 3700
    assert dl._gh_updated_age_secs(None) is None
    assert dl._gh_updated_age_secs("not-a-date") is None
    assert dl._gh_updated_age_secs("") is None


# -- 端到端：problems 非空 → main 退出码 1（负控制：滞留必须翻红回归）--------

def test_stall_drives_nonzero_exit(tmp_path, monkeypatch, capsys):
    _patch_hosting(monkeypatch, issues=[
        {"number": 165, "labels": ["factory:in-progress"],
         "updatedAt": _iso(datetime.now(timezone.utc))}])
    repo = _mk_repo(tmp_path)
    monkeypatch.setattr(dl, "DEFAULT_REGISTRY", tmp_path / "none.conf")
    monkeypatch.setattr(dl, "REPO", repo)  # 无注册表 → 单仓自检指向夹具仓
    monkeypatch.delenv("SUPABASE_DB", raising=False)
    monkeypatch.setattr(dl.sys, "argv",
                        ["dispatch_liveness.py", "--stale-days", "7"])
    rc = dl.main()
    assert rc == 1, "滞留未驱动 FAIL（回归层对死信筒失明）"
