#!/usr/bin/env python3
"""hosting.py — 托管平台抽象层（ADR-008）：核心逻辑与 GitHub/Codeup 解耦。

设计（对齐 MISSION 铁律 4：零 LLM、确定性）：
- 中立契约唯一：核心脚本/状态机只认本模块的中立 schema 与 op 集，
  平台差异（gh CLI vs 云效 OpenAPI、reviewDecision vs reviewOpinionStatus、
  issue vs Projex 工作项）收敛在适配器内。
- 中立 schema v1（stdout JSON；factory-state.sh/state.py/factory_lib.py 消费）：
    issue = {"number": int, "state": "open"|"closed", "title": str, "body": str,
             "labels": [str], "comments": [{"author": str, "body": str}]}
    pr    = {"number": int, "state": "open"|"closed"|"merged",
             "review": "pending"|"approved"|"changes_requested",
             "mergeable": bool|null, "labels": [str],
             "title": str, "body": str, "head": str, "base": str}
    label_history = [{"op": "add"|"remove", "label": str}]
- 原子性：issue/pr set-labels 的 add+remove 在支持单请求换标的平台
  （GitHub）合并为一次调用——半途断裂=双标签或裸奔（factory-lib.sh 语义）。
- 平台选择：FACTORY_HOSTING 显式设置优先；未设置按 origin remote 检测
  （codeup.aliyun.com → codeup，github.com/无 remote → github 历史默认）。
- 退出码：0 成功；1 平台操作失败；2 用法/配置/平台能力缺口（fail-closed，
  绝不静默降级——降级等于状态机半转移）。
- 层级契约：本模块是**传输层**。issue 评论/标签副作用的唯一出口是
  factory-lib.sh 的 issue_comment()/issue_label_swap()（sanitize 与租约
  围栏在出口统一管）；链/批次脚本不得绕过 factory-lib 直调本模块写
  issue 副作用（tools/check_hosting_exit.py 机械化盯防）。issue/pr 的
  **创建**与 PR 侧写不在该收口范围（S3/M2 流程无 issue 租约上下文，
  PR 标签漂移由 factory-state.sh sync 兜底收敛）。

Codeup 能力边界（ADR-008 证据，勿删）：
- 【实测】MR 评论端点（org 级 changeRequests + comment_type/resolved 必填）
  ——本仓 skills/alibabacloud-devops 生产沉淀。
- 【文档推导】其余 MR 端点按 oapi/v1 org 级模式推导，未经 live 验证
  （本仓无云效凭据环境），请求形状由 tests/test_hosting.py mock 锁定。
- 【实测破案 PR #62】issue create 可用:create 本体必填仅 assignedTo/
  spaceId/subject/workitemTypeId;模板层 SystemCustomField 经
  customFieldValues 平面对象 {"fieldId":"value"} 传,fieldId 从字段配置
  端点发现,assignedTo=24-hex 用户 id(env CODEUP_ASSIGN_USER_ID)。
  工作项读/写面（view/list/set-labels/comment）仍未实装——链状态机
  依赖 PR 侧标签/事件史,缺口 (b)(c) 未解。
- 【平台缺口】(b) MR 类标无 Unlink 端点 → set-labels --remove 不可表达；
  (c) 无标签事件时间线 → label history 不可表达。fail-closed exit 2。

CLI（bash 侧调用面；py 侧 import current_adapter）：
  hosting.py auth ok
  hosting.py label ensure <name> <color> <desc>
  hosting.py label history <pr>
  hosting.py issue view <n>
  hosting.py issue get-labels <n>
  hosting.py issue list [--state open|all] [--label L] [--limit N] [--comments]
  hosting.py issue set-labels <n> [--add CSV] [--remove CSV]
  hosting.py issue comment <n> (--body S | --body-file F) [--marker M]
  hosting.py issue create --title T (--body S | --body-file F) [--label L] [--repo R]
  hosting.py pr view <p> [--repo R]
  hosting.py pr list [--state open|all] [--label L] [--limit N] [--repo R]
  hosting.py pr set-labels <p> [--add CSV] [--remove CSV]
  hosting.py pr create --head B --title T (--body S | --body-file F)
                       [--label L] [--base B] [--repo R]
  hosting.py pr comment <p> (--body S | --body-file F)
  hosting.py pr diff <p> [--name-only]
  hosting.py pr merge <p> --method merge|squash|rebase
"""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

FACTORY_HOSTING = os.environ.get("FACTORY_HOSTING")


class HostingError(Exception):
    """op 失败（exit 1）或平台能力缺口/配置错误（exit 2）。"""

    def __init__(self, msg, code=1):
        super().__init__(msg)
        self.code = code


# ---------------------------------------------------------------------------
# Codeup add「预检+POST」的跨进程互斥（PR #116 CodeRabbit）：锁原语与工厂
# 调度锁同语义（mkdir 原子 + pid 活性判死接管），但锚点不同——hosting CLI
# 常跨 cwd/worktree 调用，无统一仓内锚点，锁根取机器级临时目录
# （FACTORY_LOCK_DIR 显式覆盖：测试隔离/多租户）。互斥对象=同仓
# (adapter.repo 视角)同 PR 同名 add 的双进程写；粒度偏粗无害
# （串行化而非错误化）。
# ---------------------------------------------------------------------------

_LABEL_LOCK_TIMEOUT = 5.0      # 等锁最久；超时 fail-closed（code=1）拒放行双写
_LABEL_LOCK_STALE_GRACE = 2.0  # 无 pid 残锁的年龄宽限（建锁→写 pid 的崩溃窗）


def _label_lock_root() -> str:
    """add 互斥锁根：FACTORY_LOCK_DIR 显式（测试隔离）→ 系统临时目录
    （跨进程共享——传输层锁须机器级可见；与工厂调度锁的主树锚点两域不重叠）。"""
    return os.environ.get("FACTORY_LOCK_DIR") or os.path.join(
        tempfile.gettempdir(), "factory-hosting-locks")


def _pid_alive(pid: int) -> bool:
    """pid 活性（kill(pid, 0) 语义）：EPERM=进程存在按活；内容异常
    （垃圾/超 C int）不可判定 → 保守按活（等锁超时 fail-closed，不误清）。"""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, ValueError, OverflowError):
        return True
        # 等锁超时 fail-closed（code=1）也不误清可能活着的持锁主


def _lock_owner(lock_dir: str) -> str:
    """锁内 pid 文件内容；无/读失败 → ""（建锁与写 pid 之间的崩溃窗形态）。"""
    try:
        with open(os.path.join(lock_dir, "pid"), encoding="ascii") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _lock_stale(lock_dir: str, owner: str) -> bool:
    """死者残锁判定：有 pid 且进程已死 → 可接管；pid 内容异常按活等
    （宁可等超时 fail-closed，不清活主）；无 pid → 目录年龄超宽限判死
    （崩溃残锁可清；活主写 pid 在微秒级，不可能越过宽限）。"""
    if owner:
        try:
            pid = int(owner)
        except ValueError:
            return False
        return not _pid_alive(pid)
    try:
        return time.time() - os.stat(lock_dir).st_mtime > _LABEL_LOCK_STALE_GRACE
    except OSError:
        return False  # 目录已被他人清掉：外层重试 mkdir 收敛


def _label_lock_dir(repo: str, p: int, name: str) -> str:
    """同名 add 的互斥锁目录：sha1(repo|p|name) 折叠——repo/name 来自外部
    输入，目录名不得含不可信路径字符。"""
    h = hashlib.sha1(f"{repo}|{p}|{name}".encode()).hexdigest()[:16]
    return os.path.join(_label_lock_root(), h)


# ---------------------------------------------------------------------------
# GitHub slug 解析（自 factory_lib.py 迁入——平台选择逻辑归本层，
# 核心脚本不再各自扫 remote）
# ---------------------------------------------------------------------------

# 主机白名单基础面 = github 双域名；bot ssh Host 别名等机器特定主机走
# FACTORY_SLUG_EXTRA_HOSTS（逗号分隔）注入（ADR-012：公开仓零内部标识，
# 配置数据化 env 两级回退——与 PR #61 平台配置同模式）。token 严格校验
# [A-Za-z0-9_.-]+（进 regex 交替支，防注入），坏配置 fail-closed 抛错
# 而非静默降级。缓存按 env 值键控：同进程 env 不变零重编译
_SLUG_HOST_ENV = "FACTORY_SLUG_EXTRA_HOSTS"
_slug_re_cache = (None, None)


