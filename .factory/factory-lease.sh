#!/usr/bin/env bash
# factory-lease.sh — Supabase 租约仲裁层客户端（source 引入，勿直接执行）。
#
# 三层架构（README「租约仲裁」节）：
#   仲裁 = 本库 + db/schema.sql（claim/heartbeat/release/fence，全部服务端原子）
#   投影 = GitHub labels + state.py（声明式收敛，sync 多写者安全）
#   围栏 = git refs 服务端保护（factory/* 禁 force push/禁删）
#
# 双态铁律（2026-08-24 人类决策）：
#   SUPABASE_DB 未设              = 显式选择单写者形态 → 降级本地锁
#                                  （.factory/locks/leases/，见下方降节）；
#                                  跨机互斥不存在，禁止多机运行（stderr 告警）。
#   SUPABASE_DB 已设但 psql 失败   = 配置错误 → fail-closed 拒绝动作退出，
#   / 不可达                        绝不降级——把配置错误伪装成单写者形态
#                                  等于重新打开多写者竞态。
#
# 环境变量：
#   SUPABASE_DB          PG 连接串（Supabase pooler 或任何 Postgres）；未设=单写者降级
#   FACTORY_LEASE_SECS   租期秒数（默认 900 = 15min，心跳 60s 的 15 倍余量）
#   FACTORY_HB_INTERVAL  心跳间隔秒数（默认 60）
#
# 调用方契约：REPO 已定义（git 仓库根）。兼容 bash 3.2（macOS）。
[ -n "${__FACTORY_LEASE_SH:-}" ] && return 0
__FACTORY_LEASE_SH=1

lease_db() {  # 打印连接串；未配置即失败（PG 路径 fail-closed；单写者降级在各操作入口分支，不经此）
  if [ -z "${SUPABASE_DB:-}" ]; then
    echo "[error] SUPABASE_DB 未设置：仲裁层缺失，fail-closed 拒绝动作（README「租约仲裁」）" >&2
    return 1
  fi
  printf '%s' "$SUPABASE_DB"
}

lease_psql() {  # lease_psql <sql> [psql-args...] —— 单语句执行；任何错误都是失败
  # 额外参数透传：调用方用 -v k=... + SQL :'k' 参数化（PR#34 审查修复），
  # 杜绝值字符串拼接进 SECURITY DEFINER 函数的注入面。
  local sql="$1"; shift
  psql "$(lease_db)" -X -q -tA -v ON_ERROR_STOP=1 "$@" -c "$sql"
}

lease_key_sane() {  # 键/机器 ID 白名单 [A-Za-z0-9._:-]（SQL 注入面收口）
  case "$1" in
    *[!A-Za-z0-9._:-]*) return 1 ;;
    "") return 1 ;;
  esac
  return 0
}

lease_main_factory() {  # 主树 .factory 绝对路径：git-common-dir 锚定（worktree 回主树，
  # 对齐 dispatch.sh 硬锁路径解析——锁/身份随主 .git 走，各 worktree 互见）；
  # 非 git 环境退回 REPO/.factory
  local mf
  mf="$(git -C "${REPO}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null \
    | sed 's#/\.git$##' || true)"
  printf '%s/.factory' "${mf:-${REPO}}"
}

lease_machine_id() {  # 稳定机器身份：主树 .factory/var/machine-id（非 PID）
  # PID 是机器局部命名空间，跨机不可判活性；machine-id 跟主 .git 走，
  # worktree 共享（lease_main_factory 锚定）。
  local f tmp mid
  f="$(lease_main_factory)/var/machine-id"
  if [ ! -s "$f" ]; then
    mkdir -p "${f%/*}"
    tmp="${f}.tmp.$$"
    ( umask 077; python3 -c 'import uuid; print(uuid.uuid4().hex)' > "$tmp" ) \
      && mv "$tmp" "$f" || { rm -f "$tmp"; echo "[error] machine-id 生成失败" >&2; return 1; }
  fi
  mid="$(cat "$f")"
  # 内容校验（同键白名单，PR#34 审查修复）：文件被篡改含引号/SQL 语法 =
  # 完整性事故，fail-closed 拒绝——不静默重生成（那会掩盖事故并遗孤儿租约）
  lease_key_sane "$mid" || { echo "[error] machine-id 内容非法（疑似篡改）：${f}" >&2; return 1; }
  printf '%s\n' "$mid"
}

