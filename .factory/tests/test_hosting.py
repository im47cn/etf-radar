"""hosting.py 契约测试（ADR-008）——抽象层的两条防线：

1. GitHub 适配器：中立 schema 归一化 + gh 命令构造（含 --repo 追加与
   单请求原子换标签）；gh 失败必须 HostingError（fail-closed 不静默）。
2. Codeup 适配器：请求形状（org 级端点 / comment_type+resolved 必填 /
   mergeType 枚举映射）经 mock _req 锁定；平台缺口三件套必须 exit 2
   （issue 面 / label unlink / label history）——缺口静默降级等于
   状态机半转移。

运行：python3 -m pytest .factory/tests/test_hosting.py -q
（conftest 注入 .factory 到 sys.path）
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import hosting


def _raise(exc: BaseException) -> None:
    """异常注入辅助：mock 回调用（lambda 内不能 raise 语句）。"""
    raise exc


def _cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


# ── GitHub：中立归一化 ───────────────────────────────────────────────

class TestGithubNormalize:
    def test_issue_gh_shape_to_neutral(self):
        d = {"number": 7, "state": "CLOSED", "title": "t", "body": "b",
             "labels": [{"name": "factory:accepted"}, {"name": "x"}],
             "comments": [{"author": {"login": "u"}, "body": "c"}]}
        n = hosting.GitHubAdapter._issue(d)
        assert n["state"] == "closed"
        assert n["labels"] == ["factory:accepted", "x"]
        assert n["comments"] == [{"author": "u", "body": "c"}]

    def test_pr_review_and_mergeable_map(self):
        for gh, want in [("APPROVED", "approved"),
                         ("CHANGES_REQUESTED", "changes_requested"),
                         ("REVIEW_REQUIRED", "pending"), (None, "pending")]:
            n = hosting.GitHubAdapter._pr(
                {"number": 1, "state": "OPEN", "reviewDecision": gh,
                 "mergeable": "MERGEABLE", "labels": [],
                 "headRefName": "h", "baseRefName": "b"})
            assert n["review"] == want, gh
        assert hosting.GitHubAdapter._pr(
            {"number": 1, "state": "MERGED", "mergeable": "CONFLICTING"}
        )["mergeable"] is False

    def test_gh_failure_raises_not_silent(self):
        ad = hosting.GitHubAdapter()
        ad.slug = lambda o=None: "o/r"
        ad._gh = lambda a, r=None, s=None: _cp(rc=1, err="boom")
        with pytest.raises(hosting.HostingError):
            ad.issue_view(1)


# ── GitHub：命令构造（含原子换标签）─────────────────────────────────

class TestGithubCommands:
    def _ad(self, calls):
        ad = hosting.GitHubAdapter()
        ad.slug = lambda o=None: "o/r" if o is None else o

        def fake_gh(args, repo_override=None, stdin=None):
            calls.append((tuple(args), repo_override))
            return _cp(out="{}")
        ad._gh = fake_gh
        return ad

    def test_set_labels_single_request_atomic(self):
        calls = []
        ad = self._ad(calls)
        ad.issue_set_labels(9, add=["factory:in-progress"],
                            remove=["factory:accepted"])
        # add+remove 一次 gh edit：半途断裂=双标签的窗口被消除（factory-lib 语义）
        edits = [c for c in calls if c[0][:2] == ("issue", "edit")]
        assert len(edits) == 1
        args = edits[0][0]
        assert "--remove-label" in args and "--add-label" in args

    def test_set_labels_empty_remove_omits_flag(self):
        calls = []
        ad = self._ad(calls)
        ad.issue_set_labels(9, add=["x"])
        args = [c for c in calls if c[0][:2] == ("issue", "edit")][0][0]
        assert "--remove-label" not in args  # bash 3.2 空参守卫的 py 侧等价

    def test_set_labels_false_negative_reconciles(self):
        """#207 实证形态：gh edit 非零但标签已落服务端（mutation
        landed + client reported failure）——失败路径重读标签态，
        目标已达成即幂等成功，裁决不被传输层误报否决。"""
        calls = []
        ad = hosting.GitHubAdapter()
        ad.slug = lambda o=None: "o/r"

        def fake_gh(args, repo_override=None, stdin=None):
            calls.append(tuple(args))
            if args[:2] == ["issue", "edit"]:
                return _cp(rc=1, err="gh: POST api.github.com: 502")
            return _cp(out=json.dumps(
                {"labels": [{"name": "factory:rejected"}]}))
        ad._gh = fake_gh
        assert ad.issue_set_labels(9, add=["factory:rejected"],
                                   remove=["factory:triaging"]) is True
        assert calls[1][:2] == ("issue", "view")  # 复核是读路径

    def test_set_labels_true_failure_raises(self):
        """复核确证目标未达成 → 原 fail-closed 透传（和解不吞真失败）。"""
        ad = hosting.GitHubAdapter()
        ad.slug = lambda o=None: "o/r"

        def fake_gh(args, repo_override=None, stdin=None):
            if args[:2] == ["issue", "edit"]:
                return _cp(rc=1, err="boom")
            return _cp(out=json.dumps(
                {"labels": [{"name": "factory:triaging"}]}))
        ad._gh = fake_gh
        with pytest.raises(hosting.HostingError):
            ad.issue_set_labels(9, add=["factory:rejected"])

    def test_set_labels_readback_failure_raises(self):
        """复核读自身失败（网络仍断）→ 不视作已落定，fail-closed。"""
        ad = hosting.GitHubAdapter()
        ad.slug = lambda o=None: "o/r"
        ad._gh = lambda a, r=None, s=None: _cp(rc=1, err="still down")
        with pytest.raises(hosting.HostingError):
            ad.issue_set_labels(9, add=["factory:rejected"])

    def test_pr_set_labels_false_negative_reconciles(self):
        """PR 侧镜像：同构假阴性和解（pr view 重读标签态）。"""
        calls = []
        ad = hosting.GitHubAdapter()
        ad.slug = lambda o=None: "o/r"

        def fake_gh(args, repo_override=None, stdin=None):
            calls.append(tuple(args))
            if args[:2] == ["pr", "edit"]:
                return _cp(rc=1, err="gh: 502")
            return _cp(out=json.dumps(
                {"labels": [{"name": "factory:in-progress"}]}))
        ad._gh = fake_gh
        assert ad.pr_set_labels(12, add=["factory:in-progress"]) is True
        assert calls[1][:2] == ("pr", "view")

    def test_pr_create_overrides_repo(self):
        calls = []
        ad = self._ad(calls)
        ad._gh = lambda args, repo_override=None, stdin=None: (
            calls.append((tuple(args), repo_override)) or _cp(out="https://x/pull/12"))
        out = ad.pr_create("br", "t", "b", label="l", base="main",
                           repo="up/stream")
        assert out["number"] == 12
        assert calls[0][1] == "up/stream"  # feedback-upstream 的上游仓显式覆盖

    def test_label_history_neutral_events(self):
        ad = hosting.GitHubAdapter()
        ad.slug = lambda o=None: "o/r"
        events = [{"event": "labeled", "label": {"name": "factory:needs-fix"}},
                  {"event": "unlabeled", "label": {"name": "factory:needs-fix"}},
                  {"event": "labeled", "label": {"name": "other"}},
                  {"event": "commented"}]
        ad._gh_raw = None
        orig = subprocess.run
        hosting.subprocess.run = lambda *a, **k: _cp(out=json.dumps(events))
        try:
            hist = ad.label_history(5)
        finally:
            hosting.subprocess.run = orig
        assert hist == [{"op": "add", "label": "factory:needs-fix"},
                        {"op": "remove", "label": "factory:needs-fix"},
                        {"op": "add", "label": "other"}]
    def test_pr_create_requires_explicit_base(self):
        """CodeRabbit E（GitHub 侧镜像 codeup）：--base 显式必填——gh
        猜默认分支（默认分支因仓而异）会静默落错基线；缺省 raise
        HostingError code=2（fail-closed，绝不条件拼接静默省略）。"""
        ad = hosting.GitHubAdapter()
        ad.slug = lambda o=None: "o/r"
        with pytest.raises(hosting.HostingError) as e:
            ad.pr_create("br", "t", "b")
        assert e.value.code == 2
        assert "--base" in str(e.value)

    def test_pr_create_explicit_base_into_gh_args(self):
        """显式 base 进 gh 参数（args 含 --base 且后一位为主干名）——
        宿主脚本（feedback-upstream/upstream-sync-check）base 落点锚。"""
        calls = []
        ad = self._ad(calls)
        ad._gh = lambda args, repo_override=None, stdin=None: (
            calls.append((tuple(args), repo_override)) or _cp(out="https://x/pull/12"))
        assert ad.pr_create("br", "t", "b", base="main")["number"] == 12
        args = calls[0][0]
        assert args[args.index("--base") + 1] == "main"

    def test_auth_diagnose_reports_gh_stderr(self):
        """auth 失败留痕：gh auth status 原始 stderr 返回（可回溯诊断）。"""
        ad = hosting.GitHubAdapter()
        orig = subprocess.run
        hosting.subprocess.run = lambda *a, **k: _cp(rc=1, err="auth failed: bad keyring")
        try:
            diag = ad.auth_diagnose()
        finally:
            hosting.subprocess.run = orig
        assert diag == "auth failed: bad keyring"

    def test_auth_diagnose_gh_missing_from_path(self):
        """无 gh CLI → 诊断标明环境缺失（区别于凭据/网络失败）。"""
        ad = hosting.GitHubAdapter()
        orig = subprocess.run

        def _boom(*a, **k):
            raise FileNotFoundError

        hosting.subprocess.run = _boom
        try:
            diag = ad.auth_diagnose()
        finally:
            hosting.subprocess.run = orig
        assert "gh CLI 不在 PATH" in diag

# ── Codeup：请求形状 + 缺口 fail-closed ────────────────────────────

class TestCodeupShapes:
    def _ad(self, routes, monkeypatch):
        monkeypatch.setenv("YUNXIAO_ACCESS_TOKEN", "t")
        monkeypatch.setenv("CODEUP_ORG_ID", "org")
        monkeypatch.setenv("CODEUP_REPO_ID", "42")
        """routes: {(method, path_suffix): payload}；记录全部请求（env 注入后
        _cfg/_base 可解析，请求本身被 mock 截获——零网络）。"""
        ad = hosting.CodeupAdapter()
        ad.seen = []

        def fake_req(method, path, body=None, query=None, _retry_rdc=True):
            ad.seen.append((method, path, body, query))
            for (m, suf), payload in routes.items():
                if m == method and path.endswith(suf):
                    return payload
            raise hosting.HostingError(f"mock 未路由: {method} {path}")
        ad._req = fake_req
        return ad

    def test_pr_view_review_normalization(self, monkeypatch):
        ad = self._ad({("GET", "/changeRequests/3"): {
            "result": {"localId": 3, "newVersionState": "UNDER_REVIEW",
                       "reviewers": [{"reviewOpinionStatus": "NOT_PASS"}],
                       "sourceBranch": "s", "targetBranch": "t",
                       "title": "T", "description": "D"}},
            # 【live 2026-08-26】MR 详情无 labels 字段，类标专用端点读回
            ("GET", "/changeRequests/3/labels"): [
                {"name": "factory:needs-fix"}],
            # #66 评论标记模型：pr_view 兼查标记评论（active 承载 needs-fix——
            # 投影语义：无 active 标记的原生工厂类标视为投影失真被过滤）
            ("POST", "/comments/list"): {"result": [
                {"id": "c1", "content": "[factory:label:add] factory:needs-fix",
                 "resolved": False}]}}, monkeypatch)
        n = ad.pr_view(3)
        assert n["review"] == "changes_requested"
        assert n["state"] == "open"
        assert n["labels"] == ["factory:needs-fix"]
        assert n["head"] == "s" and n["base"] == "t"

    def test_pr_set_labels_link_post_degrades(self, monkeypatch, capsys):
        """类标 Link POST 失败 → 降级告警不冒泡（skills#12 审查收口：标记
        评论已承载状态机语义，Link 仅平台原生补充——对齐 _label_id 降级）。"""
        ad = self._ad({
            # add 幂等预检（php#17）：无既有未 resolved 标记 → 发标记评论
            ("POST", "/comments/list"): {"result": []},
            ("POST", "/changeRequests/3/comments"): {"result": {"id": "c1"}},
            ("GET", "/labels"): [{"name": "factory:needs-review", "id": 7}],
            # 故意不路由 POST .../labels → fake_req 抛 HostingError → 降级
        }, monkeypatch)
        assert ad.pr_set_labels(3, add=["factory:needs-review"]) is True
        assert "类标 Link 降级" in capsys.readouterr().err

        ad2 = self._ad({("GET", "/changeRequests/4"): {
            "result": {"localId": 4, "newVersionState": "MERGED",
                       "reviewers": [{"reviewOpinionStatus": "PASS"},
                                     {"reviewOpinionStatus": "PASS"}]}},
            ("POST", "/comments/list"): {"result": []}}, monkeypatch)
        n2 = ad2.pr_view(4)
        assert n2["review"] == "approved" and n2["state"] == "merged"

    def test_pr_comment_required_fields(self, monkeypatch):
        ad = self._ad({("POST", "/comments"): {"success": True}}, monkeypatch)
        ad.pr_comment(5, "LGTM")
        m, p, body, _q = ad.seen[0]
        assert m == "POST" and p.endswith("/changeRequests/5/comments")
        # 【实测】坑位锁定：comment_type 无默认值且 resolved 必填
        assert body["comment_type"] == "GLOBAL_COMMENT"
        assert body["resolved"] is True
        assert body["content"] == "LGTM"

    def test_pr_merge_method_enum(self, monkeypatch):
        ad = self._ad({("POST", "/merge"): {"success": True, "result": True}}, monkeypatch)
        ad.pr_merge(6, method="squash")
        m, p, body, _q = ad.seen[0]
        assert p.endswith("/changeRequests/6/merge")
        assert body["mergeType"] == "squash"

    def test_pr_close_post_empty_body(self, monkeypatch):
        """live 契约：唯一生效形态 = POST /close 空 body；PUT 详情带
        state=closed 是假阳性（result:true 但状态不变）——MR#7 实测。"""
        ad = self._ad({("POST", "/close"): {"result": True}}, monkeypatch)
        ad.pr_close(7)
        m, p, body, _q = ad.seen[0]
        assert (m, p) == ("POST", f"{ad._base()}/changeRequests/7/close")
        assert body == {}  # 空 body；PUT /changeRequests/7 假阳性形态禁用

    def test_pr_close_github_uses_gh(self, monkeypatch):
        """GitHub 侧 pr_close → gh pr close（_gh 内部按 slug 追加 --repo，
        这里只断言子命令形状）。"""
        calls = []

        def fake(_self, args, repo_override=None, stdin=None):
            calls.append(args)
            return type("R", (), {"returncode": 0, "stderr": "",
                                  "stdout": ""})()
        monkeypatch.setattr(hosting.GitHubAdapter, "_gh", fake)
        assert hosting.GitHubAdapter().pr_close(9) is True
        assert calls[0] == ["pr", "close", "9"]

    def test_pr_list_filters_state_and_label(self, monkeypatch):
        page = {"result": [
            {"localId": 1, "newVersionState": "UNDER_REVIEW",
             "labels": [{"name": "factory:needs-fix"}]},
            {"localId": 2, "newVersionState": "MERGED", "labels": []},
            {"localId": 3, "newVersionState": "TO_BE_MERGED",
             "labels": [{"name": "factory:approved"}]},
        ]}
        ad = self._ad({("GET", "/changeRequests"): page}, monkeypatch)
        prs = ad.pr_list(state="open", label=None, limit=10)
        assert [p["number"] for p in prs] == [1, 3]  # MERGED 被滤出 open 集
        only = ad.pr_list(state="open", label="factory:needs-fix", limit=10)
        assert [p["number"] for p in only] == [1]

    def test_label_link_resolves_name_to_id(self, monkeypatch):
        ad = self._ad({
            ("GET", "/labels"): {"result": [
                {"id": "lbl-9", "name": "factory:needs-review"}]},
            ("POST", "/comments/list"): {"result": []},
            # #66 标记模型：add 先发标记评论，类标 Link 为补充载体
            ("POST", "/comments"): {"success": True},
            ("POST", "/changeRequests/7/labels"): {"success": True}}, monkeypatch)
        ad.pr_set_labels(7, add=["factory:needs-review"])
        marker = [s for s in ad.seen if s[0] == "POST"
                  and s[1].endswith("/comments")][0]
        assert marker[2]["content"] == "[factory:label:add] factory:needs-review"
        assert marker[2]["resolved"] is False
        link = [s for s in ad.seen if s[0] == "POST" and "labels" in s[1]][0]
        assert link[2] == {"labelIdList": ["lbl-9"]}  # live 破案键名（labelIds 拒）

    def test_pr_create_requires_base_fail_closed(self, monkeypatch):
        """Codeup pr create 缺 --base fail-closed（web-tools#5 Sourcery）：
        targetBranch 因仓而异（master/main 均有实仓），猜默认会静默落错
        基线；显式 base 透传 targetBranch。"""
        ad = self._ad({("POST", "/changeRequests"): {
            "result": {"localId": 9, "detailUrl": "u"}}}, monkeypatch)
        with pytest.raises(hosting.HostingError) as e:
            ad.pr_create("br", "t", "b")
        assert e.value.code == 2
        assert "--base" in str(e.value)
        assert ad.pr_create("br", "t", "b", base="release/x") == {
            "number": 9, "url": "u"}
        assert ad.seen[0][2]["targetBranch"] == "release/x"

    def test_space_id_maps_path_namespace(self, monkeypatch, tmp_path):
        """namespace = remote path 首段（php#17 Sourcery）：
        gtsp/open-platform/<repo> 的中间层不是 namespace，旧 [1] 索引
        永不命中 conf 键；单段 path（无 namespace 层）fail-closed。"""
        conf = tmp_path / "spaces.conf"
        conf.write_text("gtsp|SID-1\n", encoding="utf-8")
        monkeypatch.setenv("YUNXIAO_ACCESS_TOKEN", "t")
        monkeypatch.setenv("CODEUP_ORG_ID", "org")
        monkeypatch.setenv("CODEUP_REPO_ID", "42")
        monkeypatch.setenv("FACTORY_SPACES_CONF", str(conf))
        monkeypatch.delenv("CODEUP_SPACE_ID", raising=False)
        ad = hosting.CodeupAdapter()
        ad._remote = lambda: ("610b3c9d", "gtsp/open-platform/gtsp-xx-gateway")
        assert ad._space_id() == "SID-1"
        ad._remote = lambda: ("610b3c9d", "plain-repo")
        with pytest.raises(hosting.HostingError) as e:
            ad._space_id()
        assert e.value.code == 2