def _slug_re():
    env = os.environ.get(_SLUG_HOST_ENV, "")
    if _slug_re_cache[0] == env:
        return _slug_re_cache[1]
    hosts = "github\\.com|ssh\\.github\\.com"
    if env.strip():
        toks = [t.strip() for t in env.split(",") if t.strip()]
        for t in toks:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", t):
                raise ValueError(
                    f"{_SLUG_HOST_ENV} 含非法主机名: {t!r}"
                    "（仅允许 [A-Za-z0-9_.-]）")
        hosts += "|" + "|".join(re.escape(t) for t in toks)
    cre = re.compile(
        rf"^(?:[A-Za-z0-9_.-]+@)?(?:{hosts})(?::\d+)?[/:]"
        r"(?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$")
    globals()["_slug_re_cache"] = (env, cre)
    return cre
_SLUG_VALID = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def extract_slug(urls):
    """remote URL 清单 → GitHub slug。首条 github.com 者胜出（github remote
    名优先由调用方注入顺序保证）；主机锚定防伪装（CodeQL 同源），产出再过
    owner/repo 白名单双闸。GH_REPO 显式指定不经此函数。"""
    for u in urls:
        t = re.sub(r"^(?:ssh|git|https?)://", "", (u or "").strip())
        m = _slug_re().match(t)
        if m and _SLUG_VALID.fullmatch(m.group("slug")):
            return m.group("slug")
    return ""


def _git_remote_urls(repo):
    urls = []
    for remote in ("github", "origin"):
        r = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "--all", "--push", remote],
            capture_output=True, text=True)
        urls += [ln for ln in r.stdout.splitlines() if ln.strip()]
    return urls


def resolve_repo_slug(repo):
    """GH_REPO 显式指定优先；否则双 remote 布局逐条扫（github remote 名优先，
    origin push 兜底；443 端口形态兼容——双仓镜像布局实证）。"""
    if os.environ.get("GH_REPO"):
        return os.environ["GH_REPO"]
    return extract_slug(_git_remote_urls(repo))


# ---------------------------------------------------------------------------
# GitHub 适配器
# ---------------------------------------------------------------------------

_GH_STATE = {"OPEN": "open", "CLOSED": "closed", "MERGED": "merged"}
_GH_REVIEW = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes_requested"}


class GitHubAdapter:
    name = "github"

    def __init__(self, repo="."):
        self.repo = repo
        self._slug = None

    def slug(self, override=None):
        if override:
            return override
        if self._slug is None:
            self._slug = resolve_repo_slug(self.repo)
        return self._slug

    def _gh(self, args, repo_override=None, stdin=None):
        slug = self.slug(repo_override)
        if not slug:
            raise HostingError(
                "无法确定 GitHub 仓库 slug（GH_REPO 或 github remote）", code=2)
        cmd = ["gh", *args]
        # 只对语义上指向仓库的子命令追加 --repo（auth status 等全局命令不追加）
        if args and args[0] in ("issue", "pr", "label", "api"):
            cmd += ["--repo", slug]
        return subprocess.run(cmd, capture_output=True, text=True, input=stdin)

    def _gh_json(self, args, repo_override=None):
        r = self._gh(args, repo_override)
        if r.returncode != 0:
            raise HostingError(f"gh {' '.join(args)} 失败: {r.stderr.strip()[:300]}")
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError as e:
            raise HostingError(f"gh {' '.join(args)} 输出非 JSON（网络截断/stub）") from e

    # -- 归一化 --
    @staticmethod
    def _issue(d):
        return {"number": d.get("number"), "state": _GH_STATE.get(d.get("state"), "open"),
                "title": d.get("title") or "", "body": d.get("body") or "",
                # updatedAt ISO8601（缺省 None）：dispatch-liveness rejected
                # 滞留阈值用；非 gh 后端无此字段则该项检测自动跳过
                "updatedAt": d.get("updatedAt"),
                "labels": [l["name"] for l in d.get("labels") or []],
                "comments": [{"author": (c.get("author") or {}).get("login") or "",
                              "body": c.get("body") or ""}
                             for c in d.get("comments") or []]}

    @staticmethod
    def _pr(d):
        return {"number": d.get("number"), "state": _GH_STATE.get(d.get("state"), "open"),
                "review": _GH_REVIEW.get(d.get("reviewDecision"), "pending"),
                "mergeable": (True if d.get("mergeable") == "MERGEABLE"
                              else False if d.get("mergeable") == "CONFLICTING" else None),
                "labels": [l["name"] for l in d.get("labels") or []],
                "title": d.get("title") or "", "body": d.get("body") or "",
                "head": d.get("headRefName") or "", "base": d.get("baseRefName") or ""}

    # -- ops --
    def auth_ok(self):
        try:
            r = subprocess.run(["gh", "auth", "status"],
                               capture_output=True, text=True)
        except FileNotFoundError:
            return False  # gh CLI 不在 PATH（环境缺失，非凭据问题）
        return r.returncode == 0

    def auth_diagnose(self) -> str:
        """auth_ok 失败的留痕诊断：返回 gh auth status 的 stderr（非空时，否则 stdout），并去除首尾空白。

        【2026-09-05 02:00 6 仓瞬断事故（内部 SDK 仓）】auth_ok 只回布尔，失败
        stderr 被丢弃 → 事后无法回溯是 keyring/网络/过期哪种。dispatch
        preflight 失败路径调用，输出附着 dispatch 日志（同 bare 事故的
        诊断附着模式）。"""
        try:
            r = subprocess.run(["gh", "auth", "status"],
                               capture_output=True, text=True)
        except FileNotFoundError:
            return "gh CLI 不在 PATH（auth_ok 同因失败）"
        return (r.stderr if r.stderr.strip() else r.stdout).strip()

    def issue_view(self, n, repo=None):
        return self._issue(self._gh_json(
            ["issue", "view", str(n),
             "--json", "number,state,title,body,labels,comments"], repo))

    def issue_labels(self, n, repo=None):
        d = self._gh_json(["issue", "view", str(n), "--json", "labels"], repo)
        return [l["name"] for l in d.get("labels") or []]

    def issue_list(self, state="open", label=None, limit=100,
                   comments=False, repo=None):
        fields = "number,state,title,body,labels,updatedAt" + (",comments" if comments else "")
        args = ["issue", "list", "--state", state, "--limit", str(limit),
                "--json", fields]
        if label:
            args += ["--label", label]
        return [self._issue(d) for d in self._gh_json(args, repo)]

    def issue_set_labels(self, n, add=(), remove=(), repo=None):
        args = ["issue", "edit", str(n)]
        if remove:
            args += ["--remove-label", ",".join(remove)]
        if add:
            args += ["--add-label", ",".join(add)]
        if not add and not remove:
            return True
        r = self._gh(args, repo)
        if r.returncode != 0:
            # 假阴性和解（#207 实证：gh 非零但服务端已应用标签——
            # "mutation landed + client reported failure"）：失败路径重读
            # 远端标签态，目标已达成即幂等成功，裁决不被传输层误报否决；
            # 复核不可用/目标未达成 → 原 fail-closed 错误透传。
            try:
                labels = set(self.issue_labels(n, repo))
            except HostingError:
                labels = None
            if labels is None or not set(add) <= labels or set(remove) & labels:
                raise HostingError(
                    f"issue #{n} 标签设置失败: {r.stderr.strip()[:200]}")
            return True
        return True

    def issue_comment(self, n, body, marker=None, repo=None):
        if marker:
            have = self.issue_view(n, repo)["comments"]
            if any(f"<!-- {marker} -->" in c["body"] for c in have):
                print(f"[dedupe] 评论标记 {marker} 已存在，跳过", file=sys.stderr)
                return True
            body = f"{body}\n<!-- {marker} -->\n"
        r = self._gh(["issue", "comment", str(n), "--body", body], repo)
        if r.returncode != 0:
            raise HostingError(f"issue #{n} 评论失败: {r.stderr.strip()[:200]}")
        return True

    def issue_create(self, title, body, label=None, repo=None):
        args = ["issue", "create", "--title", title, "--body", body]
        if label:
            args += ["--label", label]
        r = self._gh(args, repo)
        if r.returncode != 0:
            raise HostingError(f"issue 创建失败: {r.stderr.strip()[:200]}")
        url = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        m = re.search(r"/issues/(\d+)$", url)
        return {"number": int(m[1]) if m else None, "url": url}

    def pr_view(self, p, repo=None):
        return self._pr(self._gh_json(
            ["pr", "view", str(p),
             "--json", "number,state,reviewDecision,mergeable,labels,"
                       "title,body,headRefName,baseRefName"], repo))

    def pr_list(self, state="open", label=None, limit=100, repo=None):
        args = ["pr", "list", "--state", state, "--limit", str(limit),
                "--json", "number,state,reviewDecision,mergeable,labels,"
                          "title,body,headRefName,baseRefName"]
        if label:
            args += ["--label", label]
        return [self._pr(d) for d in self._gh_json(args, repo)]

    def pr_set_labels(self, p, add=(), remove=(), repo=None):
        args = ["pr", "edit", str(p)]
        if remove:
            args += ["--remove-label", ",".join(remove)]
        if add:
            args += ["--add-label", ",".join(add)]
        if not add and not remove:
            return True
        r = self._gh(args, repo)
        if r.returncode != 0:
            # 假阴性和解：同 issue_set_labels（#207 实证类）——pr view
            # 重读标签态复核，目标已达成即幂等成功；复核不可用/未达成
            # → 原 fail-closed 错误透传。
            try:
                d = self._gh_json(["pr", "view", str(p), "--json", "labels"], repo)
                labels = {l.get("name") for l in d.get("labels") or []}
            except HostingError:
                labels = None
            if labels is None or not set(add) <= labels or set(remove) & labels:
                raise HostingError(
                    f"pr #{p} 标签设置失败: {r.stderr.strip()[:200]}")
            return True
        return True

    def pr_create(self, head, title, body, label=None, base=None, repo=None):
        """创建 PR → 中立 {number,url}。--base 显式必填：默认分支因仓而异
        （gh 猜默认 = 静默落错基线），同 codeup 形态 fail-closed（PR #116）。"""
        if not base:
            raise HostingError(
                "github pr create 需要 --base（默认分支因仓而异，勿猜默认）",
                code=2)
        args = ["pr", "create", "--head", head, "--title", title, "--body", body]
        args += ["--base", base]
        if label:
            args += ["--label", label]
        r = self._gh(args, repo)
        if r.returncode != 0:
            raise HostingError(f"PR 创建失败: {r.stderr.strip()[:200]}")
        url = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        m = re.search(r"/pull/(\d+)$", url)
        return {"number": int(m[1]) if m else None, "url": url}

    def pr_comment(self, p, body, repo=None):
        r = self._gh(["pr", "comment", str(p), "--body", body], repo)
        if r.returncode != 0:
            raise HostingError(f"pr #{p} 评论失败: {r.stderr.strip()[:200]}")
        return True

    def pr_diff(self, p, name_only=False, repo=None):
        args = ["pr", "diff", str(p)]
        if name_only:
            args += ["--name-only"]
        r = self._gh(args, repo)
        if r.returncode != 0:
            raise HostingError(f"pr #{p} diff 失败: {r.stderr.strip()[:200]}")
        return r.stdout

    def pr_merge(self, p, method="merge", repo=None):
        r = self._gh(["pr", "merge", str(p), f"--{method}", "--admin"], repo)
        if r.returncode != 0:
            raise HostingError(f"pr #{p} merge 失败: {r.stderr.strip()[:200]}")
        return True

    def pr_close(self, p, repo=None):
        r = self._gh(["pr", "close", str(p)], repo)
        if r.returncode != 0:
            raise HostingError(f"pr #{p} close 失败: {r.stderr.strip()[:200]}")
        return True

    def label_ensure(self, name, color, desc):
        r = self._gh(["label", "create", name, "--color", color,
                      "--description", desc, "--force"])
        return r.returncode == 0

    def label_history(self, p):
        slug = self.slug()
        if not slug:
            raise HostingError("无法确定 GitHub 仓库 slug", code=2)
        out = subprocess.run(
            ["gh", "api", f"repos/{slug}/issues/{p}/events", "--paginate"],
            capture_output=True, text=True)
        if out.returncode != 0:
            raise HostingError(f"label history 取回失败: {out.stderr.strip()[:200]}")
        hist = []
        for e in json.loads(out.stdout or "[]"):
            ev, name = e.get("event"), (e.get("label") or {}).get("name")
            if ev == "labeled" and name:
                hist.append({"op": "add", "label": name})
            elif ev == "unlabeled" and name:
                hist.append({"op": "remove", "label": name})
        return hist