# ── 单写者降级（SUPABASE_DB 未设 = 显式单写者形态，2026-08-24）───────
# 本地锁镜像仲裁层语义：O_EXCL 判代、过期 = mtime+锁内租期（内容第 5
# 字段，缺省回退 FACTORY_LEASE_SECS——旧 4 字段锁兼容）、过期可夺
# （epoch+1，rename 单赢家接管——rm 后建新有双赢家窗口）、fence 校验
# machine-id+epoch、heartbeat 续租写回新租期+刷 mtime
# （过期不许复活，须重新 claim——对齐 PG）。锁锚定主树
# .factory/locks/leases/（lease_main_factory，worktree 共享）。两处刻意
# 差异：①持有中二次 claim 即便同机也拒——本地锁的互斥对象就是同机进程，
# PG 的同机续约语义在这里恰是要防的双链并发；②epoch 计数器
# （<key>.epoch）跨 release 单调不回零，对齐 PG 行常驻语义（fencing
# token 永不复活）。跨机互斥不存在：本地锁互不可见，每个降级路径 stderr
# 显式告警。已设 SUPABASE_DB 但 psql 不可达不走此路径（配置错误，
# fail-closed 由 PG 路径维持）。

_lease_sw_notice() {  # 每个降级路径必打：显式声明互斥边界
  echo "[lease] single-writer mode: local lock (SUPABASE_DB unset); do NOT run factory on multiple machines" >&2
}

if [ "$(uname -s)" = "Darwin" ]; then
  _lease_mtime() { stat -f %m "$1" 2>/dev/null; }  # macOS
else
  _lease_mtime() { stat -c %Y "$1" 2>/dev/null; }  # Linux
fi

_lease_sw_path() {  # _lease_sw_path <key> <后缀 .lock|.epoch> → 主树锁目录下路径
  printf '%s/locks/leases/%s%s' "$(lease_main_factory)" "$1" "$2"
}

_lease_sw_read() {  # _lease_sw_read <lock> → 置 _SW_MID/_SW_EPOCH/_SW_SECS；缺文件/坏内容 return 1
  local line _pid _ts
  IFS= read -r line < "$1" 2>/dev/null || return 1
  _SW_MID="${line%%|*}"; _SW_EPOCH="${line#*|}"; _SW_EPOCH="${_SW_EPOCH%%|*}"
  case "${_SW_EPOCH}" in ''|*[!0-9]*) return 1 ;; esac
  # 第 5 字段 = 本租约租期（claim/hb 写入）。旧 4 字段锁（mid|epoch|pid|ts）
  # 无此字段 → 空 = 回退 FACTORY_LEASE_SECS 判过期（PR #53 审查③）。
  IFS='|' read -r _pid _ts _SW_SECS <<< "${line#*|*|}"
  case "${_SW_SECS}" in ''|*[!0-9]*) _SW_SECS="" ;; esac
  [ -n "$_SW_MID" ] || return 1
}

_lease_sw_fresh() {  # _lease_sw_fresh <mtime> → 0=未过期 1=已过期；租期=锁内 _SW_SECS，缺省回退全局默认
  local now; now="$(date +%s)"
  [ $(( $1 + ${_SW_SECS:-${FACTORY_LEASE_SECS:-900}} )) -gt "$now" ]
}

_lease_sw_restore() {  # <src 墓碑/残本> <dst 锁位> → 不可覆盖放回：ln 原子判位后统一 rm 源
  # 检查-移动（[ -e ] || mv）在检查与 mv 之间可被并发 claimer 占位，mv 会覆盖
  # 新主锁（双赢家）；ln 硬链原子（dst 已存在即失败）——成功=dst 得内容删源链；
  # 失败=位上有更新主，弃残本（其主 hb/fence 自毙，单写者仍成立）。
  ln "$1" "$2" 2>/dev/null || true
  rm -f "$1"
}

