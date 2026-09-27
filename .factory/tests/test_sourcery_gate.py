"""Sourcery 闸语言口径与引号展开回归（2026-09-05）——真实执行 sourcery-gate.sh。

事故背景：issue #123——纯 PHP 仓本地 sourcery 硬闸是安慰剂（.php 实测不
扫描，送审零输出静默空转 = fail-open）；CI 侧各仓 yml 同病。PR #141
（ac71ae0 + 21351a6）修 tools/git/lefthook/sourcery-gate.sh 与
.github/workflows/sourcery-review-gate.yml：SUPPORTED=py/ts/js 进闸面，
UNSENT=go/java/cs/php 显式披露不进闸面。21351a6 另修 yml 侧字符串分词/
glob 真缺陷（文件名含空格会拆参）。#141 无自动化测试——本测试锚定该
行为契约防回归：

- opt-in：无 .sourcery.yaml → 跳过（fail-safe）；未装 sourcery CLI → 跳过
- 纯面外语集 → 显式降级披露 + exit 0 + 不调用 sourcery（防静默 fail-open）
- 混合集 → 只 review 实测支持子集 + ⚠ 披露未送审清单
- 无语言文件 → 跳过；.lefthook/（上游分发面）文件不审判
- 含空格文件名 → 单参数传递（21351a6 引号展开修复锚定）
- sourcery review 非零 → 闸透传非零并给跳过提示（硬闸语义）
- CLI 在装但认证/订阅失效（rc≠0 + 认证类错误输出）→ 显式降级 exit 0
  （2026-09-13 防砖化：trial 到期不得拦死一切 push；CI 侧 fail-closed 兜底）

运行：python3 -m pytest .factory/tests -q（沙箱同构：tmp 工作目录 +
PATH 桩 sourcery 记录 args/rc，真实调用目标脚本本体）。

与 Sourcery CLI 版本无关：不依赖真实 sourcery，桩记录调用形状。
"""

import os
import subprocess
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]          # .factory/
GATE = FACTORY.parent / "tools/git/lefthook/sourcery-gate.sh"

_SOURCERY_STUB = """#!/bin/sh
echo "argc=$#" >> "$STUB_LOG"
for a in "$@"; do printf 'arg=%s\\n' "$a" >> "$STUB_LOG"; done
[ -n "${STUB_OUT:-}" ] && printf '%s\\n' "$STUB_OUT"
exit "${STUB_RC:-0}"
"""

_BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _run_gate(tmp_path: Path, files: list[str], *, sourcery_yaml=True,
              with_cli=True, stub_rc=0, stub_out="") -> tuple[subprocess.CompletedProcess, list[str]]:
    """tmp 工作目录 + 可选 .sourcery.yaml + 可选桩 sourcery；返回 (result, stub 调用行)。"""
    work = tmp_path / "work"
    work.mkdir()
    if sourcery_yaml:
        (work / ".sourcery.yaml").write_text("# 评审保留清单（测试桩）\n", encoding="utf-8")
    for f in files:
        p = work / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    path = _BASE_PATH
    log = tmp_path / "stub.log"
    if with_cli:
        bindir = tmp_path / "bin"
        bindir.mkdir()
        (bindir / "sourcery").write_text(_SOURCERY_STUB, encoding="utf-8")
        (bindir / "sourcery").chmod(0o755)
        path = f"{bindir}:{path}"
    else:
        bindir = tmp_path / "empty-bin"
        bindir.mkdir()
        path = str(bindir)
    env = dict(os.environ, PATH=path, STUB_LOG=str(log), STUB_RC=str(stub_rc),
               STUB_OUT=stub_out)
    r = subprocess.run(["/bin/bash", str(GATE), *files], cwd=str(work), env=env,
                       capture_output=True, text=True, timeout=30)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return r, calls