class TestCodeupGaps:
    """平台缺口收敛后仍 fail-closed（exit 2）的操作集。"""

    def _ad(self, monkeypatch):
        monkeypatch.setenv("YUNXIAO_ACCESS_TOKEN", "t")
        monkeypatch.setenv("CODEUP_ORG_ID", "org")
        monkeypatch.setenv("CODEUP_REPO_ID", "42")
        ad = hosting.CodeupAdapter()
        ad._req = lambda *a, **k: {"success": True, "result": []}
        return ad

    # 缺口 (b)(c) 已由评论标记模型承载（#66）；真缺口仅剩 diff 全文
    @pytest.mark.parametrize("fn", [
        lambda ad: ad.pr_diff(2),
    ])
    def test_unsupported_ops_exit2(self, fn, monkeypatch):
        with pytest.raises(hosting.HostingError) as e:
            fn(self._ad(monkeypatch))
        assert e.value.code == 2
        assert "ADR-008" in str(e.value)


class TestCodeupMarkerModel:
    """#66 评论标记模型：add/remove 序列、label_history 轮次语义、
    changes-requested 手势映射。"""

    def _ad(self, monkeypatch, comments_by_resolved):
        """comments_by_resolved: {False: [未resolved评论], True: [已resolved评论]}
        自定义 mock 按 body['resolved'] 分流（_ad 简单路由无法区分两态）。"""
        monkeypatch.setenv("YUNXIAO_ACCESS_TOKEN", "t")
        monkeypatch.setenv("CODEUP_ORG_ID", "org")
        monkeypatch.setenv("CODEUP_REPO_ID", "42")
        ad = hosting.CodeupAdapter()
        ad.seen = []

        def fake_req(method, path, body=None, query=None, _retry_rdc=True):
            ad.seen.append((method, path, body, query))
            if method == "POST" and path.endswith("/comments/list"):
                return {"result": comments_by_resolved.get(
                    (body or {}).get("resolved"), [])}
            return {"success": True, "result": []}
        ad._req = fake_req
        return ad

    def test_remove_resolves_marker_keeps_content(self, monkeypatch):
        """remove = 置 resolved（PUT comments/{id}），内容保留——轮次不减。"""
        ad = self._ad(monkeypatch, {False: [
            {"id": "c-1", "content": "[factory:label:add] factory:needs-fix"},
            {"id": "c-2", "content": "[factory:label:add] factory:approved"}]})
        ad.pr_set_labels(7, remove=["factory:needs-fix"])
        puts = [s for s in ad.seen if s[0] == "PUT"]
        assert len(puts) == 1  # 只 resolve needs-fix，approved 不动
        assert puts[0][1].endswith("/changeRequests/7/comments/c-1")
        assert puts[0][2] == {"resolved": True}

    def test_remove_idempotent_no_marker(self, monkeypatch, capsys):
        ad = self._ad(monkeypatch, {})
        assert ad.pr_set_labels(7, remove=["x"]) is True
        assert not [s for s in ad.seen if s[0] == "PUT"]
        assert "幂等跳过" in capsys.readouterr().err

    def test_add_idempotent_existing_marker(self, monkeypatch, capsys):
        """add 幂等（php#17 Sourcery）：已有同名未 resolved 标记 → 跳过
        POST 不堆重复；类标 Link 仍 best-effort（未路由路径走 _ad 兜底
        空列表 → 降级告警，不影响 True 契约）。"""
        ad = self._ad(monkeypatch, {False: [
            {"id": "c-1", "content": "[factory:label:add] factory:needs-review"}]})
        assert ad.pr_set_labels(7, add=["factory:needs-review"]) is True
        posts = [s for s in ad.seen if s[0] == "POST"
                 and s[1].endswith("/changeRequests/7/comments")]
        assert not posts  # 未发新标记评论（幂等跳过）
        assert "幂等跳过" in capsys.readouterr().err

    def test_pr_labels_merges_two_carriers(self, monkeypatch):
        """labels = 类标 Link ∪ 未 resolved 标记（两载体合并去重）。"""
        ad = self._ad(monkeypatch, {False: [
            {"id": "c-1", "content": "[factory:label:add] factory:needs-fix"}]})

        real_req = ad._req

        def fake_req(method, path, body=None, query=None, _retry_rdc=True):
            if method == "GET" and path.endswith("/labels"):
                return [{"name": "factory:needs-fix"}, {"name": "factory:extra"},
                        {"name": "release/x"}]
            return real_req(method, path, body, query, _retry_rdc)
        ad._req = fake_req
        # 标记是真相源：factory:extra 无未 resolved 标记 → 屏蔽；
        # 非 factory 前缀类标（release/x）不受标记生命周期约束
        assert ad._pr_labels(7) == ["factory:needs-fix", "release/x"]

    def test_pr_labels_marker_failure_degrades_best_effort(self, monkeypatch, capsys):
        """Sourcery #11：评论端点失败降级空集——标签读失败不阻断 PR 详情
        （尽力而为契约；写路径 pr_set_labels 仍显式失败）。"""
        ad = self._ad(monkeypatch, {})
        real_req = ad._req

        def fake_req(method, path, body=None, query=None, _retry_rdc=True):
            if method == "GET" and path.endswith("/labels"):
                return [{"name": "factory:needs-fix"}]
            if method == "POST" and path.endswith("/comments/list"):
                raise hosting.HostingError("comments endpoint down")
            return real_req(method, path, body, query, _retry_rdc)
        ad._req = fake_req
        assert ad._pr_labels(7) == ["factory:needs-fix"]  # 类标保留，标记载体降级
        assert "降级空集" in capsys.readouterr().err

    def test_pr_view_marker_failure_keeps_review(self, monkeypatch, capsys):
        """手势载体失败：review 维持平台原生映射，pr_view 不抛、不误报。"""
        ad = self._ad(monkeypatch, {})
        real_req = ad._req

        def fake_req(method, path, body=None, query=None, _retry_rdc=True):
            if method == "GET" and path.endswith("/changeRequests/5"):
                return {"result": {"localId": 5, "newVersionState": "TO_BE_MERGED",
                                   "reviewers": [{"reviewOpinionStatus": "PASS"}]}}
            if method == "GET" and path.endswith("/labels"):
                return []
            if method == "POST" and path.endswith("/comments/list"):
                raise hosting.HostingError("comments endpoint down")
            return real_req(method, path, body, query, _retry_rdc)
        ad._req = fake_req
        out = ad.pr_view(5)
        assert out["labels"] == []
        assert out["review"] != "changes_requested"  # 载体缺席不得误报打回
        assert "降级空集" in capsys.readouterr().err

    def test_marker_label_prefix_only_returns_empty(self, monkeypatch):
        """CodeRabbit xx-skills#14：标记评论恰为前缀/前缀+空白时切片为空，
        旧实现 splitlines()[0] 抛 IndexError（平台开放输入不可约束）——
        空标记按无标记处理，不越过 HostingError 边界。"""
        ad = self._ad(monkeypatch, {})
        assert ad._marker_label("[factory:label:add] ") == ""
        assert ad._marker_label("[factory:label:add]") == ""
        # 常规形态不回归
        assert ad._marker_label(
            "[factory:label:add] factory:needs-review") == "factory:needs-review"

    def test_label_history_resolved_does_not_decrease(self, monkeypatch):
        """轮次语义：resolved 不减计数——全部 add 标记都计入事件流。"""
        ad = self._ad(monkeypatch, {
            False: [{"id": "c-2", "content": "[factory:label:add] factory:needs-fix"}],
            True: [{"id": "c-1", "content": "[factory:label:add] factory:needs-fix"}]})
        hist = ad.label_history(7)
        assert hist == [{"op": "add", "label": "factory:needs-fix"},
                        {"op": "add", "label": "factory:needs-fix"}]

    def test_label_history_skips_empty_label_markers(self, monkeypatch):
        """CodeRabbit #119：前缀-only 评论 _marker_label 返回 ""——
        label_history 不得产出 {"op": "add", "label": ""} 无效事件。"""
        ad = self._ad(monkeypatch, {False: [
            {"id": "c-3", "content": "[factory:label:add] "},
            {"id": "c-4", "content": "[factory:label:add] factory:needs-fix"}]})
        hist = ad.label_history(7)
        assert hist == [{"op": "add", "label": "factory:needs-fix"}]

    def test_label_history_ignores_changes_requested_markers(self, monkeypatch):
        """输入面守卫：#119 walrus 版若删 startswith 过滤（M2 变异），
        _marker_comments 收的 changes-requested 评论会被 _marker_label 盲切
        成垃圾 label——label_history 只认 add 前缀，changes-req 评论不产事件。"""
        ad = self._ad(monkeypatch, {False: [
            {"id": "c-5", "content": "[factory:changes-requested] 理由"},
            {"id": "c-6", "content": "[factory:label:add] factory:needs-fix"}]})
        hist = ad.label_history(7)
        assert hist == [{"op": "add", "label": "factory:needs-fix"}]

    def test_changes_requested_gesture_maps_review(self, monkeypatch):
        """[factory:changes-requested] 评论 → changes_requested（无
        reviewDecision 等价物场景）；reviewer PASS 映射不覆盖手势。"""
        ad = self._ad(monkeypatch, {False: [
            {"id": "c-9", "content": "[factory:changes-requested] 命名漂移"}]})

        real_req = ad._req

        def fake_req(method, path, body=None, query=None, _retry_rdc=True):
            if method == "GET" and path.endswith("/changeRequests/5"):
                return {"result": {"localId": 5, "newVersionState": "TO_BE_MERGED",
                                   "reviewers": [{"reviewOpinionStatus": "PASS"}]}}
            if method == "GET" and path.endswith("/labels"):
                return []
            return real_req(method, path, body, query, _retry_rdc)
        ad._req = fake_req
        n = ad.pr_view(5)
        assert n["review"] == "changes_requested"  # 手势取严于 reviewer PASS



