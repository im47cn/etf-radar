#!/usr/bin/env bash
# sync-from-upstream.sh — 下游从上游仓库拉取 .factory 工具链。
#
# 定位：替代「移植后手工 diff 对账」。上游是唯一真相源（.factory/
# DISTRIBUTION.json 分类），本脚本按分类三态处理：
#   full  文件：--apply 直接覆盖（零本地化）；--check 漂移即失败（门禁）
#   local 文件：永不覆盖；报告与上游的 diff 摘要，人工合并
#               （漂移的正道是 feedback-upstream 反哺，不是静默分叉）
#   skip  文件：不看（仓特定/运行时产物）
#
# 用法: sync-from-upstream.sh <upstream-path> [--check | --apply] [--anchor <ref>]
#                       [--repo <path>] [--commit]
#   upstream-path  上游仓路径（工作树或 bare 仓均可——经 git show 读取）
#   --check        只报告漂移；full 文件有漂移 exit 1（可挂 CI/gauntlet）
#   --apply        full 覆盖 + local diff 摘要；写 upstream-lock.json 锚点
#   --anchor <ref> 用指定上游 ref（默认：upstream-lock.json 锚点 → main）
#   --repo <path>  目标仓（默认：当前目录所属仓）——中心仓巡检以此驱动
#                  下游追平，始终执行中心版脚本，免疫下游副本滞后
#   --commit       仅与 --apply 组合：追平产物+锚点+blame-ignore 以单提交
#                  落库（factory: 上游同步追平（<sha9>）），落在当前分支不推送；
#                  提交无法含自身 SHA，blame-ignore 滞后一条（本次记上次）
#
# 退出码: 0=干净/已同步  1=有漂移（--check）或应用失败  2=用法/上游不可用
#
# 首次移植仍走 README「移植到其他仓库」四步（MISSION/PERIMETER/测试门/
# 重证 kill rate）；本脚本管的是此后的一切增量。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

UP="${1:-}"; MODE="check"; ANCHOR=""; REPO_ARG=""; COMMIT=0
[ -n "$UP" ] || { sed -n '2,26p' "$0" >&2; exit 2; }
shift
while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --apply) MODE="apply" ;;
    --anchor) ANCHOR="${2:-}"; shift ;;
    --repo) REPO_ARG="${2:-}"
            [ -n "$REPO_ARG" ] || { echo "--repo 缺路径参数" >&2; exit 2; }
            shift ;;
    --commit) COMMIT=1 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
  shift
done
[ "$COMMIT" = 0 ] || [ "$MODE" = apply ] \
  || { echo "--commit 仅与 --apply 组合使用" >&2; exit 2; }

if [ -n "$REPO_ARG" ]; then
  [ -d "$REPO_ARG" ] || { echo "目标仓目录不存在: $REPO_ARG" >&2; exit 2; }
  # 规范化到仓根（PR #106 评论 2）：toplevel 校验与捕获一步完成——
  # 子目录入参不得令 FACTORY/锁/分发目标错位到 <subdir>/.factory
  REPO="$(git -C "$REPO_ARG" rev-parse --show-toplevel)" \
    || { echo "目标仓不是 git 仓库: $REPO_ARG" >&2; exit 2; }
else
  REPO="$(git rev-parse --show-toplevel)"
fi
FACTORY="$REPO/.factory"
LOCKFILE="$FACTORY/upstream-lock.json"

# 上游可用性（bare 仓无工作树，一律经 git 对象库读）
git -C "$UP" rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "上游仓不可用: $UP" >&2; exit 2; }

# --commit 前置脏检查（fail-closed）：目标仓 .factory 有未提交 tracked 改动
# 即拒绝——自动提交会淹没热修；热修正道是先落库或走 feedback-upstream 反哺
if [ "$MODE" = apply ] && [ "$COMMIT" = 1 ]; then
  dirty="$(git -C "$REPO" status --porcelain -- .factory | grep -v '^??' || true)"
  [ -z "$dirty" ] || {
    echo "拒绝 --commit：目标仓 .factory 有未提交改动（先落库或反哺）:" >&2
    printf '%s\n' "$dirty" >&2
    exit 1
  }
  # 提交阶段会无条件 git add 根目录 .git-blame-ignore-revs（blame 消噪
  # 清单，不在 .factory 面）——其 tracked 修改或人工 untracked 内容会被
  # 并入同步提交而淹没本地改动（Sourcery PR#14 评论 2）。放行仅限脚本
  # 首建残留：untracked 单行注释头（设计随下一次真追平的 add 一并入库，
  # PR #105 评论 1 锚定）；tracked 改动 / staged / 人工 untracked 均拒绝
  ignore_state="$(git -C "$REPO" status --porcelain -- .git-blame-ignore-revs || true)"
  if [ -n "$ignore_state" ]; then
    IGNORE_FILE="$REPO/.git-blame-ignore-revs"
    if ! { printf '%s\n' "$ignore_state" | grep -q '^?? ' \
        && [ -f "$IGNORE_FILE" ] \
        && cmp -s "$IGNORE_FILE" <(printf '%s\n' '# factory: 追平提交忽略清单（git blame --ignore-revs 消噪）'); }; then
      echo "拒绝 --commit：目标仓 .git-blame-ignore-revs 有未提交改动（先落库或反哺）:" >&2
      printf '%s\n' "$ignore_state" >&2
      exit 1
    fi
  fi