_lease_sw_claim() {  # <key> <secs> <mid> → 成功打印 epoch，失败 return 1
  local key="$1" secs="$2" mid="$3"
  local lock ctr mt held last new_ep stale
  _lease_sw_notice
  lock="$(_lease_sw_path "$key" .lock)"; ctr="$(_lease_sw_path "$key" .epoch)"
  mkdir -p "${lock%/*}" || return 1
  # 墓碑调和（PR #116 CodeRabbit）：release 在 mv 后/放回前被 SIGKILL → .rel.*
  # 会截留仍有效（新鲜）的持有者锁。建主锁前先处理：新鲜墓碑 = 活锁被截留
  # → 不可覆盖放回（_lease_sw_restore 的 ln 判位；随后正常流程读新鲜即拒，
  # ≤ 租期后自解）；过期/坏内容 = 死锁残渣 → 清理。
  for tomb in "${lock}".rel.*; do
    [ -e "$tomb" ] || continue
    _SW_MID=; _SW_EPOCH=; _SW_SECS=""
    if _lease_sw_read "$tomb"; then
      mt="$(_lease_mtime "$tomb")"
      case "$mt" in ''|*[!0-9]*) rm -f "$tomb"; continue ;; esac
      if _lease_sw_fresh "$mt"; then
        _lease_sw_restore "$tomb" "$lock"
        continue
      fi
    fi
    rm -f "$tomb"
  done
  held=0; _SW_MID=; _SW_EPOCH=; _SW_SECS="$secs"   # 读失败时新鲜度按本 claim 租期判（原语义）
  if [ -f "$lock" ]; then
    _lease_sw_read "$lock" || true     # 坏内容 → held=0（判代退回计数器）
    [ -n "${_SW_EPOCH}" ] && held="$_SW_EPOCH"
    mt="$(_lease_mtime "$lock")"
    case "$mt" in ''|*[!0-9]*) return 1 ;; esac
    # 未过期 = 拒（同机并发也拒，见上方差异①）
    _lease_sw_fresh "$mt" && return 1
    # 原子接管（单赢家，PR #53 审查①）：rename 是唯一通道——并发竞争者
    # 只有一个 mv 成功，输者 mv 失败（源路径已不在）即拒。绝不能 rm 后
    # 再建：rm-建新窗口里后来者会删掉先来者刚建的锁，双赢家破坏单写者。
    stale="${lock}.stale.$$.$RANDOM"
    mv "$lock" "$stale" 2>/dev/null || return 1
    # 防偷鲜锁：过期检查与 mv 之间可能有人刚换上未过期新锁——对搬走的
    # 文件重验新鲜度（内容随 inode 走，_SW_* 仍有效）；偷到鲜锁则放回
    # 并拒（放回位已有新锁则弃残本——输者 hb/fence 自毙，单写者仍成立）。
    mt="$(_lease_mtime "$stale")"
    if _lease_sw_fresh "$mt"; then
      _lease_sw_restore "$stale" "$lock"
      return 1
    fi
    rm -f "$stale"
  fi
  ( set -C; : > "$lock" ) 2>/dev/null || return 1  # 原子判代（noclobber = O_EXCL）
  # fencing token 单调：max(计数器, 旧锁 epoch)+1（见上方差异②）
  last=0
  if [ -f "$ctr" ]; then
    last="$(cat "$ctr" 2>/dev/null)"
    case "$last" in ''|*[!0-9]*) last=0 ;; esac
  fi
  [ "$held" -gt "$last" ] && last="$held"
  new_ep=$(( last + 1 ))
  printf '%s\n' "$new_ep" > "$ctr" 2>/dev/null || { rm -f "$lock"; return 1; }
  printf '%s|%s|%s|%s|%s\n' "$mid" "$new_ep" "$$" "$(date +%s)" "$secs" > "$lock"
  printf '%s\n' "$new_ep"
}

