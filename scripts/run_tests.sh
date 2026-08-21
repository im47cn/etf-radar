#!/usr/bin/env bash
# 全量测试门: 与 scripts/hooks/pre-push 和 CI 同口径的完整门禁。
# 工厂链(.factory)与人工均可调用; 退出码非零 = 门失败。
#
# 用法:
#   scripts/run_tests.sh [--no-lock]              # 全量门(mypy/ruff/pytest+tsc/eslint/vitest+diff-cover)
#   scripts/run_tests.sh --evidence <suite>       # 单套件 verbose 证据段(holdout 证据源)
#     suite: backend  → uv run --all-extras pytest -v
#     suite: frontend → npx vitest run --reporter=verbose
#
# 对比基准: BASE 环境变量, 默认 origin/main
# --no-lock: 兼容工厂提示词的 final_gate 形参, 本仓库无锁, 接受并忽略
set -euo pipefail

REPO=$(git rev-parse --show-toplevel)
BASE="${BASE:-origin/main}"
FAIL_UNDER=95

cd "$REPO"

backend_gate() {
  echo "▶ backend: mypy (strict, 与项目规则一致)"
  (cd backend && uv run --all-extras mypy src)
  echo "▶ backend: ruff (与 CI 同口径)"
  (cd backend && uv run ruff check src tests scripts)
  echo "▶ backend: pytest --cov"
  (cd backend && uv run --all-extras pytest --cov=src --cov-report=xml:coverage.xml -q)
  (cd backend && uv run --all-extras diff-cover coverage.xml --compare-branch="$BASE" --fail-under="$FAIL_UNDER")
}

frontend_gate() {
  echo "▶ frontend: tsc -b (与 deploy-frontend build 一致)"
  (cd frontend && npx tsc -b)
  echo "▶ frontend: eslint (与 CI 同口径)"
  (cd frontend && npm run lint)
  echo "▶ frontend: vitest --coverage"
  (cd frontend && npx vitest run --coverage)
  # lcov SF 是 frontend-relative, diff-cover 需要 repo-relative, 加前缀匹配
  sed -i.bak 's|^SF:src/|SF:frontend/src/|' "$REPO/frontend/coverage/lcov.info" 2>/dev/null || true
  rm -f "$REPO/frontend/coverage/lcov.info.bak"
  (cd backend && uv run --all-extras diff-cover "$REPO/frontend/coverage/lcov.info" --compare-branch="$BASE" --fail-under="$FAIL_UNDER")
}

# --- 证据段模式: 单套件 verbose, 供 fix-issue 链 tests-output.txt 附加 ---
if [ "${1:-}" = "--evidence" ]; then
  suite="${2:?用法: run_tests.sh --evidence backend|frontend}"
  case "$suite" in
    backend)  (cd backend && uv run --all-extras pytest -o addopts= -v) ;;
    frontend) (cd frontend && npx vitest run --reporter=verbose) ;;
    *) echo "未知套件: $suite (backend|frontend)" >&2; exit 2 ;;
  esac
  exit 0
fi

[ "${1:-}" = "--no-lock" ] || { [ $# -eq 0 ] || { echo "未知参数: $1" >&2; exit 2; }; }

backend_gate
frontend_gate
echo "✓ 全量门通过 (mypy+ruff+pytest+tsc+eslint+vitest, diff-cover ≥${FAIL_UNDER}%, 对比 ${BASE})"