class TestCodeupWorkItemFace:
    """#67 工作项面五方法（live 已验形态;forge 参考实现迁移）。"""

    WI_DESC = json.dumps({"htmlValue":
                           "<p>正文</p>\n<!-- factory:labels:v1: factory:accepted -->"},
                          ensure_ascii=False)
    WI = {"result": {"id": "wid1", "serialNumber": "T-18",
                     "subject": "标题", "logicalStatus": "NORMAL",
                     "description": WI_DESC,
                     "labels": None},
          "_comments": [{"author": {"name": "纪柏涛"}, "content": "<p>早</p>"}]}

    def _ad(self, monkeypatch, routes=None, env=None):
        for k, v in {**{"YUNXIAO_ACCESS_TOKEN": "t", "CODEUP_ORG_ID": "org",
                        "CODEUP_REPO_ID": "42", "CODEUP_SPACE_ID": "sp1"}, **(env or {})}.items():
            monkeypatch.setenv(k, v)
        ad = hosting.CodeupAdapter()
        ad.seen = []
        base = routes or {}
        def fake_req(method, path, body=None, query=None, _retry_rdc=True):
            ad.seen.append((method, path, body, query))
            for (m, suf), payload in base.items():
                if m == method and path.endswith(suf):
                    return payload
            if path.endswith("/comments"):
                return self.WI["_comments"]
            if path.endswith("/workitems/T-18") or path.endswith("/workitems/wid1"):
                return self.WI["result"]
            if path.endswith("/workitems:search"):
                return {"result": [self.WI["result"], {"id": "wid2", "serialNumber": "T-19",
                              "subject": "旧", "logicalStatus": "FINISHED", "description": ""}]}
            raise hosting.HostingError(f"mock 未路由: {method} {path}")

        ad._req = fake_req
        return ad

    def test_issue_view_normalizes_and_strips_marker(self, monkeypatch):
        monkeypatch.setenv("CODEUP_ISSUE_LABELS", "description")
        ad = self._ad(monkeypatch)
        n = ad.issue_view("T-18")
        assert n["number"] == "T-18" and n["state"] == "open"
        assert n["title"] == "标题"
        assert n["body"] == "正文"           # HTML 剥离 + 标记块剥离
        assert "factory:labels" not in n["body"]
        assert n["labels"] == ["factory:accepted"]  # description 载体解析
        assert n["comments"] == [{"author": "纪柏涛", "body": "早"}]

    def test_issue_view_native_labels(self, monkeypatch):
        wi = {**self.WI["result"], "labels": ["factory:rejected"], "description": ""}
        ad = self._ad(monkeypatch, routes={("GET", "/workitems/T-16"): wi})
        assert ad.issue_labels("T-16") == ["factory:rejected"]

    def test_issue_list_paginates_filters_state_and_label(self, monkeypatch):
        monkeypatch.setenv("CODEUP_ISSUE_LABELS", "description")
        ad = self._ad(monkeypatch)
        out = ad.issue_list(state="open", label="factory:accepted", limit=10)
        assert [i["number"] for i in out] == ["T-18"]  # FINISHED 滤出+label 过滤
        m, p, body, _q = ad.seen[0]
        assert (m, p.endswith("/workitems:search")) == ("POST", True)
        assert body["category"] == "Task" and body["spaceId"] == "sp1"  # category 必填（live）

    def test_issue_list_requires_space_env(self, monkeypatch):
        monkeypatch.delenv("CODEUP_SPACE_ID", raising=False)
        ad = hosting.CodeupAdapter()
        ad._req = lambda *a, **k: {}
        with pytest.raises(hosting.HostingError) as e:
            ad.issue_list()
        assert e.value.code == 2

    def test_issue_set_labels_native_put(self, monkeypatch):
        wi = {**self.WI["result"], "labels": ["keep"]}
        ad = self._ad(monkeypatch, routes={("GET", "/workitems/T-18"): wi})
        ad.issue_set_labels("T-18", add=["factory:triaging"], remove=["keep"])
        put = [s for s in ad.seen if s[0] == "PUT"][-1]
        assert put[2] == {"labels": ["factory:triaging"]}  # 排序去重

    def test_issue_set_labels_description_rw(self, monkeypatch):
        monkeypatch.setenv("CODEUP_ISSUE_LABELS", "description")
        ad = self._ad(monkeypatch)
        ad.issue_set_labels("T-18", add=["factory:in-progress"])
        put = [s for s in ad.seen if s[0] == "PUT"][-1]
        assert put[2]["formatType"] == "MARKDOWN"
        # 读-改-写保留原始载体格式（JSON 串不解包）:原 accepted 保留+新增
        # 原文字面 \n（json 转义）保留;块前是真换行（实现拼接语义）
        assert put[2]["description"] == (
            '{"htmlValue": "<p>正文</p>\\n"}'
            '\n\n<!-- factory:labels:v1: factory:accepted factory:in-progress -->')
        # 移除唯一标签 = 块消失,原文保留
        ad2 = self._ad(monkeypatch)
        ad2.issue_set_labels("T-18", remove=["factory:accepted"])
        put2 = [s for s in ad2.seen if s[0] == "PUT"][-1]
        assert put2[2]["description"] == '{"htmlValue": "<p>正文</p>\\n"}'

    def test_issue_comment_uses_id_and_marker_dedupe(self, monkeypatch, capsys):
        monkeypatch.setenv("CODEUP_ISSUE_LABELS", "description")
        ad = self._ad(monkeypatch, routes={
            ("GET", "/workitems/wid1/comments"): [
                {"author": {"name": "x"}, "content": "<p>旧<!-- m1 --></p>"}]})
        assert ad.issue_comment("T-18", "回执", marker="m1") is True  # dedupe 命中
        assert "dedupe" in capsys.readouterr().err
        posts = [s for s in ad.seen if s[0] == "POST"]
        assert not posts
        ad.issue_comment("T-18", "新评论")
        posts = [s for s in ad.seen if s[0] == "POST"]
        assert posts[-1][1].endswith("/workitems/wid1/comments")  # serialNumber→id
        assert posts[-1][2]["contentType"] == "markdown"


