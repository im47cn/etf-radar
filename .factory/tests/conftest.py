import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 测试密封性（steering/testing-standards.md）：import 期剥离 hook 注入的
# GIT_*（lefthook pre-push 链），显式环境变量优先于 cwd 发现，会把测试里
# cwd=tmp_path / git -C <tmp夹具仓> 的 git init/add/commit 劫持到真仓
# （2026-08-22 事故：389 文件被删；2026-08-27 PR #71：夹具提交落真仓
# HEAD）。import 期剥离最早且确定，先于任何测试执行；子进程继承剥离后的
# 环境（含 spawn 的 .factory 脚本子链）。与各 skills 套件 conftest 同一
# 范式（ADR-010 机械化：tools/check_git_sealing.py R1）。
for _k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
           "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE"):
    os.environ.pop(_k, None)


@pytest.fixture()
def private_tmp(tmp_path: Path) -> Path:
    """泄漏断言隔离：被测进程 TMPDIR 注入 pytest 私有目录。

    mktemp 泄漏断言（after-before 差集）原对共享系统 tempdir glob 同模板
    文件（.factory-dist.* / .factory-stage.* / .factory-downstream-check.*），
    套件外进程瞬时写入同模板即随机打破差集（pre-push 闸两次 flake，隔离
    重跑绿证实环境性；tests 顺序执行、其余三闸对本仓 no-op，污染源必在
    套件外）。被测脚本 mktemp 模板 "${TMPDIR:-/tmp}/..." 原生尊重 TMPDIR
    ——用例把 env["TMPDIR"] 指到本目录后，泄漏检测语义不变（仍检被测
    进程自身暂存），断言 glob 对齐同一目录，外部写者不再可见。
    """
    d = tmp_path / "tmp"
    d.mkdir()
    return d
