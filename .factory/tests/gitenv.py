"""git 子进程环境密闭（pre-push 钩子防夹具污染，PR #71 实测事故）。

lefthook pre-push 在 git 钩子环境运行测试门禁：GIT_DIR 等仓库发现类
环境变量被导出给钩子进程链，泄漏进测试子进程后，`git -C <tmp仓>` 的
仓库发现被环境变量优先级覆盖——夹具 init/commit 落进真实仓 HEAD
（推送实测：worktree HEAD 出现树仅含 2 个夹具文件的陌生提交，随后
plugin_lock 因 HEAD 树缺文件连锁失败）。

issue #109 补密闭两缺口（根因同源：os.environ 逐字渗漏进子进程）：
- PATH 白名单：只留测试链真正依赖的目录（python3/git/bash 所在目录
  ∪ /usr/bin:/bin）。宿主 PATH 可见 sourcery（pip user bin）时，
  夹具内 sync-from-upstream.sh 的 `command -v sourcery` 探测通过 →
  发真网络请求 → 套件挂起/超时（本机 300s 超时实证）。锚定解析强制
  走 POSIX 标准目录——宿主 PATH 永不参与白名单推导，锚定工具与
  sourcery 同目录共存（homebrew bin 等）不可再泄漏（PR #111 评论①）。
- GIT_CONFIG_GLOBAL/SYSTEM=/dev/null：宿主全局 gitconfig 的
  commit.gpgsign=true 使夹具 commit rc=128（gpg 签名失败）。命令行
  -c 与 GIT_AUTHOR_* 等环境变量注入优先级高于文件配置，不受影响
  （测试显式身份注入原样工作）。另剥除 GIT_CONFIG 环境注入族
  （COUNT/KEY_n/VALUE_n/PARAMETERS）——其优先级高于文件密封值，
  泄漏则 gpgsign 仍可注入（PR #111 评论②）。

调用：剥除仓库发现类变量 + 上述密闭注入，保留其余变量。
"""
from __future__ import annotations

import os
import shutil

# 仓库发现/定位类变量（泄漏即改写 -C/子目录发现结果）。
_STALE = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_GRAFT_FILE",
    "GIT_INDEX_VERSION", "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES",
)

# 环境注入配置族（优先级高于 GIT_CONFIG_GLOBAL/SYSTEM 密封值，
# PR #111 Sourcery 评论②）：键名固定 + KEY_n/VALUE_n 前缀两种形态
_GIT_CONFIG_INJECT = ("GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS")
_GIT_CONFIG_INJECT_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")

# 测试子进程链锚定工具（所在目录进 PATH 白名单：python3 → bash → git）
_ANCHOR_TOOLS = ("python3", "git", "bash")
# POSIX 标准目录兜底（sed/grep/sh 等 coreutils 所在）
_FALLBACK_DIRS = ("/usr/bin", "/bin")


def _sealed_path() -> str:
    """PATH 白名单：锚定工具所在目录 ∪ POSIX 标准目录。

    目录级白名单（非工具级）：够跑 python3→bash→git 测试链即可，
    宿主私有目录（pip user bin 等）整体剥除——sourcery 不可见 →
    夹具闸 command -v 探测跳过 → 零出网（issue #109 陷阱①）。

    锚定解析强制走 POSIX 标准目录（PR #111 Sourcery 评论①）：宿主
    PATH 永不参与白名单推导——锚定工具与 sourcery 同目录共存时
    （如 homebrew bin 同时装 python3 与 sourcery），该目录不可再
    泄漏进白名单。锚定工具均在标准目录内可解析（/usr/bin/python3、
    /usr/bin/git、/bin/bash），解析失败亦有 _FALLBACK_DIRS 兜底。
    """
    dirs: list[str] = []
    for tool in _ANCHOR_TOOLS:
        where = shutil.which(tool, path=os.pathsep.join(_FALLBACK_DIRS))
        d = os.path.dirname(where) if where else None
        if d and d not in dirs:
            dirs.append(d)
    for d in _FALLBACK_DIRS:
        if d not in dirs:
            dirs.append(d)
    return os.pathsep.join(dirs)


def git_env(base: dict | None = None) -> dict:
    """拷贝环境并密闭 git 子进程面（默认基于 os.environ）。

    - 剥除仓库发现类变量（PR #71）
    - PATH 白名单化 + GIT_CONFIG_GLOBAL/SYSTEM=/dev/null（issue #109）
    - 剥除 GIT_CONFIG 环境注入族（PR #111 Sourcery 评论②）

    base 显式传入的 PATH/GIT_CONFIG_* 会被密闭值覆盖/剥除——密闭面
    不可被调用方松开（breaker 沙箱的显式 /dev/null 注入自此冗余但
    同值）。
    """

    env = dict(base if base is not None else os.environ)
    for k in _STALE:
        env.pop(k, None)
    for k in list(env):
        if (k in _GIT_CONFIG_INJECT
                or k.startswith(_GIT_CONFIG_INJECT_PREFIXES)):
            del env[k]
    env["PATH"] = _sealed_path()
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return env