class TestCodeupIssueCreate:
    """issue create 实装契约（forge 实装迁移,PR #62 实测破案）:
    本体 4 必填 + customFieldValues 平面对象 + 缺 env fail-closed。"""

    ENV = {"CODEUP_SPACE_ID": "sp1", "CODEUP_WORKITEM_TYPE_ID": "wt9",
           "CODEUP_ASSIGN_USER_ID": "0123456789abcdef01234567"}

    FIELDS = {"result": [
        {"id": 1, "name": "标题", "required": True, "type": "NativeField"},
        {"id": 79, "name": "计划开始时间", "required": True, "format": "date"},
        {"id": 80, "name": "计划结束时间", "required": True, "format": "date"},
        {"id": 101586, "name": "预计工时", "required": True, "format": "float"},
        {"id": 6, "name": "优先级", "required": True,
         "options": [{"id": 11}, {"id": 22}]},
        {"id": 7, "name": "可选字段", "required": False},
    ]}

    def _ad(self, monkeypatch, fields=None, create_resp=None,
            detail_resp=None, fail_fields=False, fail_detail=False):
        for k, v in {**{"YUNXIAO_ACCESS_TOKEN": "t", "CODEUP_ORG_ID": "org",
                        "CODEUP_REPO_ID": "42"}, **self.ENV}.items():
            monkeypatch.setenv(k, v)
        ad = hosting.CodeupAdapter()
        calls = []

        def fake_req(method, path, body=None, query=None, _retry_rdc=True):
            calls.append((method, path, body))
            if "workitemTypes" in path:  # 字段配置发现端点
                if fail_fields:
                    raise hosting.HostingError("codeup GET fields HTTP 404: x")
                return fields if fields is not None else self.FIELDS
            # 【live 2026-08-26】create 响应只含 24-hex id（无 serialNumber/
            # detailUrl）——T-21 实测；详情回查才有可读编号
            if method == "POST" and path.endswith("/workitems"):
                return create_resp or {"result": {"id": "wid123"}}
            if fail_detail:
                raise hosting.HostingError("codeup GET detail HTTP 500: x")
            return detail_resp or {"result": {"serialNumber": "T-42",
                                              "detailUrl": "https://x/T-42"}}

        ad._req = fake_req
        return ad, calls

    def test_missing_env_fail_closed(self, monkeypatch):
        monkeypatch.setenv("YUNXIAO_ACCESS_TOKEN", "t")
        monkeypatch.setenv("CODEUP_ORG_ID", "org")
        monkeypatch.delenv("CODEUP_SPACE_ID", raising=False)
        ad = hosting.CodeupAdapter()
        with pytest.raises(hosting.HostingError) as e:
            ad.issue_create("t", "b")
        assert e.value.code == 2
        assert "CODEUP_SPACE_ID" in str(e.value)

    def test_create_payload_shape(self, monkeypatch):
        ad, calls = self._ad(monkeypatch)
        out = ad.issue_create("标题", "正文", label="factory:triaging")
        posts = [c for c in calls if c[0] == "POST" and c[1].endswith("/workitems")]
        m, path, body = posts[-1]  # 回查 GET 在 POST 后,calls[-1] 已非 POST
        assert (m, path) == ("POST", "/oapi/v1/projex/organizations/org/workitems")
        assert body["spaceId"] == "sp1" and body["workitemTypeId"] == "wt9"
        assert body["subject"] == "标题"
        assert body["assignedTo"] == "0123456789abcdef01234567"
        # label 载体 = description 尾部 HTML 注释块（云效 Task 常无 labels
        # 字段，ADR-007 实测；PR #64 审查 F1 修复）
        assert body["description"].startswith("正文")
        assert "<!-- factory:labels:v1: factory:triaging -->" in body["description"]
        assert "labels" not in body  # 不再直写 labels 字段（真实平台 400）
        cfvs = body["customFieldValues"]
        # 平面对象 {"fieldId": "value"}（数组形态 = Invalid format 实测）
        assert isinstance(cfvs, dict)
        assert cfvs["79"].endswith("-") or len(cfvs["79"]) == 10  # date ISO
        assert cfvs["101586"] == "0.5"  # float=小数字符串
        assert cfvs["6"] == "22"  # list=末档 option id（str）
        assert 1 not in cfvs and "1" not in cfvs  # NativeField 走本体
        assert 7 not in cfvs and "7" not in cfvs  # 非 required 不带
        assert out == {"number": "T-42", "url": "https://x/T-42"}

    def test_fields_fetch_failure_degrades_with_warning(self, monkeypatch, capsys):
        ad, calls = self._ad(monkeypatch, fail_fields=True)
        out = ad.issue_create("t", "b")
        assert "warn" in capsys.readouterr().err  # 降级可见不静默
        posts = [c for c in calls if c[0] == "POST" and c[1].endswith("/workitems")]
        assert posts and "customFieldValues" not in posts[-1][2]  # POST 仍发出
        assert out["number"] == "T-42"

    def test_create_returns_serial_via_detail_lookup(self, monkeypatch):
        """live 契约：create 响应仅 24-hex id；serialNumber 由详情回查取得。"""
        ad, calls = self._ad(monkeypatch)
        out = ad.issue_create("t", "b")
        gets = [(m, p) for m, p, _b in calls if m == "GET"]
        assert any(p.endswith("/workitems/wid123") for _m, p in gets), \
            "必须回查详情端点"
        assert out == {"number": "T-42", "url": "https://x/T-42"}

    def test_detail_lookup_failure_degrades_to_id(self, monkeypatch, capsys):
        """回查失败降级返回 id + stderr 告警（可读性损失可见，不阻断）。"""
        ad, _calls = self._ad(monkeypatch, fail_detail=True)
        out = ad.issue_create("t", "b")
        assert out["number"] == "wid123"
        assert "serialNumber" in capsys.readouterr().err

    def test_create_resp_with_serial_still_wins(self, monkeypatch):
        """若平台未来在 create 响应补 serialNumber：有 id 仍回查（详情
        是 detailUrl 权威源）；无 id 才直取响应字段。"""
        ad, _calls = self._ad(
            monkeypatch, create_resp={"result": {"serialNumber": "T-9"}})
        out = ad.issue_create("t", "b")
        # create 无 id → 不回查，直接响应字段
        assert out["number"] == "T-9"