fi

# 锚点解析：--anchor > 上次 lock > main（优先级左→右；下游迁移
# sync 实测：lock 读取无条件覆盖会把 --anchor main 吞掉——只在未显式
# 指定时才读 lock，--anchor 成为唯一强制追新出口）
if [ -z "${ANCHOR:-}" ]; then
  ANCHOR="$(python3 -c '
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
try: print(json.loads(p.read_text())["anchor"])
except Exception: pass' "$LOCKFILE" 2>/dev/null || true)"
fi
[ -n "$ANCHOR" ] && git -C "$UP" rev-parse --verify -q "$ANCHOR^{commit}" >/dev/null \
  || ANCHOR="main"
git -C "$UP" rev-parse --verify -q "$ANCHOR^{commit}" >/dev/null \
  || { echo "上游锚点不可解析: $ANCHOR" >&2; exit 2; }
HEAD_SHA="$(git -C "$UP" rev-parse "$ANCHOR^{commit}")"
echo "上游: ${UP} @ ${ANCHOR} (${HEAD_SHA:0:9})"

# 分发清单——从**上游**对象库读（下游本地副本可能滞后甚至缺失；
# 清单是上游主权，锚点即版本）。无清单=上游版本旧，全部按 local。
# 展开逻辑在 factory_lib.py dist-manifest（2026-08-28 自此处 heredoc 下沉，
# 铁律 4：git 子进程编排归 Python；无清单=空输出，警告走 stderr）
DIST_FILE="$(mktemp "${TMPDIR:-/tmp}/.factory-dist.XXXXXX")"
# EXIT trap 兜底清理：Sourcery 拒绝、git 失败等 set -e 中途退出不泄漏
# /tmp 暂存文件（PR #105 评论 3）——正常退出同样兜底，显式 rm 不再需要。
# trap 紧随首个 mktemp 安装（PR #120 review 1）：第二个 mktemp（STAGE_FILE）
# 失败时首个暂存不再泄漏。未达定义处的变量以 :- 防 set -u 中断 trap。
# tmp = apply 循环 tmp+mv 的中转文件（#103）：中断即清；未入循环时未定义，
# set -u 下 :- 防 unbound（rm -f 空串为无害 no-op）
trap 'rm -f "$DIST_FILE" "${STAGE_FILE:-}" "${tmp:-}"' EXIT
STAGE_FILE="$(mktemp "${TMPDIR:-/tmp}/.factory-stage.XXXXXX")"
python3 "$SCRIPT_DIR/factory_lib.py" dist-manifest "$UP" "$HEAD_SHA" > "$DIST_FILE"

# Sourcery 回归闸（2026-08-31 事故锚：追平所取上游快照早于下游已修复版，
# 100 个已清零 issue 整体回退，PR gate 才拦截——闸前移到追平时点）。
# 语义与 sourcery-review-gate 同构：exit code（0=干净 1=有 issue 其余=异常）。
# 不解析 stdout：CLI 在管道（命令替换）下精简输出、干净时零输出，
# 人类概览（Total 表/No issues detected）仅 tty 形态存在——解析它必脆。
# 注意：多文件入参须相对路径（绝对路径仅接受单个）；点目录不可整目录扫描。
_sr_py_files() {
  (cd "$REPO" && find .factory -name '*.py' -type f | sort)
}
_sr_clean() {  # 0=干净 1=有 issue 2=CLI 异常
  local files rc
  files="$(_sr_py_files | tr '\n' ' ')"
  [ -n "$files" ] || return 0
  # 相对路径须相对 $REPO 解析：--repo 巡检场景 cwd 是中心仓，不 cd 会
  # 检查到错仓的 .factory（2026-09-01 foreign-cwd 测试暴露）
  (cd "$REPO" && sourcery review --check $files) >/dev/null 2>&1
  rc=$?
  [ "$rc" -eq 0 ] && return 0
  [ "$rc" -eq 1 ] && return 1
  return 2
}
SR_GATE_ON=0
if [ "$MODE" = apply ] && command -v sourcery >/dev/null 2>&1; then
  SR_GATE_ON=1
  # 版本口径提示（issue #104）：本地 CLI 版本与上游 CI pin 不一致时，
  # 上游已清零的快照本地可报 issue——先排除口径差异再查真实回归。
  # rc 区分（Sourcery 审查）：1=有 issue（才可能是版本口径差异）；
  # ≥2=CLI 执行失败，误诊为版本漂移会误导排查
  if _sr_clean; then
    echo "Sourcery 回归闸基线: .factory 干净"
  else
    sr_status=$?
    if [ "$sr_status" -eq 1 ]; then
      echo "Sourcery 回归闸基线: .factory 已有 issue——先清零再追平（闸口径=PR gate）。" \
           "若上游 CI 曾全绿：疑似本地 CLI 版本口径差异（本地 $(sourcery --version 2>/dev/null || echo '?') vs 上游 sourcery-review-gate.yml 的 pin），对齐版本后复跑再定" >&2
    else
      echo "Sourcery 回归闸执行失败（CLI 异常，退出码=$sr_status）——请检查本地 CLI 后重试" >&2
    fi
    exit 2
  fi