def test_pure_unsent_language_degrades_without_calling(tmp_path):
    """纯 php（实测不扫描）→ 降级披露 + exit 0 + sourcery 不调用（#123 主诉）。"""
    r, calls = _run_gate(tmp_path, ["a.php"])
    assert r.returncode == 0, r.stderr
    assert "实测支持面外" in r.stdout and "降级跳过" in r.stdout
    assert "该集不经 Sourcery 评审" in r.stdout
    assert calls == [], f"纯面外语不应调用 sourcery：{calls}"


def test_untested_languages_disclosed_not_silently_passed(tmp_path):
    """go/java/cs（未实测面）→ 披露 + 不调用（防静默 fail-open）。"""
    r, calls = _run_gate(tmp_path, ["a.go", "b.java", "c.cs"])
    assert r.returncode == 0, r.stderr
    assert "实测支持面外" in r.stdout
    assert calls == [], f"未实测语言不应进闸面：{calls}"


def test_mixed_reviews_supported_discloses_unsent(tmp_path):
    """py+php 混合 → 只 review py + ⚠ 披露 php 清单。"""
    r, calls = _run_gate(tmp_path, ["a.py", "b.php"])
    assert r.returncode == 0, r.stderr
    assert "⚠ 1 个语言文件未送审" in r.stdout and "b.php" in r.stdout
    assert "review --check：1 个实测支持文件" in r.stdout
    assert calls and calls[0] == "argc=5", f"应精确 5 参：{calls}"
    assert "arg=a.py" in calls and "arg=b.php" not in calls, calls


def test_supported_languages_all_reviewed(tmp_path):
    """py/ts/js 全进闸面，单次调用精确传参。"""
    r, calls = _run_gate(tmp_path, ["x.py", "y.ts", "z.js"])
    assert r.returncode == 0, r.stderr
    assert "review --check：3 个实测支持文件" in r.stdout
    assert calls and calls[0] == "argc=7", calls  # review --check --config .sourcery.yaml + 3 文件
    for want in ["arg=review", "arg=--check", "arg=--config",
                 "arg=.sourcery.yaml", "arg=x.py", "arg=y.ts", "arg=z.js"]:
        assert want in calls, f"缺 {want}：{calls}"


def test_filename_with_spaces_stays_single_argument(tmp_path):
    """含空格文件名 → 单参数传递（21351a6 引号展开修复锚定，分词/glob 回归）。"""
    r, calls = _run_gate(tmp_path, ["my file.py"])
    assert r.returncode == 0, r.stderr
    assert calls and calls[0] == "argc=5", f"5 参（含整名文件）实得：{calls}"
    assert "arg=my file.py" in calls, f"文件名被拆参：{calls}"
    assert "arg=my" not in calls and "arg=file.py" not in calls, f"分词复现：{calls}"


def test_lefthook_upstream_mirror_excluded(tmp_path):
    """.lefthook/（上游分发面）不审判——即使扩展名在支持面内。"""
    r, calls = _run_gate(tmp_path, [".lefthook/hook.py", "real.py"])
    assert r.returncode == 0, r.stderr
    assert "review --check：1 个实测支持文件" in r.stdout
    assert calls and "arg=real.py" in calls and "arg=.lefthook/hook.py" not in calls, calls


def test_sourcery_failure_blocks_with_skip_hint(tmp_path):
    """sourcery review 非零 → 闸透传非零 + 跳过提示（硬闸语义）。"""
    r, calls = _run_gate(tmp_path, ["a.py"], stub_rc=1)
    assert r.returncode == 1, r.stderr
    assert "存在未解决 issue，push 被拦" in r.stdout
    assert "--no-verify" in r.stdout


def test_no_language_files_skips(tmp_path):
    """无语言文件变更 → 跳过 exit 0（README/LICENSE 不进任何面）。"""
    r, calls = _run_gate(tmp_path, ["README.md", "LICENSE"])
    assert r.returncode == 0, r.stderr
    assert "无语言文件变更，跳过" in r.stdout
    assert calls == []