class TestCodeupEndpointFallback:
    """【实测】默认端点受限网络 TLS 静默丢弃 → 中心版端点一次重试。"""

    def test_urLError_retries_rdc(self, monkeypatch):
        ad = hosting.CodeupAdapter()
        calls = []

        class _Err(Exception):
            pass

        import urllib.error as ue
        monkeypatch.setattr(
            hosting.urllib.request,
            "urlopen",
            lambda req, timeout=None: _raise(ue.URLError("tls dropped")),
        )
        monkeypatch.setenv("YUNXIAO_ACCESS_TOKEN", "t")
        monkeypatch.setenv("CODEUP_ORG_ID", "org")
        monkeypatch.setenv("CODEUP_REPO_ID", "42")
        with pytest.raises(hosting.HostingError) as e:
            ad._req("GET", "/oapi/v1/codeup/organizations/org/repositories/42")
        # 两次都失败才报错；且报错信息指向重试后的端点
        assert re.search(r"openapi-rdc\.aliyuncs\.com", str(e.value))  # codeql[py/incomplete-url-substring-sanitization] ADR-GH1: 断言消息含端点 (regex 形式脱离子串校验 sink 模式), 非 URL 安全校验


class TestCli:
    def test_codeup_issue_view_cli_fails_closed(self, tmp_path):
        """#67 后 issue view 已实装：CLI 边界=无凭据/网络失败 fail-closed
        非零（假 token → 401 → HostingError），不再是无条件 unsupported。"""
        r = subprocess.run(
            [sys.executable, str(Path(hosting.__file__).resolve()),
             "issue", "view", "1"],
            capture_output=True, text=True,
            env={"FACTORY_HOSTING": "codeup", "PATH": "/usr/bin:/bin",
                 "YUNXIAO_ACCESS_TOKEN": "t", "CODEUP_ORG_ID": "o",
                 "CODEUP_REPO_ID": "1"})
        assert r.returncode != 0          # 401 fail-closed（无真凭据环境）
        assert "hosting" in r.stderr or "codeup" in r.stderr

    def test_platform_select_unknown(self):
        with pytest.raises(hosting.HostingError) as e:
            hosting.FACTORY_HOSTING = "gitlab"
            try:
                hosting.current_adapter()
            finally:
                hosting.FACTORY_HOSTING = "github"
        assert e.value.code == 2

    def test_platform_select_unknown_cli_exit2(self, monkeypatch):
        """PR #64 Sourcery：ad=current_adapter() 移入 try 后，未知
        FACTORY_HOSTING 经 CLI 主入口必须 rc=2（fail-closed），
        不再是裸 traceback + Python 通用 rc=1。"""
        import subprocess, sys
        monkeypatch.setenv("FACTORY_HOSTING", "gitlab")
        r = subprocess.run(
            [sys.executable, str(hosting.__file__ or ".factory/hosting.py"), "auth"],
            capture_output=True, text=True, timeout=15)
        assert r.returncode == 2, (r.returncode, r.stderr[-200:])

    def test_req_malformed_json_fail_closed(self, monkeypatch):
        """PR #64 Sourcery：200 + 畸形体必须转 HostingError（exit 2 域），
        裸 JSONDecodeError 不逃出适配器边界。"""
        import io

        class _BadResp:
            def read(self):
                return b"{not-json"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        monkeypatch.setenv("CODEUP_ORG_ID", "org")
        monkeypatch.setenv("CODEUP_REPO_ID", "42")
        # 凭据值非被测语义（被测 = 200+畸形体 fail-closed）：_req 首行
        # _cfg() 读 token，无凭据环境（CI/净克隆）缺此 mock 必红——
        # 2026-08-27 实证其污染 mutations B-106 负例（rc=1 假击杀）。
        monkeypatch.setenv("YUNXIAO_ACCESS_TOKEN", "test-token")
        ad = hosting.CodeupAdapter.__new__(hosting.CodeupAdapter)
        ad._endpoint = "openapi-rdc.aliyuncs.com"
        monkeypatch.setattr(
            hosting.urllib.request, "urlopen",
            lambda req, timeout: _BadResp())
        with pytest.raises(hosting.HostingError) as e:
            ad._req("GET", "/x")
        assert "响应格式错误" in str(e.value)

    def test_issue_comments_author_neutral_string(self):
        """PR #64 Sourcery：中立 schema author 是字符串；分流提示词
        格式化不得 c["author"]["login"]（TypeError）。fix-issue.sh
        内联 python 的等价形态回归（与 triage-batch.sh 同款）。"""
        cs = [{"author": "someone", "body": "hi"},
              {"body": "no-author-entry"}]
        out = "\n\n".join(
            "[作者: %s]\n%s" % (c.get("author") or "?", c["body"])
            for c in cs[-3:])
        assert "[作者: someone]" in out
        assert "[作者: ?]" in out  # 缺 author 不炸