fi

# 上游 mode+blob（git show 丢 mode，覆盖后须恢复执行位）
up_tree() { git -C "$UP" ls-tree "$HEAD_SHA" -- ".factory/$1"; }

DRIFT=0; APPLIED=0; LOCAL_DIFF=0
while IFS=$'\t' read -r kind rel; do
  [ -n "$rel" ] || continue
  dst="$FACTORY/$rel"
  row="$(up_tree "$rel")"
  if [ -z "$row" ]; then
    echo "  [$kind] $rel: 上游不存在（上游已删？本地可退役）"
    continue
  fi
  up_blob="$(echo "$row" | awk '{print $3}')"
  up_mode="$(echo "$row" | awk '{print $1}')"
  if [ "${up_mode:0:2}" = "04" ]; then
    echo "  [$kind] $rel: 目录项——用例随源文件走，人工对齐（不做 blob 级处理）"
    continue
  fi
  if [ ! -f "$dst" ]; then
    echo "  [$kind] $rel: 本地缺失"
    [ "$kind" = full ] && DRIFT=1
    if [ "$MODE" = apply ] && [ "$kind" = full ]; then
      mkdir -p "$(dirname "$dst")" # 缺失父目录先建（xx-skills：tests/ 整缺，重定向即崩）
      # tmp+mv 原子替换（#103）：$dst 可能是运行中脚本自身——bash 惰性逐段
      # 读源文件，`> "$dst"` 直写截断同 inode，旧读位移落在新内容中途即
      # syntax error 半同步态；同目录 rename 换 inode，旧 inode 保活至跑完
      tmp="$(mktemp "${dst}.factory-new.XXXXXX")"
      git -C "$UP" cat-file blob "$up_blob" > "$tmp" && mv -f "$tmp" "$dst" \
        || { echo "  [$kind] $rel: 上游 blob 拉取失败" >&2; exit 2; }
      chmod "${up_mode: -3}" "$dst" 2>/dev/null || chmod +x "$dst"
      echo "    → 已补齐"; APPLIED=$((APPLIED+1)); echo "$dst" >> "$STAGE_FILE"
    fi
    continue
  fi
  loc_blob="$(git hash-object "$dst")"
  if [ "$loc_blob" = "$up_blob" ]; then
    continue  # 一致，静默
  fi
  if [ "$kind" = full ]; then
    echo "  [full] $rel: 漂移（本地未反哺的热修，或落后于上游）"
    DRIFT=1
    if [ "$MODE" = apply ]; then
      # 同 fill-in：tmp+mv 原子替换（#103）——漂移覆盖恰是自覆盖的主形态
      tmp="$(mktemp "${dst}.factory-new.XXXXXX")"
      git -C "$UP" cat-file blob "$up_blob" > "$tmp" && mv -f "$tmp" "$dst" \
        || { echo "  [full] $rel: 上游 blob 拉取失败" >&2; exit 2; }
      chmod "${up_mode: -3}" "$dst" 2>/dev/null || chmod +x "$dst"
      echo "    → 已覆盖（本地差异若有价值，请先走 feedback-upstream 反哺）"
      APPLIED=$((APPLIED+1)); echo "$dst" >> "$STAGE_FILE"
    fi
  else
    # local：只摘要，不碰
    n="$(git -C "$UP" cat-file blob "$up_blob" | diff - "$dst" 2>/dev/null | grep -c '^[<>]' || true)"
    echo "  [local] $rel: 与上游差 ${n} 行（含仓特定区，人工合并；正道=反哺后追平）"
    LOCAL_DIFF=$((LOCAL_DIFF+1))
  fi
done < "$DIST_FILE"

# 读 upstream-lock 字段；缺文件/坏 JSON/缺键一律空串（无输出 rc 0）
_lock_field() {
  python3 -c '
import json, sys
try: print(json.loads(open(sys.argv[2], encoding="utf-8").read())[sys.argv[1]])
except Exception: pass' "$1" "$LOCKFILE" 2>/dev/null || true
}

