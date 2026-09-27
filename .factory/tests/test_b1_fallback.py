"""B1 产物判定「无声明回退」回归（2026-09-05）——真实执行 run_node 分支逻辑。

事故背景：438aa0f 引入 B1 后，artifact 提取行（`grep … | sed …`）缺 `|| true`。
fix-issue.sh 顶部 `set -euo pipefail` 下，prompts 无 ARTIFACT 声明时 grep
无匹配 exit 1 → 管道失败（pipefail）→ 命令替换失败 → 赋值语句非零 →
errexit 杀整个脚本，永远到不了 `-z` 回退分支（stdout ARTIFACT: 行检查）。
Sourcery 在 PR #144 合并前自动修复（sed 后补 `|| true`）——本测试锚定该
行为防回归：

- 提取 fix-issue.sh 的 run_node/_node_metric 函数体（sed 锚定函数名起止，
  不执行顶层主流程/锁/trap），在 `set -euo pipefail` 子进程内 source 后
  真实调用 run_node —— 不是复制判定逻辑，穿的是真实脚本代码。
- 场景 A：prompts 无 ARTIFACT 声明 + 节点 log 含 `ARTIFACT:` 行
  → 提取得空值 → 走 `-z` 回退 → 节点 ok（exit 0、metrics 记 ok）。
  修复前 errexit 在此杀进程，测试红。
- 场景 B：prompts 无 ARTIFACT 声明 + log 无 `ARTIFACT:` 行
  → 回退判定失败 → return 1（no-artifact 失败路径，非 errexit 死）。

运行：python3 -m pytest .factory/tests -q（与其他沙箱测试同构：tmp git 仓
+ .factory 拷贝 + PATH 桩；omp_node/node_timeout 只记录调用）。
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]

_OMP_STUB = """#!/bin/sh
echo "omp_node $*" >> "${STUB_CALLS:?}"
if [ "${STUB_MODE:-ok}" != "bare" ]; then
  printf 'done\\nARTIFACT: $ISSUE_DIR/%s\\n' "${STUB_ARTIFACT:-foo.md}" >> "$2"
else
  printf 'done\\n' >> "$2"
fi
exit 0
"""
_TIMEOUT_STUB = "#!/bin/sh\necho 30m\n"

_BASH_DRIVER = r"""#!/usr/bin/env bash
set -euo pipefail
REPO="$1"; DIR="$2"; WT="$3"; ISSUE="99"; DRY=0
export PATH="$4:$PATH"
export STUB_CALLS="$5" STUB_MODE="$6"
	awk '/^run_node\(\)/{f=1} /^run_triage\(\)/{f=0} f' "$REPO/.factory/fix-issue.sh" > "$DIR/.fn-extract.sh"
	source "$DIR/.fn-extract.sh"
	run_node foo
"""


def _sandbox(tmp_path: Path, stub_mode: str) -> dict:
    """tmp git 仓 + .factory 拷贝 + 无声明 foo.md + 桩 bin；返回路径/调用标记。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=env)
    factory = repo / ".factory"
    shutil.copytree(FACTORY, factory,
                    ignore=shutil.ignore_patterns("artifacts", "worktrees", "__pycache__", "locks"))
    # 无 ARTIFACT 声明的测试节点 prompt（场景核心：grep 提取为空）
    (factory / "prompts" / "foo.md").write_text(
        "# foo 节点\n\n输出计划正文即可。\n", encoding="utf-8")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.txt"
    (bindir / "omp_node").write_text(_OMP_STUB, encoding="utf-8")
    (bindir / "node_timeout").write_text(_TIMEOUT_STUB, encoding="utf-8")
    for f in bindir.iterdir():
        f.chmod(0o755)
    issue_dir = repo / "issue-99"
    issue_dir.mkdir()
    return {"repo": str(repo), "dir": str(issue_dir), "bin": str(bindir),
            "calls": str(calls), "mode": stub_mode}


def _run_node(tmp_path: Path, stub_mode: str) -> subprocess.CompletedProcess:
    s = _sandbox(tmp_path, stub_mode)
    return subprocess.run(
        ["bash", "-c", _BASH_DRIVER, "driver",
         s["repo"], s["dir"], s["repo"], s["bin"], s["calls"], s["mode"]],
        capture_output=True, text=True, timeout=60)


def _metrics(sandbox_dir: str) -> list[dict]:
    p = Path(sandbox_dir) / "node-metrics.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]


def test_no_artifact_prompt_falls_back_to_stdout(tmp_path):
    """场景 A：prompts 无声明 + log 含 ARTIFACT 行 → 回退通过，不 errexit 死。"""
    r = _run_node(tmp_path, stub_mode="ok")
    assert r.returncode == 0, f"errexit 杀进程或非预期失败：\n{r.stdout}\n{r.stderr}"
    assert "节点 foo 未声明产物" not in r.stderr        # 走了通过路径
    metrics = _metrics(str(tmp_path / "repo" / "issue-99"))
    assert metrics and metrics[-1]["status"] == "ok", f"台账缺 ok：{metrics}"


def test_no_artifact_prompt_and_no_stdout_line_fails_closed(tmp_path):
    """场景 B：prompts 无声明 + log 无 ARTIFACT 行 → no-artifact return 1。"""
    r = _run_node(tmp_path, stub_mode="bare")
    assert r.returncode == 1, f"应为 no-artifact 失败(1)，实得 {r.returncode}：\n{r.stdout}\n{r.stderr}"
    assert "未声明产物（缺 ARTIFACT 行）" in r.stderr
    metrics = _metrics(str(tmp_path / "repo" / "issue-99"))
    assert metrics and metrics[-1]["status"] == "no-artifact", f"台账缺 no-artifact：{metrics}"
