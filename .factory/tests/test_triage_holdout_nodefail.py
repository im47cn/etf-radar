"""triage/holdout/marker 失败路径 node-fail 证据回归（PR #172 Sourcery 复审）。

缺口：run_triage/run_holdout 的失败出口（进程失败/裁决解析失败）与
run_node 起点标记创建失败原本只留通用 chain-abort——下轮 prime 无法
区分"裁决器死"与"编排死"。本测试沿用 test_b1_fallback 的提取哲学：
按函数名切源码执行真实函数体，桩 omp_node 可控退码/日志，
factory_lib.parse 走真实现——parse 失败即真实解析器判定，非桩回声。

marker-create 用例：issue 目录 chmod 0555 后 touch 新文件被拒（目录
不可写），但 append 到已存在的 chain-history 不受目录位影响（文件权限
独立于目录权限）——恰好隔离出"标记创建失败而台账可写"的观测窗口。

运行：python3 -m pytest .factory/tests -q
"""

import json
import shutil
import subprocess
from pathlib import Path

FACTORY = Path(__file__).resolve().parents[1]


def _func_body(name: str) -> str:
    lines = (FACTORY / "fix-issue.sh").read_text(encoding="utf-8").splitlines()
    start = next((i for i, l in enumerate(lines)
                  if l.startswith(name + "() {")), None)
    assert start is not None, f"fix-issue.sh 缺 {name} 定义——锚定失效即红"
    end = next((i for i in range(start + 1, len(lines)) if lines[i] == "}"), None)
    assert end is not None, f"{name} 函数体未按列 0 闭括号闭合——锚定失效即红"
    return "\n".join(lines[start:end + 1])


TRIAGE = _func_body("run_triage")
HOLDOUT = _func_body("run_holdout")
RUN_NODE = _func_body("run_node")

_OMP_STUB = """#!/bin/sh
case "${STUB_MODE:?}" in
  fail) exit 1 ;;
  garbage) printf '思考中……未见 JSON\\n' >> "$2"; exit 0 ;;
  *) printf '{"verdict":"%s"}\\n' "${STUB_MODE}" >> "$2"; exit 0 ;;
esac
"""

_DRIVER = r"""#!/usr/bin/env bash
set -euo pipefail
REPO="$1"; DIR="$2"; WT="$1"; ISSUE="99"; DRY=0; ROUND=3
export PATH="$3:$PATH"
export STUB_MODE="$4"
node_timeout() { echo 30m; }
_node_metric() { :; }
json_field() { python3 "${REPO}/.factory/factory_lib.py" jfield "$@"; }
__FUNC__
__CALL__
"""


def _sandbox(tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(FACTORY, repo / ".factory",
                    ignore=shutil.ignore_patterns(
                        "artifacts", "worktrees", "__pycache__", "locks"))
    (repo / "MISSION.md").write_text("mission stub\n", encoding="utf-8")
    (repo / ".factory" / "prompts" / "foo.md").write_text(
        "# foo 节点\n\n输出计划正文即可。\n", encoding="utf-8")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "omp_node").write_text(_OMP_STUB, encoding="utf-8")
    (bindir / "node_timeout").write_text("#!/bin/sh\necho 30m\n", encoding="utf-8")
    for f in bindir.iterdir():
        f.chmod(0o755)
    issue_dir = repo / "issue-99"
    issue_dir.mkdir()
    (issue_dir / "issue.json").write_text(json.dumps({
        "title": "标题", "body": "正文",
        "comments": [{"author": "u", "body": "评论"}]}), encoding="utf-8")
    (issue_dir / "tests-output.txt").write_text("全部通过\n", encoding="utf-8")
    return str(issue_dir)


def _run(tmp_path: Path, func_src: str, call: str, mode: str, setup=None):
    issue_dir = _sandbox(tmp_path)
    if setup:
        setup(Path(issue_dir))
    drv = tmp_path / "drv.sh"
    drv.write_text(_DRIVER.replace("__FUNC__", func_src)
                   .replace("__CALL__", call), encoding="utf-8")
    r = subprocess.run(["/bin/bash", str(drv), str(tmp_path / "repo"),
                        issue_dir, str(tmp_path / "bin"), mode],
                       capture_output=True, text=True, timeout=60)
    return r, issue_dir


def _history(issue_dir: str) -> list:
    p = Path(issue_dir) / "chain-history"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def test_triage_omp_failure_leaves_node_fail(tmp_path):
    """裁决器进程失败（omp 退码非零）→ node-fail omp-exit 行，非只有 chain-abort。"""
    r, d = _run(tmp_path, TRIAGE, "run_triage", "fail")
    assert r.returncode == 1, r.stderr
    rows = _history(d)
    assert rows and "node=triage" in rows[-1] and "reason=omp-exit" in rows[-1] \
        and "round=3" in rows[-1], rows


def test_triage_parse_failure_leaves_node_fail(tmp_path):
    """裁决输出无法解析为 JSON（真实 factory_lib.parse 判定）→ node-fail parse 行。"""
    r, d = _run(tmp_path, TRIAGE, "run_triage", "garbage")
    assert r.returncode == 1, r.stderr
    rows = _history(d)
    assert rows and "node=triage" in rows[-1] and "reason=parse" in rows[-1], rows


def test_triage_success_writes_no_node_fail(tmp_path):
    """裁决成功（verdict=accept 经真实 parse）→ 不落 node-fail，triage.json 落盘。"""
    r, d = _run(tmp_path, TRIAGE, "run_triage", "accept")
    assert r.returncode == 0, r.stderr
    assert not _history(d)
    assert (Path(d) / "triage.json").exists()


def test_holdout_omp_failure_leaves_node_fail(tmp_path):
    """验证器进程失败 → node-fail omp-exit 行。"""
    r, d = _run(tmp_path, HOLDOUT, "run_holdout", "fail")
    assert r.returncode == 1, r.stderr
    rows = _history(d)
    assert rows and "node=holdout" in rows[-1] and "reason=omp-exit" in rows[-1], rows


def test_holdout_parse_failure_leaves_node_fail(tmp_path):
    """验证输出无法解析 → node-fail parse 行。"""
    r, d = _run(tmp_path, HOLDOUT, "run_holdout", "garbage")
    assert r.returncode == 1, r.stderr
    rows = _history(d)
    assert rows and "node=holdout" in rows[-1] and "reason=parse" in rows[-1], rows


def test_holdout_success_writes_no_node_fail(tmp_path):
    """验证成功（verdict=PASS）→ 不落 node-fail，holdout.json 落盘。"""
    r, d = _run(tmp_path, HOLDOUT, "run_holdout", "PASS")
    assert r.returncode == 0, r.stderr
    assert not _history(d)
    assert (Path(d) / "holdout.json").exists()


def test_marker_create_failure_leaves_node_fail(tmp_path):
    """起点标记创建失败（目录不可写）→ node-fail marker-create 行再退出。"""

    def setup(d: Path):
        (d / "chain-history").write_text("", encoding="utf-8")
        d.chmod(0o555)

    try:
        r, d = _run(tmp_path, RUN_NODE, "run_node foo", "fail", setup=setup)
        assert r.returncode == 1, r.stderr
        rows = _history(d)
        assert rows and "node=foo" in rows[-1] \
            and "reason=marker-create" in rows[-1], rows
    finally:
        (tmp_path / "repo" / "issue-99").chmod(0o755)  # 还原权限供 tmp 清理