if [ "$MODE" = apply ]; then
  # 追平后 Sourcery 回归闸：.factory 必须仍清零（不写锁点，下次重跑）
  if [ "$SR_GATE_ON" = 1 ]; then
    rc=0; _sr_clean || rc=$?
    case $rc in
      0) echo "Sourcery 回归闸通过: .factory 干净" ;;
      1) echo "Sourcery 回归闸拦截: 追平把 issue 带回 .factory（上游快照含已修复回退或新问题）" >&2
         echo "  先在本地修复这批文件后重试追平，或走 feedback-upstream.sh 反哺上游（正道），" >&2
         echo "  不得以静默回退换追平。定位: sourcery review --check \$(_sr_py_files | tr '\\n' ' ')" >&2
         exit 1 ;;
      *) echo "Sourcery 回归闸计数失败（CLI 限流/异常，fail-closed 拦截）" >&2; exit 2 ;;
    esac
  fi

  # 锁点仅在内容前进时重写（APPLIED>0 或锚点/upstream 变更）——空追平
  # 不制造 synced_at 噪音提交；落库补 upstream 字段（skip 态本地路径，
  # M2 契约）。upstream 缺失/变更也触发回填（PR #106 评论 4）：旧锁
  # anchor 未变而无 upstream 时，upstream-sync-check.sh 永缺上游凭据
  old_anchor="$(_lock_field anchor)"
  old_upstream="$(_lock_field upstream)"
  if [ "$APPLIED" -gt 0 ] || [ "$old_anchor" != "$HEAD_SHA" ] || [ "$old_upstream" != "$UP" ]; then
    python3 - "$LOCKFILE" "$HEAD_SHA" "$UP" <<'PY'
import json, sys, pathlib, datetime
p = pathlib.Path(sys.argv[1])
p.write_text(json.dumps({
    "anchor": sys.argv[2],
    "upstream": sys.argv[3],
    "synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
    echo "锚点已写: $LOCKFILE @ ${HEAD_SHA:0:9}（覆盖 ${APPLIED} 个 full 文件；local 待人工 ${LOCAL_DIFF}）"
  fi

  if [ "$COMMIT" = 1 ]; then
    # blame-ignore 滞后一条：提交无法包含自身 SHA（自指无解），本次记
    # 「上一个触碰 upstream-lock.json 的提交」（即上次追平），下轮补记本次。
    # 追加仅在确有实质提交时做——否则无漂移重跑会链式生成空转噪音提交
    IGNORE="$REPO/.git-blame-ignore-revs"
    # 文件始终确保存在（config 指向不存在文件会令 blame 直接失败），但
    # 首建仅含注释头、不入 staged 面——已同步仓库首跑不得凭空制造一条
    # 仅初始化 ignore 的空提交（PR #105 评论 1）；首建留在工作树，随
    # 下一次真追平的 add 一并入库
    [ -f "$IGNORE" ] || printf '# factory: 追平提交忽略清单（git blame --ignore-revs 消噪）\n' > "$IGNORE"
    git -C "$REPO" add -- "$LOCKFILE"
    while IFS= read -r f; do
      [ -n "$f" ] && git -C "$REPO" add -- "$f"
    done < "$STAGE_FILE"
    if git -C "$REPO" diff --cached --quiet; then
      echo "无变更可提交（full 面与锚点均未前进）"
    else
      git -C "$REPO" add -- "$IGNORE"
      PREV_SYNC="$(git -C "$REPO" log -1 --format=%H -- "$LOCKFILE" 2>/dev/null || true)"
      if [ -n "$PREV_SYNC" ] && ! grep -q "^${PREV_SYNC}$" "$IGNORE" 2>/dev/null; then
        printf '# factory: 上游同步追平（%s）\n%s\n' "${HEAD_SHA:0:9}" "$PREV_SYNC" >> "$IGNORE"
        git -C "$REPO" add -- "$IGNORE"
      fi
      git -C "$REPO" commit -q -m "factory: 上游同步追平（${HEAD_SHA:0:9}）"
      echo "已提交: $(git -C "$REPO" rev-parse --short HEAD)（当前分支，不推送）"
    fi
    # 无条件设置（幂等，绝对路径）：无变更分支此前直接跳过，文件在而
    # blame 不消噪（PR #105 评论 2）
    git -C "$REPO" config blame.ignoreRevsFile "$IGNORE"
  fi
  exit 0
fi

# --check 收尾
if [ "$DRIFT" = 0 ]; then
  echo "full 面干净（local 面 ${LOCAL_DIFF} 项人工漂移不计失败）"
else
  echo "full 面有漂移：追平（--apply）或反哺（feedback-upstream.sh）二选一" >&2
  exit 1
fi