class TestIssueCreateAcceptanceGate:
    """issue create 验收明确性预检（#104/#109 triage 对比观察落地：
    创建时拦截无验收载体的正文，比 triage 判据 b 打回省一轮往返）。

    缺陷→测试映射：
    - #104 形态（描述+建议、无验收载体）拦 → test_rejects_104_style_body
    - #109 形态（验收判据节+checkbox）过 → test_accepts_109_style_body
    - 空/空白/None body 拦 → test_rejects_empty_body
    - 仅「验收/acceptance」节（机器模板形态）过
      → test_accepts_acceptance_heading
    - CLI 端到端：预检失败 exit 2 且先于平台触达
      → test_cli_gate_fails_closed
    """

    BODY_104 = ("## 问题\nsync 分发缺 CODEOWNERS 三态管理。\n\n"
                "## 建议方向\n补入 DISTRIBUTION.json。")
    BODY_109 = ("## 根因\n宿主环境渗漏两陷阱。\n\n## 验收判据\n\n"
                "- [ ] 完整 PATH 全套件绿\n"
                "- [ ] 无 homebrew PATH 全套件绿\n"
                "- [ ] 全程无出网\n"
                "- [ ] 301 零回归")

    def test_accepts_109_style_body(self):
        assert hosting._issue_acceptance_error(self.BODY_109) is None

    def test_rejects_104_style_body(self):
        err = hosting._issue_acceptance_error(self.BODY_104)
        assert err is not None
        assert "验收" in err

    def test_rejects_empty_body(self):
        assert hosting._issue_acceptance_error("") is not None
        assert hosting._issue_acceptance_error("   ") is not None
        assert hosting._issue_acceptance_error(None) is not None

    def test_accepts_acceptance_heading(self):
        # 机器模板形态：验收节存在即可（节内判定语句由模板补全）
        body = ("## 现象\n上游 local 面漂移。\n\n"
                "## Acceptance Criteria\n--check 不再报分叉即完成。")
        assert hosting._issue_acceptance_error(body) is None

    def test_cli_gate_fails_closed(self, capsys):
        # 端到端：预检失败 → exit 2 + stderr 提示，先于任何平台触达
        with pytest.raises(SystemExit) as e:
            hosting.main(["issue", "create", "--title", "t",
                          "--body", self.BODY_104])
        assert e.value.code == 2
        assert "预检未过" in capsys.readouterr().err



