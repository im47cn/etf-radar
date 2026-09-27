"""issue_reject 回执沙箱——2026-09-20 #207 静默拒绝事故形态。

回归优先：真实函数按名从 factory-lib.sh 正则提取（零拷贝，源漂移即
测试失败），在 git-free 夹具沙箱执行（REPO 指向临时目录，hosting/
factory_lib/lease 全部桩替，零网络零真实 issue）。三态钉死后修复的
两级失败语义：
- 假阴性：set-labels 非零 + 远端 factory:rejected 已落 → 按已落定继续
  发回执（#207 修复锚：旧实现 || return 1 早退，回执永不执行）；
- 真失败：非零 + 复核确证缺失 → return 1 不发评论；
- 成功路径：落标成功 → 回执照常。
机器评论正文不得含 [factory:rejected] 子串（state.py 毒丸扫描）。
"""
import re
import subprocess
from pathlib import Path

import pytest

FACTORY = Path(__file__).resolve().parents[1]
LIB = (FACTORY / "factory-lib.sh").read_text(encoding="utf-8")

STUB_HOSTING = '''\
#!/usr/bin/env python3
"""沙箱桩：set-labels 由 env 注入成败；get-labels 打印 REMOTE_LABELS；
comment 追加到 COMMENT_LOG（不真实发送）。"""
import json
import os
import sys

args = sys.argv[1:]
if args[:2] == ["issue", "set-labels"]:
    if os.environ.get("LABEL_RESULT") != "ok":
        print("HostingError: gh issue edit 失败: POST api.github.com: 502",
              file=sys.stderr)
        sys.exit(1)
elif args[:2] == ["issue", "get-labels"]:
    print(json.dumps(json.loads(os.environ.get("REMOTE_LABELS", "[]"))))
    sys.exit(0)
elif args[:2] == ["issue", "comment"]:
    with open(os.environ["COMMENT_LOG"], "a", encoding="utf-8") as log:
        body_file = args[args.index("--body-file") + 1]
        marker = (args[args.index("--marker") + 1]
                  if "--marker" in args else "")
        log.write(f"--- marker={marker}\\n"
                  + open(body_file, encoding="utf-8").read())
    sys.exit(0)
sys.exit(0)
'''

STUB_FACTORY_LIB = '''\
#!/usr/bin/env python3
"""沙箱桩：sanitize no-op（正文安全非本套件主题）；receipt 打固定
回执正文（刻意不含 [factory:rejected] 子串——state.py 毒丸不变量）。"""
import sys

if sys.argv[1] == "sanitize":
    sys.exit(0)
if sys.argv[1] == "receipt":
    print("## 工厂 triage 裁决：reject —— 判据 b 不通过\\n\\n- 判据b: 不通过\\n")
    sys.exit(0)
'''

STUB_LEASE = "lease_guard() { return 0; }\n"


def _fn(name: str) -> str:
    # 函数体行全缩进、收尾 } 顶格——非贪婪到首个顶格 } 即函数边界
    m = re.search(rf"\n({name}\(\) \{{.*?\n\}})\n", LIB, re.S)
    assert m, f"factory-lib.sh 缺 {name}() —— 正则提取漂移，源已变"
    return m.group(1) + "\n"


FUNCS = "".join(_fn(n) for n in
                ("issue_label_swap", "issue_comment", "issue_reject"))


@pytest.fixture()
def sandbox(tmp_path: Path):
    repo = tmp_path / "repo"
    fdir = repo / ".factory"
    fdir.mkdir(parents=True)
    (fdir / "hosting.py").write_text(STUB_HOSTING, encoding="utf-8")
    (fdir / "factory_lib.py").write_text(STUB_FACTORY_LIB, encoding="utf-8")
    (fdir / "factory-lease.sh").write_text(STUB_LEASE, encoding="utf-8")
    (fdir / "triage.json").write_text(
        '{"verdict": "reject", "reasons": ["判据b: 不通过"]}',
        encoding="utf-8")
    return repo


def _run(repo: Path, env_extra: dict) -> subprocess.CompletedProcess:
    # set -uo pipefail（无 -e）：issue_reject 内部自持失败语义；先
    # source 桩 lease——对齐真实形态（factory-lib.sh 顶部 source
    # factory-lease.sh 提供 lease_guard，正则提取的函数体不含该行）
    script = (f"set -uo pipefail\n"
              f"source '{repo}/.factory/factory-lease.sh'\n"
              f"{FUNCS}\nissue_reject '' .factory/triage.json\n")
    env = {"REPO": str(repo), "ISSUE": "207", "PATH": "/usr/bin:/bin",
           "COMMENT_LOG": str(repo / "comment.log"), **env_extra}
    return subprocess.run(["bash", "-c", script], cwd=str(repo), env=env,
                          capture_output=True, text=True)


def test_false_negative_posts_receipt(sandbox):
    """#207 事故核心形态：set-labels 非零 + 远端已落 → 回执不丢
    （旧实现 || return 1 早退、回执永不执行——本回归锚）。"""
    r = _run(sandbox, {"LABEL_RESULT": "fail",
                       "REMOTE_LABELS": '["factory:rejected"]'})
    assert r.returncode == 0, r.stderr
    log = (sandbox / "comment.log").read_text(encoding="utf-8")
    assert "factory:receipt:issue-207:rbatch" in log
    out = r.stdout + r.stderr
    assert "按已落定继续回执" in out
    assert "[hosting]" in out  # 落标 stderr 落档回显（Fix B）


def test_true_failure_aborts_without_receipt(sandbox):
    """复核确证 factory:rejected 缺失 → return 1 不发评论（裁决未落定，
    调用方终止——和解不掩盖真失败）。"""
    r = _run(sandbox, {"LABEL_RESULT": "fail", "REMOTE_LABELS": "[]"})
    assert r.returncode == 1
    assert not (sandbox / "comment.log").exists()
    assert "按已落定继续回执" not in r.stdout + r.stderr


def test_success_path_posts_receipt(sandbox):
    """快乐路径：落标成功 → 回执照常（两级语义改动不回归）。"""
    r = _run(sandbox, {"LABEL_RESULT": "ok"})
    assert r.returncode == 0, r.stderr
    log = (sandbox / "comment.log").read_text(encoding="utf-8")
    assert "factory:receipt:issue-207:rbatch" in log
    assert "[factory:rejected]" not in log  # state.py 毒丸不变量