_lease_sw_hb() {  # <key> <epoch> <mid> <secs> → 0=活 1=失效
  local key="$1" epoch="$2" mid="$3" secs="$4" lock mt tmp
  _lease_sw_notice
  lock="$(_lease_sw_path "$key" .lock)"
  [ -f "$lock" ] || return 1
  _lease_sw_read "$lock" || return 1
  [ "$_SW_MID" = "$mid" ] && [ "$_SW_EPOCH" = "$epoch" ] || return 1
  mt="$(_lease_mtime "$lock")"
  case "$mt" in ''|*[!0-9]*) return 1 ;; esac
  _lease_sw_fresh "$mt" || return 1  # 过期不许复活，须重新 claim（对齐 PG）
  # 续租租期写回锁内（hb 的 secs 即新租期，对齐 PG heartbeat(p_secs)；
  # 兼职把旧 4 字段锁升级为带租期格式）：temp+mv 原子替换防撕裂读，mv
  # 保留 temp 的 mtime，故随后 touch 刷活。重写失败退化为纯 touch 续租
  # （旧租期继续生效）——续租写失败不该杀活链。
  tmp="${lock}.hb.$$.$RANDOM"
  if printf '%s|%s|%s|%s|%s\n' "$mid" "$epoch" "$$" "$(date +%s)" "$secs" \
       > "$tmp" 2>/dev/null && mv -f "$tmp" "$lock" 2>/dev/null; then
    touch "$lock"
  else
    rm -f "$tmp" 2>/dev/null
    touch "$lock"
  fi
}

_lease_sw_fence() {  # <key> <epoch> <mid> → 0=仍持有 1=已被夺走/过期
  local key="$1" epoch="$2" mid="$3" lock mt
  _lease_sw_notice
  lock="$(_lease_sw_path "$key" .lock)"
  [ -f "$lock" ] || return 1
  _lease_sw_read "$lock" || return 1
  [ "$_SW_MID" = "$mid" ] && [ "$_SW_EPOCH" = "$epoch" ] || return 1
  mt="$(_lease_mtime "$lock")"
  case "$mt" in ''|*[!0-9]*) return 1 ;; esac
  # 过期即失效（对齐 PG fence expires_at>now）：租期取锁内实际值——短租期
  # 租约不被全局默认租期撑腰（PR #53 审查③）；旧 4 字段锁回退默认。
  _lease_sw_fresh "$mt"
}

_lease_sw_release() {  # <key> <epoch> <mid> → 尽力释放（幂等）：持有者匹配才删锁，计数器留档
  local key="$1" epoch="$2" mid="$3" lock tomb
  _lease_sw_notice
  lock="$(_lease_sw_path "$key" .lock)"
  [ -f "$lock" ] || return 0
  _lease_sw_read "$lock" || return 0
  [ "$_SW_MID" = "$mid" ] && [ "$_SW_EPOCH" = "$epoch" ] || return 0
  # 原子释放（对齐 claim 的 rename 协议）：读-验-rm 非原子——验证与
  # rm 之间锁可过期被新 claimer 接管（mv 走旧 inode + O_EXCL 建新锁），
  # rm -f 按路径删掉的是新主的锁（单写者破坏，web-tools#5 Sourcery）。
  # 先 mv 到唯一墓碑（单赢家），对墓碑重验内容（随 inode 走）：仍是我
  # → 删墓碑；已非我（误搬新主锁）→ 位空则放回、位占则弃残本——
  # 绝不删位上现有锁。
  tomb="${lock}.rel.$$.$RANDOM"
  mv "$lock" "$tomb" 2>/dev/null || return 0
  _lease_sw_read "$tomb" || { rm -f "$tomb"; return 0; }
  if [ "$_SW_MID" = "$mid" ] && [ "$_SW_EPOCH" = "$epoch" ]; then
    rm -f "$tomb"
  else
    # 放回语义见 _lease_sw_restore：ln 原子判位，绝不 mv 覆盖并发新主
    _lease_sw_restore "$tomb" "$lock"
  fi
  return 0
}

lease_claim() {  # lease_claim <key> [secs] —— 成功打印 epoch，失败 return 1
  local key="$1" secs="${2:-${FACTORY_LEASE_SECS:-900}}" mid out epoch
  lease_key_sane "$key" || { echo "[error] 非法租约键: ${key}" >&2; return 1; }
  case "$secs" in ''|*[!0-9]*) echo "[error] 非法租期秒数: ${secs}" >&2; return 1 ;; esac
  mid="$(lease_machine_id)" || return 1
  if [ -z "${SUPABASE_DB:-}" ]; then  # 单写者降级（显式选择，非配置错误；双态铁律见头部）
    _lease_sw_claim "$key" "$secs" "$mid"
    return
  fi
  out="$(lease_psql "select * from factory_claim(:'k',:'m',${secs})" -v k="$key" -v m="$mid")" \
    || { echo "[error] 租约仲裁不可达（key=${key}），fail-closed" >&2; return 1; }
  # 输出形如 "t|3"（o_won|o_epoch）；未赢（f|-1）与解析异常一律 return 1
  [ "${out%%|*}" = "t" ] || return 1
  epoch="${out##*|}"
  case "$epoch" in ''|*[!0-9]*) return 1 ;; esac
  [ "$epoch" -gt 0 ] || return 1
  printf '%s\n' "$epoch"
}