class TestIssueCreateLabelGate:
    """issue create 标签合法性预检（第三层：factory: 命名空间保留）。

    语义 = factory:* 命名空间属状态机/门控（regression/README.md：「打
    其他 factory:* 标签会永远不被拾取」）。命名空间拦截 fail-closed：
    typo 与新增状态标签自动被拦，不依赖枚举镜像。豁免 needs-human
    （机器「不可自动」合法落点，upstream-sync 实证）；非 factory 标签
    （priority:* dispatch 消费面）放行。

    缺陷→测试映射：
    - needs-human 过（机器实证用法）→ test_allows_needs_human
    - 8 个状态机保留标签拦 → test_blocks_state_machine_labels
    - typo / PR 门控产物（validated 族）拦 → test_blocks_unknown_factory_labels
    - 非 factory 标签/空放行 → test_allows_non_factory_and_empty
    - 命名空间覆盖 state 全部状态标签（防脱节）→ test_state_labels_covered_by_namespace
    - CLI 端到端：非法标签 exit 2 且先于平台触达 → test_cli_gate_fails_closed
    """

    def test_allows_needs_human(self):
        assert hosting._issue_label_error("factory:needs-human") is None

    def test_blocks_state_machine_labels(self):
        for label in ("factory:triaging", "factory:in-progress",
                      "factory:accepted", "factory:needs-review",
                      "factory:needs-fix", "factory:approved",
                      "factory:rejected", "factory:in-review"):
            err = hosting._issue_label_error(label)
            assert err is not None, label
            assert "factory: 命名空间" in err, label

    def test_blocks_unknown_factory_labels(self):
        # fail-closed：typo 与非状态机 factory 标签（PR 门控产物）
        # 同拦——枚举黑名单会放行这些（advisory 指出的缺口）
        for label in ("factory:accepetd",       # typo
                      "factory:validated",      # validate-pr 门控产物
                      "factory:validation-failed"):
            assert hosting._issue_label_error(label) is not None, label

    def test_allows_non_factory_and_empty(self):
        assert hosting._issue_label_error("priority:critical") is None
        assert hosting._issue_label_error("bug") is None
        assert hosting._issue_label_error(None) is None
        assert hosting._issue_label_error("") is None

    def test_state_labels_covered_by_namespace(self):
        # 单一来源锁：state.py 全部状态标签（三集合+裁决/接管态）落在
        # 命名空间拦截内（needs-human 豁免除外）——命名空间断言与
        # 状态机实际定义不脱节
        import state
        for label in (state.LOCKS | state.QUEUE | state.PR_SIDE
                      | {"factory:rejected", "factory:in-review"}):
            if label == "factory:needs-human":
                assert hosting._issue_label_error(label) is None
            else:
                assert hosting._issue_label_error(label) is not None, label

    def test_cli_gate_fails_closed(self, capsys):
        # 端到端：body 先过第二层（含验收节），第三层拦非法标签 → exit 2
        with pytest.raises(SystemExit) as e:
            hosting.main(["issue", "create", "--title", "t", "--body",
                          "## 验收\n- [ ] x", "--label", "factory:accepted"])
        assert e.value.code == 2
        assert "预检未过" in capsys.readouterr().err