# ---------------------------------------------------------------------------
# Codeup（云效）适配器 —— oapi/v1 org 级端点（ADR-008）
# ---------------------------------------------------------------------------

_CU_STATE = {"UNDER_DEV": "open", "UNDER_REVIEW": "open", "TO_BE_MERGED": "open",
             "CLOSED": "closed", "MERGED": "merged",
             "opened": "open", "reopened": "open", "closed": "closed",
             "accepted": "open", "merged": "merged", "locked": "open"}
_CU_MERGE_METHOD = {"merge": "no-fast-forward", "squash": "squash", "rebase": "rebase"}
# 评论标记模型（#66，ADR-007 forge 期已 live 验证的等价物迁移）：
# add 标记 = MR 评论「[factory:label:add] X」（resolved=false）；
# remove = 将该 X 未 resolved 的标记评论置 resolved（内容保留）；
# 人工打回手势 = MR 评论含「[factory:changes-requested]」。字节级对齐
# forge 时代格式——ADR-007 期的存量标记评论可被本实现读取。
_CU_LABEL_ADD = "[factory:label:add] "
_CU_FACTORY_PREFIX = "factory:"
_CU_CHANGES_REQ = "[factory:changes-requested]"


def _unsupported(op, why):
    raise HostingError(f"codeup 适配器不支持 {op}: {why}（ADR-008 平台缺口）", code=2)