lease_heartbeat() {  # lease_heartbeat <key> <epoch> [secs] —— 0=活 1=已被夺走
  local key="$1" epoch="$2" secs="${3:-${FACTORY_LEASE_SECS:-900}}" mid
  lease_key_sane "$key" && lease_key_sane "$epoch" || return 1
  case "$secs" in ''|*[!0-9]*) return 1 ;; esac
  mid="$(lease_machine_id)" || return 1
  if [ -z "${SUPABASE_DB:-}" ]; then
    _lease_sw_hb "$key" "$epoch" "$mid" "$secs"
    return
  fi
  lease_psql "select factory_heartbeat(:'k',:'m',${epoch},${secs})" -v k="$key" -v m="$mid" | grep -qx t
}

lease_fence_ok() {  # lease_fence_ok <key> <epoch> —— 0=仍持有 1=已被夺走
  local key="$1" epoch="$2" mid
  lease_key_sane "$key" && lease_key_sane "$epoch" || return 1
  mid="$(lease_machine_id)" || return 1
  if [ -z "${SUPABASE_DB:-}" ]; then
    _lease_sw_fence "$key" "$epoch" "$mid"
    return
  fi
  lease_psql "select factory_fence_ok(:'k',:'m',${epoch})" -v k="$key" -v m="$mid" | grep -qx t
}

lease_release() {  # lease_release <key> <epoch> —— 尽力释放（幂等）
  local key="$1" epoch="$2" mid
  lease_key_sane "$key" && lease_key_sane "$epoch" || return 1
  mid="$(lease_machine_id)" || return 1
  if [ -z "${SUPABASE_DB:-}" ]; then
    _lease_sw_release "$key" "$epoch" "$mid"
    return
  fi
  lease_psql "select factory_release(:'k',:'m',${epoch})" -v k="$key" -v m="$mid" >/dev/null
}

lease_guard() {  # 副作用出口围栏：租约失效即拒绝（诈尸/被吊销防护）
  # 无租约上下文（LEASE_KEY 未设，如本地直跑测试）不拦——拦是链的义务，
  # 不是库的义务；设了就必须过。
  [ -z "${LEASE_KEY:-}" ] && return 0
  lease_fence_ok "${LEASE_KEY}" "${LEASE_EPOCH}"
}

lease_heartbeat_loop() {  # lease_heartbeat_loop <key> <epoch> —— 后台心跳
  # 失效即向父进程（链）发 TERM；链须有 `trap 'exit n' TERM` 使 EXIT trap 级联。
  # 父进程消亡则自退（防孤儿心跳）。
  local key="$1" epoch="$2"
  local int="${FACTORY_HB_INTERVAL:-60}" secs="${FACTORY_LEASE_SECS:-900}"
  (
    while :; do
      sleep "$int"
      kill -0 "$PPID" 2>/dev/null || exit 0
      if ! lease_heartbeat "$key" "$epoch" "$secs"; then
        echo "[lease] 租约失效：key=${key} epoch=${epoch}（被夺/吊销/过期），TERM 链" >&2
        kill -TERM "$PPID" 2>/dev/null
        exit 1
      fi
    done
  ) &
  LEASE_HB_PID=$!
}

lease_cleanup() {  # EXIT trap 用：停心跳 + 尽力释放；永不失败
  [ -n "${LEASE_HB_PID:-}" ] && kill "${LEASE_HB_PID}" 2>/dev/null
  if [ -n "${LEASE_KEY:-}" ] && [ -n "${LEASE_EPOCH:-}" ]; then
    lease_release "${LEASE_KEY}" "${LEASE_EPOCH}" >/dev/null 2>&1 || true
  fi
  return 0
}
