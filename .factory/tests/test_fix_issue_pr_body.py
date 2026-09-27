"""fix-issue.sh 建 PR 正文须含 Closes #${ISSUE}（链约定，state.py _linked_issue 消费）。

回归锚：d6e6b57「PR 评审修复波」误删 --body-file 行 → PR 无正文、
合并后 issue 不自动关（CodeRabbit xx-skills#14 实锤，正文原文经 git
历史还原）。整链 mock 建 PR 成本高于收益，此守卫以源文本锚定最小
契约面（脚本即执行计划）：body 行丢失即测试失败。
"""
from pathlib import Path

FIX = Path(__file__).resolve().parent.parent / "fix-issue.sh"
SRC = FIX.read_text(encoding="utf-8")


def test_pr_create_carries_closes_body():
    # 完整契约行（截取 body 起始即可：误删/改前缀均失配）
    body = '--body-file <(echo "Closes #${ISSUE}"; echo;'
    assert body in SRC, "pr create 必须带 Closes body（链约定：PR body 含 Closes #N）"


def test_pr_create_keeps_base_and_label_contract():
    """评审波新增契约（显式 --base / needs-review label）与 body 共存。"""
    assert '--base "${BASE_BRANCH}"' in SRC
    assert '--label "factory:needs-review"' in SRC


def test_pr_body_carries_dir_and_chain_summary():
    """CodeRabbit #119：body 除 Closes 前缀外还须含产物目录与链流程说明
    （人工 reviewer 定位产物/理解流程的正文契约）。"""
    assert '工厂链产物见 ${DIR}' in SRC
    assert "implement ↔ review（ralph ≤${RALPH_MAX} 轮）→ guard → holdout" in SRC