class CodeupAdapter:
    name = "codeup"

    def __init__(self, repo="."):
        self.repo = repo
        self._repo_id = None
        self._endpoint = None

    def _remote(self):
        """git remote origin → (org, path)；无 remote/解析失败 → (None, None)。
        通用能力（ADR-009）：CODEUP_ORG_ID/CODEUP_REPO_PATH 缺省时自动推导，
        免每仓 hosting.env 定制。https:// 与 SSH/scp 双形态等价解析
        （PR #112 Sourcery 评论②：原正则吞不了 :// 形式）。"""
        try:
            out = subprocess.run(
                ["git", "-C", self.repo, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10)
            url = (out.stdout or "").strip()
        except Exception:
            return None, None
        if not url:
            return None, None
        _h, rpath = _split_remote(url)
        rpath = rpath.strip("/").removesuffix(".git")
        parts = rpath.split("/")
        if len(parts) >= 2 and parts[0] and parts[1]:
            return parts[0], "/".join(parts[1:])
        return None, None

    def _space_id(self, what="issue"):
        """Projex 项目 spaceId：CODEUP_SPACE_ID 显式 → 本机薄映射
        （namespace→spaceId，org 级共享，免每仓定制）。映射文件默认
        ~/.config/factory/codeup-spaces.conf，FACTORY_SPACES_CONF 可覆盖。"""
        if space := os.environ.get("CODEUP_SPACE_ID"):
            return space
        conf = os.environ.get(
            "FACTORY_SPACES_CONF",
            os.path.expanduser("~/.config/factory/codeup-spaces.conf"))
        ns_map = {}
        with contextlib.suppress(OSError):
            with open(conf, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "|" not in line:
                        continue
                    k, v = line.split("|", 1)
                    ns_map[k.strip()] = v.strip()
        org, path = self._remote()
        if org and path and "/" in path and ns_map:
            # namespace = path 首段（gtsp/open-platform/<repo> → gtsp）；
            # 旧 [1] 取到中间层 open-platform，映射永不命中（php#17）
            ns = path.split("/")[0]
            if ns in ns_map:
                return ns_map[ns]
        raise HostingError(
            f"codeup {what} 需要 CODEUP_SPACE_ID（项目 id）"
            "（或本机 codeup-spaces.conf 补 namespace→spaceId 映射）",
            code=2)

    def _cfg(self):
        token = os.environ.get("YUNXIAO_ACCESS_TOKEN")
        if not token:
            raise HostingError("codeup 需要 YUNXIAO_ACCESS_TOKEN（云效个人访问令牌）",
                               code=2)
        if org := os.environ.get("CODEUP_ORG_ID") or self._remote()[0]:
            return token, org
        raise HostingError(
            "codeup 需要 CODEUP_ORG_ID（组织管理后台-基本信息；或 git remote 自动解析）",
            code=2)

    def repo_ref(self):
        if rid := os.environ.get("CODEUP_REPO_ID"):
            return rid
        if path := os.environ.get("CODEUP_REPO_PATH"):
            return urllib.parse.quote(path, safe="")
        if path := self._remote()[1]:
            return urllib.parse.quote(path, safe="")
        raise HostingError(
            "codeup 需要 CODEUP_REPO_ID 或 CODEUP_REPO_PATH"
            "（URL 编码全路径；或 git remote 自动解析）",
            code=2)

    # -- HTTP --
    def _req(self, method, path, body=None, query=None, _retry_rdc=True):
        token, org = self._cfg()
        if self._endpoint is None:
            self._endpoint = os.environ.get("YUNXIAO_ENDPOINT",
                                            "openapi.aliyun.com")
        url = f"https://{self._endpoint}{path}"
        if query:
            url += f"?{urllib.parse.urlencode(query)}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("x-yunxiao-token", token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode() or "{}")
        except urllib.error.URLError as e:
            # 【实测】默认端点受限网络下 TLS 静默丢弃 → 中心版端点重试一次
            if _retry_rdc and self._endpoint == "openapi.aliyun.com":
                self._endpoint = "openapi-rdc.aliyuncs.com"
                return self._req(method, path, body, query, _retry_rdc=False)
            raise HostingError(f"codeup 请求不可达（{self._endpoint}）: {e}") from e
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            raise HostingError(
                f"codeup {method} {path} HTTP {e.code}: {detail}"
            ) from e
        except json.JSONDecodeError as e:
            # 200 + 空/畸形体（代理、网关截断）：fail-closed 成 HostingError，
            # 不让裸 JSONDecodeError 逃出适配器边界（PR #64 Sourcery）
            raise HostingError(
                f"codeup {method} {path} 响应格式错误（{self._endpoint}）: {e}"
            ) from e
        # 【live 2026-08-26】组织级端点（MR 集合等）直接返回 JSON 数组——
        # success/errorCode 包裹仅 dict 形态才有；列表响应原样透传
        if isinstance(payload, dict) and payload.get("success") is False:
            raise HostingError(
                f"codeup {method} {path} 失败: "
                f"{payload.get('errorCode')}: {payload.get('errorMessage')}")
        return payload

    def _base(self):
        _, org = self._cfg()
        return f"/oapi/v1/codeup/organizations/{org}/repositories/{self.repo_ref()}"

    # -- 归一化 --
    @staticmethod
    def _pr(d):
        reviewers = d.get("reviewers") or []
        opinions = [r.get("reviewOpinionStatus") for r in reviewers]
        if "NOT_PASS" in opinions:
            review = "changes_requested"
        elif reviewers and all(o == "PASS" for o in opinions):
            review = "approved"
        else:
            review = "pending"
        status = d.get("newVersionState") or d.get("state") or ""
        return {"number": d.get("localId") or d.get("iid"),
                "state": _CU_STATE.get(status, "open"), "review": review,
                "mergeable": (True if d.get("conflictCheckStatus") == "NO_CONFLICT"
                              else False if d.get("conflictCheckStatus") == "HAS_CONFLICT"
                              else None),
                "labels": [l.get("name") for l in d.get("labels") or [] if l.get("name")],
                "title": d.get("title") or "",
                "body": d.get("description") or "",
                "head": d.get("sourceBranch") or "",
                "base": d.get("targetBranch") or ""}

    # -- ops --
    def auth_ok(self):
        try:
            # 探测 = 鉴权 + 连通。【live 2026-08-26】MR 集合是组织级端点
            # （无 /repositories 段，projectIds query 过滤；仓库级集合 404），
            # 分页参数 perPage（pageSize 仅单体/labels 端点有效）
            _, org = self._cfg()
            self._req(
                "GET", f"/oapi/v1/codeup/organizations/{org}/changeRequests",
                query={"page": 1, "perPage": 1, "projectIds": self.repo_ref()})
            return True
        except HostingError as e:
            print(f"[hosting] codeup 鉴权探测失败: {e}", file=sys.stderr)
            return False

    # -- 工作项面（issue 等价物，#67 live 已验形态；forge 参考实现迁移）--

    _WI_LABELS_MARK = re.compile(r"<!--\s*factory:labels:v1:\s*(.*?)\s*-->")

    @classmethod
    def _wi_labels_of(cls, wi):
        """标签读取按载体分派：native=labels 字段；description=尾部注释块
        （云效 Task 类型常无 labels 字段——PUT 报 does not contains field,
        ADR-007 实测;富文本完整保留 HTML 注释）。载体由 env
        CODEUP_ISSUE_LABELS 选择（native|description,默认 native）。"""
        if os.environ.get("CODEUP_ISSUE_LABELS", "native") == "description":
            m = cls._WI_LABELS_MARK.search(wi.get("description") or "")
            return m.group(1).split() if m and m.group(1) else []
        return [l for l in (wi.get("labels") or []) if isinstance(l, str)]

    @classmethod
    def _wi_state_of(cls, wi):
        # logicalStatus: NORMAL=活跃;FINISHED/其余=closed（保守:不误清标签）
        return "open" if (wi.get("logicalStatus") or "NORMAL") == "NORMAL" else "closed"

    @staticmethod
    def _wi_text(raw):
        """description 双形态（{"htmlValue":...} JSON 串 / 裸 HTML）→ 纯文本。"""
        s = raw or ""
        if s.lstrip().startswith("{"):
            with contextlib.suppress(ValueError):
                s = json.loads(s).get("htmlValue") or ""
        # HTML 注释段原样保留：dedupe marker（<!-- m1 -->）与 labels 块
        # （<!-- factory:labels:v1: ... -->）靠注释承载——剥标签会把注释
        # 一起剥掉，marker 永不命中（#67 实现期实证）。labels 块的剥离
        # 由 _wi_normalize 的专用 sub 负责。
        parts = re.split(r"(<!--.*?-->)", s, flags=re.S)
        s = "".join(seg if seg.startswith("<!--")
                    else re.sub(r"<[^>]+>", " ", seg) for seg in parts)
        return re.sub(r"[ \t]+", " ", s).strip()

    def _wi_normalize(self, wi, comments=True):
        body = self._wi_text(wi.get("description"))
        # 标记块从正文剥离（native 载体下块不存在,sub 为无害 no-op）
        body = self._WI_LABELS_MARK.sub("", body).strip()
        _, org = self._cfg()
        cs = []
        if comments:
            raw = self._req(
                "GET",
                f"/oapi/v1/projex/organizations/{org}/workitems/{wi['id']}/comments")
            cs = [{"author": (c.get("author") or {}).get("name") or "",
                   "body": self._wi_text(c.get("content"))}
                  for c in (raw if isinstance(raw, list) else raw.get("result") or [])]
        return {"number": wi.get("serialNumber") or wi.get("id"),
                "state": self._wi_state_of(wi),
                "title": wi.get("subject") or "",
                "body": body,
                "labels": self._wi_labels_of(wi),
                "comments": cs}

    def _wi_get(self, n):
        """双键寻址：serialNumber（T-16）或 24-hex id 均 200（live）。"""
        _, org = self._cfg()
        r = self._req(
            "GET",
            f"/oapi/v1/projex/organizations/{org}/workitems/{n}")
        # live 形态：详情返回裸工作项 dict（无 result 包裹）;search 才包 result
        return r.get("result") or r if isinstance(r, dict) else r or {}

    def issue_view(self, n, repo=None):
        return self._wi_normalize(self._wi_get(n))

    def issue_labels(self, n, repo=None):
        return self._wi_labels_of(self._wi_get(n))

    def issue_list(self, state="open", label=None, limit=100,
                   comments=False, repo=None):
        # 【live】workitems:search：category 必填（workitemTypeId 过滤被拒
        # "工作项类型不能为空"）;分页 perPage/page;摘要有 description——
        # description 载体标签零 N+1。state 过滤客户端做（search 无
        # logicalStatus 参数）;label 过滤"含有"语义对齐 GitHub
        space = self._space_id("issue list")
        category = os.environ.get("CODEUP_WORKITEM_CATEGORY", "Task")
        _, org = self._cfg()
        out, page = [], 1
        while len(out) < limit:
            payload = self._req(
                "POST", f"/oapi/v1/projex/organizations/{org}/workitems:search",
                body={"category": category, "spaceId": space,
                      "perPage": 100, "page": page,
                      "orderBy": "gmtCreate", "sort": "desc"})
            batch = payload.get("result") if isinstance(payload, dict) else payload
            if not batch:
                break
            out += [self._wi_normalize(wi, comments=comments) for wi in batch]
            if len(batch) < 100:
                break
            page += 1
        if state != "all":
            out = [i for i in out if i["state"] == state]
        if label:
            out = [i for i in out if label in i["labels"]]
        return out[:limit]

    def issue_set_labels(self, n, add=(), remove=(), repo=None):
        wi = self._wi_get(n)
        labels = list(self._wi_labels_of(wi))
        for x in add:
            if x not in labels:
                labels.append(x)
        labels = [l for l in labels if l not in set(remove)]
        _, org = self._cfg()
        path = f"/oapi/v1/projex/organizations/{org}/workitems/{wi['id']}"
        if os.environ.get("CODEUP_ISSUE_LABELS", "native") == "description":
            # 读-改-写描述块：原文剥离旧块,尾部追加新块（空标签=移除块）
            raw = wi.get("description") or ""
            base = self._WI_LABELS_MARK.sub("", raw).rstrip()
            desc = base + ("\n\n<!-- factory:labels:v1: "
                           + " ".join(sorted(labels)) + " -->" if labels else "")
            self._req("PUT", path, body={
                "description": desc,
                "formatType": wi.get("formatType") or "MARKDOWN"})
        else:
            self._req("PUT", path, body={"labels": sorted(set(labels))})
        return True

    def issue_comment(self, n, body, marker=None, repo=None):
        if marker:
            have = self.issue_view(n, repo)["comments"]
            if any(f"<!-- {marker} -->" in c["body"] for c in have):
                print(f"[dedupe] 评论标记 {marker} 已存在，跳过", file=sys.stderr)
                return True
            body = f"{body}\n<!-- {marker} -->\n"
        wi = self._wi_get(n)  # 评论端点仅认 24-hex id（serialNumber 404）
        _, org = self._cfg()
        self._req(
            "POST",
            f"/oapi/v1/projex/organizations/{org}/workitems/{wi['id']}/comments",
            body={"content": body, "contentType": "markdown"})
        return True

    def _default_cfvs(self, space, wit):
        """拉字段配置,为全部 required 的 SystemCustomField 构造默认值
        （forge 实装迁移,PR #62 破案:开始=今日/完成=+7d/float="0.5"/
        date=今日/list=末档 option id——「末项=最低档」为实测约定）。"""
        today = datetime.date.today().isoformat()
        due = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        _, org = self._cfg()
        fields = self._req(
            "GET", f"/oapi/v1/projex/organizations/{org}/projects/{space}"
                  f"/workitemTypes/{wit}/fields")
        out = {}
        for f in (fields if isinstance(fields, list) else fields.get("result", [])):
            if f.get("required") not in (True, "true", 1):
                continue
            if f.get("type") == "NativeField":
                continue  # subject/assignedTo 走 create 本体字段
            fid, name, fmt = str(f["id"]), f["name"], f.get("format", "")
            if "开始" in name:
                out[fid] = today
            elif "完" in name or "结束" in name:
                out[fid] = due
            elif fmt == "float":
                out[fid] = "0.5"
            elif fmt == "date":
                out[fid] = today
            elif f.get("options"):
                out[fid] = str(f["options"][-1]["id"])
        return out

    def issue_create(self, title, body, label=None, repo=None):
        # forge 实装迁移（PR #62 实测破案,真实 Codeup 项目创建验证）：
        # create 本体必填仅 4 项;「计划开始时间」等模板必填是
        # SystemCustomField,须以 customFieldValues {"fieldId":"value"}
        # 平面对象传（数组形态 Invalid format;value 形态见 _default_cfvs）。
        space = self._space_id("issue create")
        wit = os.environ.get("CODEUP_WORKITEM_TYPE_ID")
        assignee = os.environ.get("CODEUP_ASSIGN_USER_ID")
        if missing := [
            k
            for k, v in (
                ("CODEUP_WORKITEM_TYPE_ID", wit),
                ("CODEUP_ASSIGN_USER_ID", assignee),
            )
            if not v
        ]:
            raise HostingError(
                "codeup issue create 需要 " + "/".join(missing)
                + "（space=项目 id、wit=工作项类型 id、assign=指派人 24-hex"
                  " 用户 id——工作项详情 assignedTo.id 形态;成员查询端点"
                  "不可达,值从云效界面取）", code=2)
        _, org = self._cfg()
        payload = {"spaceId": space, "subject": title,
                   "workitemTypeId": wit, "description": body or "",
                   "assignedTo": assignee}
        try:
            payload["customFieldValues"] = self._default_cfvs(space, wit)
        except HostingError as e:
            # 字段配置拉取失败降级告警不阻断（forge 同款行为）：create 由
            # 平台按模板必填裁决,平台错比静默跳过更可诊断
            print(f"[hosting] [warn] 字段配置拉取失败,create 可能因模板"
                  f"必填被拒: {e}", file=sys.stderr)
        if label:
            # 云效 Task 类型常无 labels 字段（ADR-007 实测：PUT 报
            # "workitem does not contains field"）；等价载体 =
            # description 尾部 HTML 注释块（富文本完整保留，读取时剥离）
            payload["description"] = (
                (body or "") + f"\n\n<!-- factory:labels:v1: {label} -->")
        r = self._req("POST",
                      f"/oapi/v1/projex/organizations/{org}/workitems", payload)
        d = r.get("result") if isinstance(r, dict) else r
        d = d or {}
        wid = d.get("id")
        # 【live 2026-08-26】create 响应只含 24-hex id，无 serialNumber
        # （实测项目 T-21）；人类可读编号（T-N）须回查
        # 详情。回查失败降级 id（view/编辑两种键都认，但人在界面引用
        # 序号——宁可多一次 GET）
        number = d.get("serialNumber") or wid
        url = d.get("detailUrl", "")
        if wid:
            try:
                det = self._req(
                    "GET",
                    f"/oapi/v1/projex/organizations/{org}/workitems/{wid}")
                det = det.get("result") if isinstance(det, dict) else det
                number = (det or {}).get("serialNumber") or wid
                url = (det or {}).get("detailUrl") or url
            except HostingError as e:
                print(f"[hosting] serialNumber 回查失败，降级 id: {e}",
                      file=sys.stderr)
        return {"number": number, "url": url}

    def _marker_comments(self, p):
        # 【live 契约，ADR-007/#66】comments/list 两态各拉一次取全集
        out = []
        for resolved in (False, True):
            payload = self._req(
                "POST", f"{self._base()}/changeRequests/{p}/comments/list",
                body={"patchSetBizIds": [], "commentType": "GLOBAL_COMMENT",
                      "state": "OPENED", "resolved": resolved})
            items = payload if isinstance(payload, list) else (payload.get("result") or [])
            for c in items:
                content = c.get("content") or ""
                if content.startswith(_CU_LABEL_ADD) or _CU_CHANGES_REQ in content:
                    out.append({"id": c.get("id") or c.get("commentBizId")
                                or c.get("commentId"),
                                "content": content, "resolved": resolved})
        return out

    def _marker_comments_best_effort(self, p):
        # 读路径专用（Sourcery #11）：评论端点失败不阻断 PR 详情。
        # 返回 (markers, ok)：ok=False = 端点降级——调用方不得把空集当
        # 「无标记」真相（advisory #11：降级时回退展示原生类标，宁可多显示
        # 不可隐藏真实标签）；写路径（pr_set_labels）仍用 _marker_comments
        # 显式失败。
        try:
            return self._marker_comments(p), True
        except HostingError as e:
            print(f"[hosting] 标记评论读取失败，降级空集: {e}", file=sys.stderr)
            return [], False

    def _pr_labels(self, p):
        # 两载体合并（#66）：类标 Link（平台原生）∪ 未 resolved 的 add 标记。
        # 【live 2026-08-26】MR 详情响应无 labels 字段——类标须专用端点读回。
        # 标记是唯一真相源：工厂类标无未 resolved 标记即视为已移除
        #（平台无类标 unlink API，remove 只 resolve 标记——CodeRabbit PR #11）
        markers, ok = self._marker_comments_best_effort(p)
        active = {self._marker_label(m["content"]) for m in markers
                  if not m["resolved"] and m["content"].startswith(_CU_LABEL_ADD)}
        names = []
        with contextlib.suppress(HostingError):
            payload = self._req("GET", f"{self._base()}/changeRequests/{p}/labels")
            items = payload if isinstance(payload, list) else (payload.get("result") or [])
            for l in items:
                name = l.get("name")
                if not name:
                    continue
                if ok and name.startswith(_CU_FACTORY_PREFIX) and name not in active:
                    continue  # 工厂类标投影失真：以标记生命周期为准（仅读成功时）
                names.append(name)
        if ok:
            names += active
        return sorted({n for n in names if n})

    @staticmethod
    def _marker_label(content):
        # 平台开放输入：恰为前缀/前缀+空白时切片为空，splitlines()[0] 抛
        # IndexError（CodeRabbit xx-skills#14）；空标记按无标记处理
        rest = content[len(_CU_LABEL_ADD):].strip()
        return rest.splitlines()[0].strip() if rest else ""

    def pr_view(self, p, repo=None):
        # 【live 2026-08-26】单体端点是仓库级（仓库级集合 404、单体正常）
        d = self._req("GET", f"{self._base()}/changeRequests/{p}")
        out = self._pr(d.get("result", d))
        out["labels"] = self._pr_labels(p)
        # 人工打回手势（#66）：[factory:changes-requested] 评论 →
        # changes_requested（Codeup 无 reviewDecision 等价物的场景；
        # reviewer 意见 NOTPASS 映射保留，两者取严）
        markers, _ = self._marker_comments_best_effort(p)  # 降级 → 空集 → 不误报
        if out["review"] != "changes_requested" and any(
                _CU_CHANGES_REQ in m["content"] for m in markers):
            out["review"] = "changes_requested"
        return out

    def pr_list(self, state="open", label=None, limit=100, repo=None):
        # 【live 2026-08-26 实测项目】集合是组织级端点（无
        # /repositories 段；仓库级集合 404——ADR-007 forge 期同发现），
        # GET + URL query 过滤 projectIds（POST/body 形态被拒），分页
        # perPage；state 服务端过滤 opened。label 过滤客户端做（labelIds
        # 服务端过滤需类标 ID，留待需要时启用）
        _, org = self._cfg()
        out, page = [], 1
        while len(out) < limit:
            payload = self._req(
                "GET", f"/oapi/v1/codeup/organizations/{org}/changeRequests",
                query={"page": page, "perPage": 100,
                       "projectIds": self.repo_ref(),
                       "state": "opened" if state == "open" else "all"})
            batch = payload if isinstance(payload, list) else (payload.get("result") or [])
            out += [self._pr(d) for d in batch]
            if len(batch) < 100:  # 页短于 perPage = 末页（空页/短页都停）
                break
            page += 1
        if state != "all":
            out = [p for p in out if p["state"] == "open"]
        if label:
            out = [p for p in out if label in p["labels"]]
        return out[:limit]

    def _label_markers(self, p, name):
        """同名 label 的未 resolved add 标记（add/remove 幂等预检共用）。

        普通循环逐条判别（无重复索引/无海象，规避 Sourcery 两口径分歧）。
        """
        out = []
        for m in self._marker_comments(p):
            c = m["content"]
            if m["resolved"] or not c.startswith(_CU_LABEL_ADD):
                continue
            if self._marker_label(c) == name:
                out.append(m)
        return out

    def pr_set_labels(self, p, add=(), remove=(), repo=None):
        """评论标记模型（#66，承载平台缺口 b）：remove = 置 resolved
        （内容保留，轮次计数不减——对齐 GitHub label-add 事件语义）；
        add = 标记评论 + 类标 Link 平台原生补充（两载体并存）。
        add 的预检+POST 以跨进程锁串行（PR #116）：双进程同时过预检再
        各 POST = 双未 resolved 标记；锁内重预检命中 → 幂等跳过。"""
        for name in remove:
            hits = self._label_markers(p, name)
            if not hits:
                print(f"[hosting] remove {name}: 无未 resolved 标记（幂等跳过）",
                      file=sys.stderr)
            for m in hits:
                self._req("PUT",
                          f"{self._base()}/changeRequests/{p}/comments/{m['id']}",
                          body={"resolved": True})
        for name in add:
            # 幂等（对齐 remove 分支）：已有同名未 resolved 标记则跳过
            # ——重试/双写场景重复 POST 会堆未 resolved 重复标记（php#17）。
            # 预检+POST 在跨进程锁内（_add_label_lock）：锁外预检=裸竞态
            # 窗口，后到者锁内重预检命中 → 幂等跳过，锁保证恰一次 POST。
            with self._add_label_lock(p, name):
                if hits := self._label_markers(p, name):
                    print(f"[hosting] add {name}: 已有未 resolved 标记（幂等跳过）",
                          file=sys.stderr)
                    continue
                self._req("POST", f"{self._base()}/changeRequests/{p}/comments",
                          body={"comment_type": "GLOBAL_COMMENT",
                                "content": f"{_CU_LABEL_ADD}{name}",
                                "resolved": False})
        # 类标 Link best-effort：不存在（label create 未破案，界面人工路径）
        # 时降级告警——标记评论已承载状态机语义，链不因平台类标缺失受阻
        ids = []
        for name in add:
            try:
                ids.append(self._label_id(name))
            except HostingError as e:
                print(f"[hosting] 类标 Link 降级（标记评论已承载）: {e}",
                      file=sys.stderr)
        # 【live 2026-08-26】LinkMergeRequestLabel body 键是 labelIdList
        # （labelIds/labels/labelId 均被拒："Invalid param value [null]"）
        if ids:
            try:
                self._req("POST", f"{self._base()}/changeRequests/{p}/labels",
                          body={"labelIdList": ids})
            except HostingError as e:
                print(f"[hosting] 类标 Link 降级（标记评论已承载）: {e}",
                      file=sys.stderr)
        return True

    @contextlib.contextmanager
    def _add_label_lock(self, p, name):
        """add「预检+POST」互斥上下文（见模块段注释）：mkdir 原子占锁 +
        pid 活性判死接管 + 等锁有界；超时 raise HostingError(code=1)——宁可
        让调用链失败重试（重试以幂等跳过收敛），不放行双写。"""
        lock_dir = _label_lock_dir(self.repo, p, name)
        deadline = time.monotonic() + _LABEL_LOCK_TIMEOUT
        # 锁根常驻：ensure 父目录（多进程并发 makedirs exist_ok 原子无害）
        os.makedirs(_label_lock_root(), exist_ok=True)
        while True:
            try:
                os.mkdir(lock_dir)
            except FileExistsError as e:
                owner = _lock_owner(lock_dir)
                if _lock_stale(lock_dir, owner):
                    # 判死与清除分离（PR #116 审查 P2）：rename 领取清除权，
                    # 他者先接管则 rename 失败、活锁不被动；owner 复核兜底
                    # 判死→改名间他者已 mkdir 新活锁的窗口（原样放回不删）
                    # ——与 lease 墓碑 check-move 竞态同族，杜绝误删活主。
                    victim = f"{lock_dir}.dead.{os.getpid()}.{time.monotonic_ns()}"
                    try:
                        os.rename(lock_dir, victim)
                    except OSError:
                        continue  # 他者已清/接管：不抢，重评估
                    if _lock_owner(victim) != owner:
                        with contextlib.suppress(OSError):
                            os.rename(victim, lock_dir)  # 判死后换新主：原样放回
                        continue
                    shutil.rmtree(victim, ignore_errors=True)
                    continue  # 死主残锁：清后重试（mkdir 收敛单赢家）
                if time.monotonic() >= deadline:
                    raise HostingError(
                        f"add {name}: 同标签并发写互斥超时"
                        f"（{_LABEL_LOCK_TIMEOUT:.0f}s，另一进程持锁），"
                        "fail-closed 拒双写",
                        code=1,
                    ) from e
                time.sleep(0.05)
                continue
            break
        with contextlib.suppress(OSError):
            with open(os.path.join(lock_dir, "pid"), "w",
                      encoding="ascii") as fh:
                fh.write(str(os.getpid()))
        try:
            yield
        finally:
            shutil.rmtree(lock_dir, ignore_errors=True)

    def _label_id(self, name):
        # 【文档推导】ListProjectLabels → name→id
        payload = self._req("GET", f"{self._base()}/labels",
                            query={"page": 1, "pageSize": 100})
        for l in (payload if isinstance(payload, list) else (payload.get("result") or [])):
            if l.get("name") == name:
                return l.get("id")
        raise HostingError(f"类标 {name} 不存在（先 label ensure）", code=2)

    def pr_create(self, head, title, body, label=None, base=None, repo=None):
        # 【文档推导】CreateMergeRequest（body 形态经文档核实）
        if not base:
            # targetBranch 必填且因仓而异（master/main 均有实仓）——猜默认
            # 会静默落错基线，fail-closed 拒猜（web-tools#5 Sourcery）
            raise HostingError(
                "codeup pr create 需要 --base（目标分支因仓而异，勿猜默认）",
                code=2)
        rid = self.repo_ref()
        payload = self._req("POST", f"{self._base()}/changeRequests", body={
            "title": title, "description": body,
            "sourceBranch": head, "targetBranch": base,
            "sourceProjectId": rid, "targetProjectId": rid})
        result = payload.get("result", payload)
        url = result.get("detailUrl") or result.get("webUrl") or ""
        if label:
            if local_id := result.get("localId"):
                try:
                    self.pr_set_labels(local_id, add=[label])
                except HostingError as e:
                    print(f"[hosting] PR 已建但打标失败: {e}", file=sys.stderr)
        return {"number": result.get("localId"), "url": url}

    def pr_comment(self, p, body, repo=None):
        # 【实测】comment_type 无默认值、resolved 必填（skills 沉淀）
        self._req("POST", f"{self._base()}/changeRequests/{p}/comments",
                  body={"comment_type": "GLOBAL_COMMENT", "content": body,
                        "resolved": True})
        return True

    def pr_close(self, p, repo=None):
        # 【live 2026-08-26】唯一生效形态 = POST /close 空 body（实测项目
        # MR#7 实测：POST {} → 200 且状态转 CLOSED）。陷阱：PUT 详情端点带
        # {"state":"closed"} 返回 {"result":true} 但状态不变——假阳性，勿用。
        self._req("POST", f"{self._base()}/changeRequests/{p}/close", body={})
        return True

    def pr_diff(self, p, name_only=False, repo=None):
        if name_only:
            # 【文档推导】GetMergeRequestChangeTree → 变更文件路径
            payload = self._req(
                "GET", f"{self._base()}/changeRequests/{p}/changeTree")
            tree = payload.get("result") or {}
            paths = []

            def _walk(node):
                for ch in node.get("children") or node.get("subTrees") or []:
                    if (ch.get("type") or ch.get("nodeType")) == "blob":
                        paths.append(ch.get("path") or ch.get("name"))
                    else:
                        _walk(ch)
            _walk(tree)
            return "\n".join(paths)
        _unsupported("pr diff 全文", "Codeup 无 unified diff 文本端点（变更树可查路径）")

    def pr_merge(self, p, method="merge", repo=None):
        # 【文档推导】MergeMergeRequest（mergeType 枚举对齐）
        self._req("POST", f"{self._base()}/changeRequests/{p}/merge",
                  body={"mergeType": _CU_MERGE_METHOD.get(method, "no-fast-forward"),
                        "removeSourceBranch": False})
        return True

    # （pr_close 唯一定义在上文——曾出现双定义后者遮蔽前者，已收口）

    def label_ensure(self, name, color, desc):
        # 【文档推导】CreateProjectLabel；已存在（409/重复码）视为成功
        try:
            self._req("POST", f"{self._base()}/labels",
                      body={"name": name, "color": f"#{color}", "description": desc})
            return True
        except HostingError as e:
            if "HTTP 4" in str(e):
                return True  # 已存在/冲突 → ensure 语义达成
            raise

    def label_history(self, p):
        # 评论标记承载（#66，平台缺口 c）：全部 add 标记 → 事件流。
        # resolved 不减计数（重派前 remove、再打回再 add，轮次单调递增
        # ——对齐 GitHub label-add 事件语义）；中立 schema 同 GitHub 侧。
        return [
            {"op": "add", "label": label}
            for m in self._marker_comments(p)
            if m["content"].startswith(_CU_LABEL_ADD)
            and (label := self._marker_label(m["content"]))
        ]  # 前缀-only 评论空标记 → walrus 短路不产无效事件（#119）


ADAPTERS = {"github": GitHubAdapter, "codeup": CodeupAdapter}


def _split_remote(url: str) -> tuple:
    """remote URL → (host, path)：https/ssh:// 走 urlparse（hostname
    小写），SSH/scp 形态 [user@]host:path 正则兜底。单一解析原语
    （PR #112 评论②③同根因：_remote 与 _detect_hosting 曾各自
    解析，一改一漏）。"""
    if "://" in url:
        u = urllib.parse.urlparse(url)
        return (u.hostname or "").lower(), u.path
    m = re.match(r"(?:[^@\s]+@)?([^:/]+)[:/](.+?)(?:\.git)?/?$", url)
    return ((m[1] if m else url.split("/")[0]).lower(),
            m[2] if m else "")


def _host_of(url: str) -> str:
    """remote URL → host（CodeQL：禁止子串猜测——URL 任意位置可伪造）。"""
    return _split_remote(url)[0]


def _is_codeup_url(url: str) -> bool:
    """codeup 域名精确锚定：host 等值或子域后缀，非子串包含。"""
    host = _host_of(url)
    return host == "codeup.aliyun.com" or host.endswith(".codeup.aliyun.com")


def _detect_hosting(repo="."):
    """按 git remote origin 自动检测 hosting：codeup.aliyun.com → codeup；
    github.com/无 remote → github（历史默认）。FACTORY_HOSTING 显式设置优先。"""
    if explicit := os.environ.get("FACTORY_HOSTING"):
        return explicit
    try:
        url = subprocess.run(
            ["git", "-C", repo, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        url = ""
    return "codeup" if _is_codeup_url(url) else "github"


def current_adapter(repo="."):
    if cls := ADAPTERS.get(FACTORY_HOSTING or _detect_hosting(repo)):
        return cls(repo)
    else:
        raise HostingError(f"未知 FACTORY_HOSTING: {FACTORY_HOSTING}", code=2)


def _repo_split(raw):
    """--repo 双语义拆分（PR #116 CodeRabbit）→ (local, slug)。

    - 本地目录形态（存在，含 "."）：探测/远端解析用真实路径（该目录
      remote 选平台、解析 slug），ops 收 slug=None——由目录 remote
      自解析（java#29 跨仓调用的本意；目录路径绝不进 gh --repo）。
    - owner/repo slug 形态：探测回退 "."（按 cwd remote 选平台），
      slug 原样透传给 ops（gh --repo <slug>）。
    未传 --repo → (".", None)。
    """
    if raw is None:
        return ".", None
    return (raw, None) if os.path.isdir(raw) else (".", raw)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _csv(v):
    return [x for x in (v or "").split(",") if x]


def _body(args):
    if args.body_file:
        with open(args.body_file, encoding="utf-8") as f:
            return f.read()
    return args.body or ""


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False))


def _build_parser():
    """构造 CLI 参数解析器（子命令定义原样迁自 main）。"""
    p = argparse.ArgumentParser(prog="hosting.py", add_help=True,
                                 description="托管平台抽象层（ADR-008）")
    sub = p.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("auth")
    ap.add_argument("ok", nargs="?", default="ok")  # `auth ok` 探测惯用形

    sp = sub.add_parser("label")
    lsp = sp.add_subparsers(dest="label_cmd", required=True)
    en = lsp.add_parser("ensure")
    en.add_argument("name"); en.add_argument("color"); en.add_argument("desc")
    lsp.add_parser("history").add_argument("pr")

    ip = sub.add_parser("issue")
    isp = ip.add_subparsers(dest="issue_cmd", required=True)
    isp.add_parser("view").add_argument("n")
    isp.add_parser("get-labels").add_argument("n")
    il = isp.add_parser("list")
    il.add_argument("--state", default="open", choices=["open", "all"])
    il.add_argument("--label"); il.add_argument("--limit", type=int, default=100)
    il.add_argument("--comments", action="store_true")
    sl = isp.add_parser("set-labels")
    sl.add_argument("n"); sl.add_argument("--add"); sl.add_argument("--remove")
    ic = isp.add_parser("comment")
    ic.add_argument("n")
    _body_opts(ic)
    ic.add_argument("--marker")
    icr = isp.add_parser("create")
    icr.add_argument("--title", required=True)
    _body_opts(icr)
    icr.add_argument("--label"); icr.add_argument("--repo")

    pp = sub.add_parser("pr")
    psp = pp.add_subparsers(dest="pr_cmd", required=True)
    pv = psp.add_parser("view"); pv.add_argument("p"); pv.add_argument("--repo")
    pl = psp.add_parser("list")
    pl.add_argument("--state", default="open", choices=["open", "all"])
    pl.add_argument("--label"); pl.add_argument("--limit", type=int, default=100)
    pl.add_argument("--repo")
    psl = psp.add_parser("set-labels")
    psl.add_argument("p"); psl.add_argument("--add"); psl.add_argument("--remove")
    pcr = psp.add_parser("create")
    pcr.add_argument("--head", required=True); pcr.add_argument("--title", required=True)
    _body_opts(pcr)
    pcr.add_argument("--label"); pcr.add_argument("--base"); pcr.add_argument("--repo")
    pc = psp.add_parser("comment")
    pc.add_argument("p"); _body_opts(pc)
    pd = psp.add_parser("diff")
    pd.add_argument("p"); pd.add_argument("--name-only", action="store_true")
    pm = psp.add_parser("merge")
    pm.add_argument("p")
    pm.add_argument("--method", default="merge",
                    choices=["merge", "squash", "rebase"])
    return p


def _cmd_label(ad, args):
    """label 子命令分派（ensure / history）。"""
    if args.label_cmd == "ensure":
        _cmd_label_ensure(ad, args)
    else:
        _cmd_label_history(ad, args)


def _cmd_label_ensure(ad, args):
    sys.exit(0 if ad.label_ensure(args.name, args.color, args.desc) else 1)


def _cmd_label_history(ad, args):
    _emit(ad.label_history(args.pr))


def _cmd_issue(ad, args):
    """issue 子命令分派。"""
    if args.issue_cmd == "view":
        _cmd_issue_view(ad, args)
    elif args.issue_cmd == "get-labels":
        _cmd_issue_get_labels(ad, args)
    elif args.issue_cmd == "list":
        _cmd_issue_list(ad, args)
    elif args.issue_cmd == "set-labels":
        _cmd_issue_set_labels(ad, args)
    elif args.issue_cmd == "comment":
        _cmd_issue_comment(ad, args)
    elif args.issue_cmd == "create":
        _cmd_issue_create(ad, args)


def _cmd_issue_view(ad, args):
    _emit(ad.issue_view(args.n))


def _cmd_issue_get_labels(ad, args):
    _emit(ad.issue_labels(args.n))


def _cmd_issue_list(ad, args):
    _emit(ad.issue_list(state=args.state, label=args.label,
                        limit=args.limit, comments=args.comments))


def _cmd_issue_set_labels(ad, args):
    ad.issue_set_labels(args.n, add=_csv(args.add), remove=_csv(args.remove))


def _cmd_issue_comment(ad, args):
    ad.issue_comment(args.n, _body(args), marker=args.marker)


# ── issue 创建验收明确性预检（#104/#109 triage 对比观察落地）──────────
# triage 判据 b（客观验收载体）对 issue 写法敏感：#104 正文只有问题
# 描述与建议、无验收载体，三判据全灭打回；#109 正文带「验收判据」节
# + 4 条可机械判定 checkbox，判据 b 直接过。创建时拦截（fail-closed）
# 比 triage 打回省一轮往返。机器开单模板（daily-regression.sh/
# upstream-sync-check.sh）已同步补「验收（可机械判定）」节。
_ACCEPTANCE_HEAD_RE = re.compile(
    r"^#{1,6}[^\n]*(?:验收|acceptance)", re.IGNORECASE | re.MULTILINE)
_CHECKBOX_RE = re.compile(r"^[\s>*-]*\[[ xX]\]", re.MULTILINE)


def _issue_acceptance_error(body):
    """issue 正文验收标准不明确时返回提示语；明确返回 None。

    明确 = 满足其一：① checkbox（可机械勾选即验收载体）
    ②「验收/acceptance」标题节。#104 形态（描述+建议、两者皆无）
    → 不明确。
    """
    if not (body or "").strip():
        return ("正文为空：无验收载体。补『## 验收（可机械判定）』节，"
                "逐条写完成与否可判定的判据（推荐 checkbox）")
    if _CHECKBOX_RE.search(body) or _ACCEPTANCE_HEAD_RE.search(body):
        return None
    return ("验收标准不明确：正文无 checkbox 亦无『验收/acceptance』节"
            "——无客观载体，triage 判据 b 必打回（#104 形态）。补"
            "『## 验收（可机械判定）』节逐条写判据（#109 形态：4 条"
            " checkbox 直接过）")


# ── issue 创建标签合法性预检（第三层：factory: 命名空间保留给状态机）──
# factory:* 是状态机/门控的属主写命名空间（regression/README.md 语义：
# 「打其他 factory:* 标签会永远不被拾取」——triage-batch 只拾取零
# factory:* 标签的 open issue）：create 时携带任何 factory:* 即伪称
# 生命周期事实——accepted 绕过 triage 裁决、triaging/in-progress 伪装
# 链锁占用、PR 侧/裁决/门控态（needs-review/validated 等）在无 PR、
# 无裁决的创建时点语义不存在。命名空间拦截 fail-closed：typo
# （factory:accepetd）与未来新增状态标签自动被拦，不依赖枚举镜像。
# 唯一豁免 factory:needs-human：机器判定「不可自动、需人工」的合法
# 落点（breaker_tripped 族命令式落标；upstream-sync-check.sh local
# 漂移实证机器用法）。非 factory:* 标签（priority:* 等 dispatch
# 消费面）不受限。


def _issue_label_error(label):
    """issue create 标签占 factory: 命名空间时返回提示语；合法返回 None。"""
    if label and label.startswith("factory:") and label != "factory:needs-human":
        return (f"标签 {label} 占用 factory: 命名空间（状态机/门控属主写），"
                "create 时携带即伪称生命周期事实（accepted 绕 triage 裁决、"
                "triaging/in-progress 伪装锁占用、PR 侧/门控态在创建时点"
                "语义不存在；未知 factory:* 多为 typo 且会被 triage 批次"
                "永久跳过）。正道：零标签走 triage 裁决路径；确需人工"
                "接管用 factory:needs-human；分类用非 factory 标签"
                "（如 priority:*）")
    return None


def _cmd_issue_create(ad, args):
    body = _body(args)
    # 预检先于任何平台触达（fail-closed；#104/#109 对比）
    if err := _issue_acceptance_error(body):
        raise HostingError(f"issue create 预检未过：{err}", code=2)
    if err := _issue_label_error(args.label):
        raise HostingError(f"issue create 预检未过：{err}", code=2)
    _emit(ad.issue_create(args.title, body, label=args.label, repo=args.repo))


def _cmd_pr(ad, args):
    """pr 子命令分派。"""
    if args.pr_cmd == "view":
        _cmd_pr_view(ad, args)
    elif args.pr_cmd == "list":
        _cmd_pr_list(ad, args)
    elif args.pr_cmd == "set-labels":
        _cmd_pr_set_labels(ad, args)
    elif args.pr_cmd == "create":
        _cmd_pr_create(ad, args)
    elif args.pr_cmd == "comment":
        _cmd_pr_comment(ad, args)
    elif args.pr_cmd == "diff":
        _cmd_pr_diff(ad, args)
    elif args.pr_cmd == "merge":
        _cmd_pr_merge(ad, args)


def _cmd_pr_view(ad, args):
    _emit(ad.pr_view(args.p, repo=args.repo))


def _cmd_pr_list(ad, args):
    _emit(ad.pr_list(state=args.state, label=args.label,
                     limit=args.limit, repo=args.repo))


def _cmd_pr_set_labels(ad, args):
    ad.pr_set_labels(args.p, add=_csv(args.add), remove=_csv(args.remove))


def _cmd_pr_create(ad, args):
    _emit(ad.pr_create(args.head, args.title, _body(args),
                       label=args.label, base=args.base, repo=args.repo))


def _cmd_pr_comment(ad, args):
    ad.pr_comment(args.p, _body(args))


def _cmd_pr_diff(ad, args):
    out = ad.pr_diff(args.p, name_only=args.name_only)
    print(out if isinstance(out, str) else json.dumps(out))


def _cmd_pr_merge(ad, args):
    ad.pr_merge(args.p, method=args.method)


def main(argv):
    """CLI 入口：解析 → --repo 双语义拆分 → 取适配器 → 命令分派。"""
    args = _build_parser().parse_args(argv)
    try:
        # --repo 目标仓驱动平台检测（java#29 Sourcery：按 cwd 检测在
        # 跨仓 CLI 调用下会选错适配器）；拆分后探测用 local（目录真实
        # 路径或 "."），args.repo 改写为 slug 形态——目录形态收 None
        # （slug 由该目录 remote 自解析），slug 形态原样进 ops。
        raw = getattr(args, "repo", None)
        local, args.repo = _repo_split(raw)
        ad = current_adapter(local)

        if args.cmd == "auth":
            sys.exit(0 if ad.auth_ok() else 1)

        if args.cmd == "label":
            _cmd_label(ad, args)
        elif args.cmd == "issue":
            _cmd_issue(ad, args)
        elif args.cmd == "pr":
            _cmd_pr(ad, args)
    except HostingError as e:
        print(f"[hosting] {e}", file=sys.stderr)
        sys.exit(e.code)


def _body_opts(sp):
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--body")
    g.add_argument("--body-file")


if __name__ == "__main__":
    main(sys.argv[1:])