class TestRepoSplitRouting:
    """CodeRabbit D：--repo 双语义拆分（_repo_split）——目录形态（java#29
    跨仓调用：平台检测用目录真实路径、slug 由该目录 remote 自解析）vs
    owner/repo slug 形态（检测回退 "."、slug 原样进 ops）。拆分点是
    「按 cwd 检测选错适配器」与「目录路径误当 slug 进 gh --repo」的
    共同单点。"""

    def test_split_three_shapes(self, tmp_path):
        d = str(tmp_path)
        assert hosting._repo_split(d) == (d, None)
        assert hosting._repo_split("up/stream") == (".", "up/stream")
        assert hosting._repo_split(None) == (".", None)

    def test_main_slug_repo_detects_dot_passes_slug(self, monkeypatch):
        """slug 形态：平台检测落在 cwd（"."）；pr view 的 --repo 原样
        进 ops（gh --repo up/stream 语义）。"""
        seen = {}

        class _Ad:
            def pr_view(self, p, repo=None):
                seen["repo"] = repo
                return {"number": 1}

        monkeypatch.setattr(hosting, "current_adapter", lambda local: (
            seen.__setitem__("local", local) or _Ad()))
        hosting.main(["pr", "view", "1", "--repo", "up/stream"])
        assert seen == {"local": ".", "repo": "up/stream"}

    def test_main_dir_repo_detects_dir_ops_none(self, monkeypatch, tmp_path):
        """目录形态：检测用目录真实路径（远端解析/平台选择以其为准）；
        ops 收 repo=None——目录路径绝不进 gh --repo。"""
        seen = {}
        d = str(tmp_path)

        class _Ad:
            def pr_view(self, p, repo=None):
                seen["repo"] = repo
                return {"number": 1}

        monkeypatch.setattr(hosting, "current_adapter", lambda local: (
            seen.__setitem__("local", local) or _Ad()))
        hosting.main(["pr", "view", "1", "--repo", d])
        assert seen == {"local": d, "repo": None}


class TestLabelAddCrossProcessLock:
    """CodeRabbit C：add「预检+POST」跨进程互斥（_add_label_lock）——
    mkdir 原子占锁 + pid 活性判死接管 + 无 pid 残锁年龄宽限 + 有界等锁
    fail-closed。缺陷：双进程同仓同 PR 同名 add 各过预检再各 POST =
    双未 resolved 标记（状态机重复转移）；锁内重预检幂等收敛恰一次
    POST。"""

    def test_active_owner_timeout_fail_closed(self, monkeypatch, tmp_path):
        """活主持锁 → 等锁超时 HostingError code=1（fail-closed 拒双
        写）：不排队不静默放行，宁可链失败重试（重试幂等收敛）。"""
        monkeypatch.setenv("FACTORY_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(hosting, "_LABEL_LOCK_TIMEOUT", 0.2)
        ad = hosting.CodeupAdapter()
        lock_dir = hosting._label_lock_dir(".", 7, "factory:needs-review")
        os.makedirs(lock_dir)
        Path(lock_dir, "pid").write_text(str(os.getpid()), encoding="ascii")
        with pytest.raises(hosting.HostingError) as e:
            with ad._add_label_lock(7, "factory:needs-review"):
                pass
        assert e.value.code == 1
        assert "fail-closed" in str(e.value)

    def test_dead_owner_lock_taken_over(self, monkeypatch, tmp_path):
        """死者残锁（pid 活性判死）→ 清后接管：with 正常进入、退出清
        目录——残锁不永久卡链（需人工清锁即锁故障）。"""
        monkeypatch.setenv("FACTORY_LOCK_DIR", str(tmp_path))
        ad = hosting.CodeupAdapter()
        lock_dir = hosting._label_lock_dir(".", 7, "factory:needs-fix")
        os.makedirs(lock_dir)
        Path(lock_dir, "pid").write_text("99999999", encoding="ascii")
        assert hosting._lock_stale(lock_dir, "99999999") is True
        with ad._add_label_lock(7, "factory:needs-fix"):
            assert os.path.isdir(lock_dir)  # 持锁期间在位
        assert not os.path.isdir(lock_dir)  # 退出清理

    def test_pidless_crash_dir_reclaimed_after_grace(self, monkeypatch, tmp_path):
        """建锁→写 pid 的崩溃窗残锁（无 pid）：年龄超宽限才判死可接管，
        宽限内按活等（不抢正在建锁的活主）；宽限 0 即刻接管。"""
        monkeypatch.setenv("FACTORY_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(hosting, "_LABEL_LOCK_STALE_GRACE", 0.0)
        ad = hosting.CodeupAdapter()
        lock_dir = hosting._label_lock_dir(".", 7, "factory:approved")
        os.makedirs(lock_dir)  # 无 pid：崩溃窗形态
        with ad._add_label_lock(7, "factory:approved"):
            assert os.path.isdir(lock_dir)
        assert not os.path.isdir(lock_dir)

    def test_parallel_add_posts_exactly_once(self, monkeypatch, tmp_path):
        """并发回归（核心契约）：两独立适配器实例（双进程/双链形态）
        同仓同 PR 同名 add 并发——锁串行化 + 后到者锁内重预检幂等跳过，
        POST comments 恰一次；无锁实现此处必双 POST。"""
        monkeypatch.setenv("FACTORY_LOCK_DIR", str(tmp_path))
        # CI 无 YUNXIAO_ACCESS_TOKEN：pr_set_labels 入口校验先于 _req stub 生效
        monkeypatch.setenv("YUNXIAO_ACCESS_TOKEN", "t")
        markers = []
        posts = []
        barrier = threading.Barrier(2)

        def make_ad():
            ad = hosting.CodeupAdapter()

            def fake_req(method, path, body=None, query=None,
                         _retry_rdc=True):
                if method == "POST" and path.endswith("/comments/list"):
                    return {"result": [
                        {"id": f"c-{i}", "content": c}
                        for i, c in enumerate(markers)]}
                if method == "POST" and path.endswith("/changeRequests/7/comments"):
                    posts.append(body["content"])
                    markers.append(body["content"])
                    time.sleep(0.05)  # 放大持锁窗：后到线程必撞上等锁
                    return {"success": True}
                return {"success": True, "result": []}  # 类标 Link 兜底
            ad._req = fake_req
            return ad

        results = []

        def worker():
            try:
                barrier.wait()
                make_ad().pr_set_labels(7, add=["factory:needs-review"])
                results.append("ok")
            except Exception as exc:  # 子线程异常收敛进结果，不裸抛
                results.append(repr(exc))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results == ["ok", "ok"]
        assert len(posts) == 1
        assert len(markers) == 1
    def test_huge_garbage_pid_waits_then_fail_closed(self, monkeypatch,
                                                     tmp_path):
        """pid 内容超 C int 巨值（损坏写，审查 P3）：按活等不误清、不裸
        traceback（OverflowError 穿透即破坏 fail-closed docstring 契约），
        等锁超时抛 code=1。"""
        monkeypatch.setenv("FACTORY_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(hosting, "_LABEL_LOCK_TIMEOUT", 0.2)
        ad = hosting.CodeupAdapter()
        lock_dir = hosting._label_lock_dir(".", 7, "factory:needs-human")
        os.makedirs(lock_dir)
        Path(lock_dir, "pid").write_text("100000000000000000000",
                                         encoding="ascii")
        owner = hosting._lock_owner(lock_dir)
        assert hosting._lock_stale(lock_dir, owner) is False  # 按活等
        with pytest.raises(hosting.HostingError) as e:
            with ad._add_label_lock(7, "factory:needs-human"):
                pass
        assert e.value.code == 1
