#!/usr/bin/env bash
# 全量测试门: 与 scripts/hooks/pre-push 和 CI 同口径的完整门禁。
# 工厂链(.factory)与人工均可调用; 退出码非零 = 门失败。
#
# 用法:
#   scripts/run_tests.sh [--no-lock]              # 全量门(backend/frontend 段并行)
#   scripts/run_tests.sh --evidence <suite>       # 单套件 verbose 证据段(holdout 证据源)
#     suite: backend  → uv run --all-extras pytest -v
#     suite: frontend → npx vitest run --reporter=verbose
#   scripts/run_tests.sh --segment backend|frontend   # 单段体(并行门编排的段实现)
#
# 并行模型(ADR-016, 2026-09-27 自上游采纳): 段清单登记在
# .factory/factory-local.json parallel_gate.segments——段体(本脚本
# --segment)是门命令的单一真相源, JSON 只登记编排; 编排器 =
# .factory/factory_lib.py parallel-gate(段间 fan-out / 失败段日志保留 /
# 一次运行全量暴露失败清单)。段间无共享固定路径(backend/coverage.xml 与
# frontend/coverage/lcov.info 互不相交), 并行安全; 但禁止两个本脚本
# 实例并发(覆盖率产物路径固定会互撞)。
#
# 对比基准: BASE 环境变量, 默认 origin/main(export 供段子进程继承)
# --no-lock: 兼容工厂提示词的 final_gate 形参, 本仓库无锁, 接受并忽略
set -euo pipefail

REPO=$(git rev-parse --show-toplevel)
BASE="${BASE:-origin/main}"
FAIL_UNDER=95
export BASE FAIL_UNDER

cd "$REPO"

# factory_lib 需 ≥3.10(PEP 604 语法), 本机缺省 python3 是 3.9——逐候选
# 探测; backend/.venv 兜底(工厂链跑门时该环境必然已建)
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.14 python3.13 python3.12 python3.11 backend/.venv/bin/python; do
    if command -v "$c" >/dev/null 2>&1 \
        && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  done
fi
[ -n "$PY" ] || { echo "❌ 无 ≥3.10 的 python(factory_lib 需要), 设 PYTHON env 指定" >&2; exit 2; }

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

# --- 段体模式: 并行门 segments 的实现入口(单段完整跑, 含 diff-cover) ---
if [ "${1:-}" = "--segment" ]; then
  seg="${2:?用法: run_tests.sh --segment backend|frontend}"
  case "$seg" in
    backend)  backend_gate ;;
    frontend) frontend_gate ;;
    *) echo "未知段: $seg (backend|frontend)" >&2; exit 2 ;;
  esac
  exit 0
fi

[ "${1:-}" = "--no-lock" ] || { [ $# -eq 0 ] || { echo "未知参数: $1" >&2; exit 2; }; }

# --- 组合方: 并行门编排 + 统一裁决(失败清单一次全量暴露) ---
FAILED=()  # 先于 trap 注册(set -u 下 trap 引用 ${#FAILED[@]}, 提前退出不 unbound)
rc=0       # 先于 trap 注册: trap 串内 rc=$? 对 shellcheck 静态不可见(SC2154 消音)
trap 'rc=$?; if [ $rc -ne 0 ] || [ "${#FAILED[@]}" -gt 0 ]; then
  echo "❌ run_tests 失败 (rc=$rc)" >&2
fi' EXIT

FAILED_TAGS="$(mktemp "${TMPDIR:-/tmp}/etf-run-tags.XXXXXX")" || exit 2
PAR_RC=0
"$PY" .factory/factory_lib.py parallel-gate --failed-tags "$FAILED_TAGS" || PAR_RC=$?
if [ "$PAR_RC" -eq 2 ]; then
  rm -f "$FAILED_TAGS"
  echo "❌ 并行门配置错误(factory-local.json parallel_gate, fail-closed)" >&2
  exit 2
fi
if [ "$PAR_RC" -ne 0 ]; then
  # 编排器已按段序回放失败段日志; 此处回收 tag, 末尾统一裁决
  while IFS= read -r t; do
    [ -n "$t" ] && FAILED+=("$t")
  done < "$FAILED_TAGS"
fi
rm -f "$FAILED_TAGS"

if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "❌ 门禁失败: ${FAILED[*]}" >&2
  exit 1
fi
echo "✓ 全量门通过 (backend/frontend 并行, mypy+ruff+pytest+tsc+eslint+vitest, diff-cover ≥${FAIL_UNDER}%, 对比 ${BASE})"