def test_not_opted_in_skips(tmp_path):
    """无 .sourcery.yaml → fail-safe 跳过（opt-in 门禁）。"""
    r, calls = _run_gate(tmp_path, ["a.py"], sourcery_yaml=False)
    assert r.returncode == 0, r.stderr
    assert "未 opt-in" in r.stdout
    assert calls == []


def test_missing_cli_skips(tmp_path):
    """未装 sourcery CLI → fail-safe 跳过（不因环境缺失误伤）。"""
    r, calls = _run_gate(tmp_path, ["a.py"], with_cli=False)
    assert r.returncode == 0, r.stderr
    assert "未安装 sourcery CLI" in r.stdout
    assert calls == []


def test_auth_failure_degrades_explicitly(tmp_path):
    """CLI 在装但认证/订阅失效（rc≠0 + 认证类错误输出）→ 显式降级 exit 0（防砖化）。

    2026-09-13：trial 到期后 review 若认证失败，闸不得拦死一切含 py/ts/js 的
    push——降级须显式（可审计非静默），且 CI 侧仍 fail-closed 兜底。
    """
    r, calls = _run_gate(tmp_path, ["a.py"], stub_rc=1,
                         stub_out="Error: Your trial has ended. Please update your payment method.")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "认证/订阅失效" in r.stdout and "降级" in r.stdout
    assert "push 被拦" not in r.stdout, "认证失效不得按代码 issue 拦截"
    assert calls and calls[0] == "argc=5", calls  # 确曾真实调过 CLI（非提前跳过）


def test_issue_failure_with_output_still_blocks(tmp_path):
    """rc≠0 + issue 表格输出（无认证关键词）→ 仍硬拦（降级仅限认证失败形态）。"""
    r, calls = _run_gate(tmp_path, ["a.py"], stub_rc=1,
                         stub_out="tools/x.py:10-12 reintroduce-else\nTotal: 1 issue")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "push 被拦" in r.stdout and "--no-verify" in r.stdout
    assert "认证/订阅失效" not in r.stdout, "issue 输出被误判为认证失败"


def test_auth_keyword_in_issue_diagnostic_still_blocks(tmp_path):
    """认证词混入 issue 诊断（评审 #178 bug_risk 场景）→ issue 形态优先，仍硬拦。

    文件名含 unauthorized、错误行含 subscription 等宽词散落形态不得放行；
    降级仅当输出无 issue 计数且认证词锚定在错误行/完整句式上。
    """
    r, calls = _run_gate(
        tmp_path, ["a.py"], stub_rc=1,
        stub_out="tools/unauthorized.py:10-12 use-named-expression\n"
                 " • 1 issue detected.\n"
                 "Error: subscription quota exceeded")   # 宽词 + issue 计数混合
    assert r.returncode == 1, r.stdout + r.stderr
    assert "push 被拦" in r.stdout, "含 issue 计数的输出不得降级"
    assert "认证/订阅失效" not in r.stdout


def test_pure_error_line_auth_degrades(tmp_path):
    """行首锚定的认证错误行（无 issue 计数）→ 降级放行（401/login 形态）。"""
    r, calls = _run_gate(tmp_path, ["a.py"], stub_rc=1,
                         stub_out="Error: 401 Unauthorized. Please log in with `sourcery login`.")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "认证/订阅失效" in r.stdout
    assert "push 被拦" not in r.stdout


def test_trial_banner_with_issues_still_blocks(tmp_path):
    """试用提示横幅（ends on，进行时）+ issue 计数 → 仍硬拦（在期真实形态）。

    横幅是 stderr 噪音且用词为 "ends on"（非 ended/expired），不得触发降级；
    本形态即试用期内含 issue 的真实 push 输出，是防误降级的主线场景。
    """
    r, calls = _run_gate(
        tmp_path, ["a.py"], stub_rc=1,
        stub_out="Your trial ends on 2026-09-13, update your payment method\n"
                 " • 4 issues detected.")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "push 被拦" in r.stdout
    assert "认证/订阅失效" not in r.stdout
