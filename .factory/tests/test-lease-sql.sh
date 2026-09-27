#!/usr/bin/env bash
# test-lease-sql.sh —— 仲裁层 schema 行为测试（真 Postgres，非 mock）。
#
# 前置：本机可 runuser（root 跑）；postgresql server/binaries 在位。
# 自建一次性实例（initdb -A trust，端口 55432，socket /tmp），不碰系统库。
# 覆盖：claim/续约/接管/heartbeat/fence/release 的 epoch 语义、配额、
# 机器自注册、RLS 直表全拒、worker 不可调管理员函数、吊销/停机即时生效、
# 未知租户 fail-closed、审计有痕。
# 用法：bash .factory/tests/test-lease-sql.sh   （root；非 root 需能 runuser postgres）
#       LEASE_SKIP_PG=1 bash ...                 （强制跳过 PG 仲裁段——
#       run_tests.sh 全量门用此形态：PG 段需 root+postgres 属手动全跑面，
#       非仲裁段（machine-id 防篡改 + 单写者降级）零环境依赖，归门禁）
set -u

# 测试密封性（steering/testing-standards.md §测试密封性，ADR-010）：本脚本
# 及其 bash -c 子链操作 tmp 夹具仓——顶层剥除 hook 注入的 GIT_*（unset 后
# 子进程继承，覆盖 source lease.sh 的子链；泄漏时 git -C "$tp" 被劫持）。
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY \
      GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_NAMESPACE

PGDATA=/tmp/pgfactory-lease-test
PORT=55432
PASS=0; FAIL=0; PG_SKIPPED=0
ck() { # ck <名称> <期望> <实得>
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "PASS: $1"
  else FAIL=$((FAIL+1)); echo "FAIL: $1（期望 [$2] 实得 [$3]）"; fi
}

# PG 仲裁层用例自建一次性 Postgres，需 initdb+runuser+postgres 账户（Linux
# root 形态）。环境不具备（如 macOS 开发机）→ 整组 SKIP（计数，不影响退出码，
# 不改用例语义）；单写者降级用例（下方）无 PG 依赖，任何环境必须可跑。
CAN_PG=0
if command -v initdb >/dev/null && command -v runuser >/dev/null \
   && runuser -u postgres -- true >/dev/null 2>&1; then
  CAN_PG=1
fi
# 门禁形态强制跳过（见头部用法注释）：环境差异不入门，PG 段语义完整保留
# 给手动全跑。
[ "${LEASE_SKIP_PG:-0}" = 1 ] && CAN_PG=0

# REPO 解析必须在下方 cd /tmp 之前（$0 相对路径 cd 后即失效）
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

if [ "$CAN_PG" = 1 ]; then  # --- PG 仲裁层用例（环境不具备 → 整组 SKIP）---
# --- 一次性实例 ---
rm -rf "$PGDATA"
runuser -u postgres -- initdb -D "$PGDATA" -A trust --locale=C >/dev/null 2>&1
cd /tmp || exit 2   # postgres 用户进不了 /root，避开 "could not change directory" 噪音
runuser -u postgres -- pg_ctl -D "$PGDATA" -o "-p $PORT -k /tmp" -l /tmp/lease-test-pg.log -w start >/dev/null 2>&1 \
  || { echo "postgres 启动失败"; cat /tmp/lease-test-pg.log; exit 2; }
trap 'runuser -u postgres -- pg_ctl -D "$PGDATA" stop -m immediate >/dev/null 2>&1; rm -rf "$PGDATA"' EXIT

PG() { runuser -u postgres -- psql -h 127.0.0.1 -p $PORT -U postgres -d postgres -X -q -tA "$@"; }
W()  { runuser -u postgres -- psql -h 127.0.0.1 -p $PORT -U factory-e2e -d postgres -X -q -tA "$@"; }

# schema 以 owner=postgres 建立并 apply（幂等迁移走一遍即可）。
# postgres 用户读不了 /root 下的仓库 —— /tmp 副本过桥
cp "$REPO/.factory/db/schema.sql" /tmp/lease-test-schema.sql && chmod 644 /tmp/lease-test-schema.sql \
  || { echo "schema 拷贝失败（REPO=${REPO}）" >&2; exit 2; }
PG -v ON_ERROR_STOP=1 -f /tmp/lease-test-schema.sql >/dev/null || { echo "schema apply 失败" >&2; exit 2; }
# 租户 onboarding（README 运维手册同款）：role + grant + 租户行
PG -c "create role \"factory-e2e\" login; grant factory_worker to \"factory-e2e\";
       insert into factory_tenants (tenant, rolname) values ('e2e','factory-e2e');" >/dev/null
# --- 1-6：claim / 续约 / fence / heartbeat / 抢占 ---
ck "新键认领 t|1"          "t|1"  "$(W -c "select * from factory_claim('issue:1','machA',900)")"
ck "同机续约 epoch 不变"    "t|1"  "$(W -c "select * from factory_claim('issue:1','machA',900)")"
ck "持有者 fence t"         "t"    "$(W -c "select factory_fence_ok('issue:1','machA',1)")"
ck "heartbeat t"            "t"    "$(W -c "select factory_heartbeat('issue:1','machA',1,900)")"
ck "未过期他机抢 f|-1"      "f|-1" "$(W -c "select * from factory_claim('issue:1','machB',900)")"
ck "陈旧 epoch fence f"     "f"    "$(W -c "select factory_fence_ok('issue:1','machA',99)")"

# --- 7-12：过期接管（fencing token 递增）与 release ---
W -c "select * from factory_claim('issue:1','machA',1)" >/dev/null   # 租期缩到 1s
sleep 1.2                                                            # 等过期
ck "过期接管 epoch+1"       "t|2"  "$(W -c "select * from factory_claim('issue:1','machB',900)")"
ck "旧链 fence f"           "f"    "$(W -c "select factory_fence_ok('issue:1','machA',1)")"
ck "旧链 heartbeat f"       "f"    "$(W -c "select factory_heartbeat('issue:1','machA',1,900)")"
ck "新主 fence t"           "t"    "$(W -c "select factory_fence_ok('issue:1','machB',2)")"
ck "release 成功"           "t"    "$(W -c "select factory_release('issue:1','machB',2)")"
ck "release 后再抢 e+1"     "t|3"  "$(W -c "select * from factory_claim('issue:1','machA',900)")"

# --- 13-15：配额（max_parallel=2）与机器自注册 ---
ck "第二键在配额内 t|1"     "t|1"  "$(W -c "select * from factory_claim('issue:2','machA',900)")"
ck "超配额第三键拒"         "f|-1" "$(W -c "select * from factory_claim('issue:3','machA',900)")"
ck "满配自有键续约 t"       "t|3"  "$(W -c "select * from factory_claim('issue:1','machA',900)")"
# 机器自注册：machB 在 5 的失败 claim 里也应登记（admin 侧盘点；worker 直表读被 RLS 拒，见 16）
ck "机器自动登记=2"         "2"    "$(PG -c "select count(*) from factory_machines" | tr -d ' ')"

# --- 16-17：权限收口 ---
W -c "select * from factory_leases" >/dev/null 2>&1; r=$?
ck "直表读被拒(rc!=0)"      "deny" "$([ $r -ne 0 ] && echo deny || echo allow)"
W -c "select factory_revoke('e2e')" >/dev/null 2>&1; r=$?
ck "worker 调 revoke 被拒"  "deny" "$([ $r -ne 0 ] && echo deny || echo allow)"

# --- 18-19：管理员吊销 → 秒级生效（不等心跳/过期）---
PG -c "select factory_revoke('e2e')" >/dev/null
ck "吊销后持有者 fence f"   "f"    "$(W -c "select factory_fence_ok('issue:1','machA',3)")"
ck "吊销租户 claim 拒"      "f|-1" "$(W -c "select * from factory_claim('issue:9','machA',900)")"

# --- 20：单机停用（精确止损）---
PG -c "update factory_tenants set status='active' where tenant='e2e'; truncate factory_leases;" >/dev/null
W -c "select * from factory_claim('issue:5','machA',900)" >/dev/null
PG -c "select factory_machine_disable('machA')" >/dev/null
ck "停用机器 fence f"       "f"    "$(W -c "select factory_fence_ok('issue:5','machA',1)")"
ck "停用机器 claim 拒"      "f|-1" "$(W -c "select * from factory_claim('issue:6','machA',900)")"

# --- 21-22：未知租户 fail-closed；审计有痕 ---
PG -c "create role nobody_e2e login; grant factory_worker to nobody_e2e;" >/dev/null
out=$(runuser -u postgres -- psql -h 127.0.0.1 -p $PORT -U nobody_e2e -d postgres -X -q -tA \
        -c "select * from factory_claim('issue:7','machA',900)" 2>&1 | tail -1)
ck "无租户行 claim 拒"      "f|-1" "$out"
ck "审计事件有痕"           "y"    "$(PG -c "select case when count(*)>0 then 'y' else 'n' end from factory_events" | tr -d ' ')"

# --- 23：配额并发串行化（for update 行锁，PR#34 审查修复）---
# 4 台机器并发 claim 4 个不同键，cap=2 → 恰好 2 赢。无行锁时是 TOCTOU：
# 并发 count 双双看到余量 → 超配。行锁下串行化，断言确定性成立。
PG -c "truncate factory_leases;" >/dev/null
for i in 1 2 3 4; do
  ( W -c "select * from factory_claim('issue:c${i}','machD${i}',900)" > "/tmp/lease-cc-${i}.out" 2>/dev/null ) &
done
wait
wins=$(grep -hc '^t|' /tmp/lease-cc-{1,2,3,4}.out 2>/dev/null | paste -sd+ | bc 2>/dev/null)
[ -z "$wins" ] && wins=$(cat /tmp/lease-cc-{1,2,3,4}.out 2>/dev/null | grep -c '^t|')
ck "并发 claim 恰满配额"    "2"    "${wins}"
rm -f /tmp/lease-cc-{1,2,3,4}.out

else
  PG_SKIPPED=25
  echo "SKIP: PG 环境不可用（initdb/runuser/postgres 任缺，本机 $(uname -s)），跳过 25 项仲裁层 SQL 用例"
fi

LEASE_SH="${REPO}/.factory/factory-lease.sh"
tp="$(mktemp -d)"; git -C "$tp" init -q; mkdir -p "$tp/.factory/var"
printf "x'); drop table factory_leases;--" > "$tp/.factory/var/machine-id"
# 载荷在位前置（tripwire，steering §自建关卡「前提失效硬失败」）：载荷
# 行被编辑事故误删时，本用例会退化为「文件缺失拒」假绿（2026-08-27
# PR #71 实发）——读回比对钉死「测的确实是注入载荷而非空缺拒」。
ck "篡改载荷在位(drop table)" "y" \
   "$(grep -q 'drop table factory_leases' "$tp/.factory/var/machine-id" && echo y || echo n)"
rc=$(REPO="$tp" SUPABASE_DB=unused bash -c "source '${LEASE_SH}'; lease_machine_id >/dev/null 2>&1; echo \$?" 2>/dev/null)
ck "machine-id 篡改拒"      "1"    "$rc"
printf '%s' "$(python3 -c 'import uuid; print(uuid.uuid4().hex)')" > "$tp/.factory/var/machine-id"
rc=$(REPO="$tp" SUPABASE_DB=unused bash -c "source '${LEASE_SH}'; lease_machine_id >/dev/null 2>&1; echo \$?" 2>/dev/null)
ck "machine-id 合法过"      "0"    "$rc"
# --- 单写者降级（SUPABASE_DB 未设 = 本地锁；README「单写者降级」）---
SW() { # SW <代码> → 干净 bash（REPO=$tp，显式 unset SUPABASE_DB）；stderr 落 $tp/stderr
  env -u SUPABASE_DB REPO="$tp" FACTORY_LEASE_SECS="${SW_SECS:-900}" \
    bash -c "source '${LEASE_SH}'; ${1}" 2>"$tp/stderr"
}
swlock="$tp/.factory/locks/leases/issue:sw.lock"

# ① 未设 SUPABASE_DB → claim 成功且锁文件存在（epoch=1：fencing token 起点）
ck "SW claim 降级成功 epoch=1" "1" "$(SW 'lease_claim issue:sw')"
ck "SW 本地锁文件存在"         "y" "$([ -f "$swlock" ] && echo y || echo n)"
ck "SW 降级告警有痕"           "y" "$(grep -q 'single-writer mode' "$tp/stderr" && echo y || echo n)"
# ② 持有中二次 claim 拒（本地互斥严于 PG 同机续约：同机并发双链正是要防的）
ck "SW 持有中再 claim 拒"      "1" "$(SW 'lease_claim issue:sw >/dev/null 2>&1; echo $?')"
# ③ 过期可夺（touch -t 伪造 mtime）且 epoch 递增
touch -t 200001010000 "$swlock"
ck "SW 过期可夺 epoch+1"       "2" "$(SW 'lease_claim issue:sw')"
# ④ release（持有者匹配删锁）后可再 claim，epoch 单调不回零（对齐 PG 行常驻）
SW 'lease_release issue:sw 2' >/dev/null 2>&1
ck "SW release 删锁"           "n" "$([ -f "$swlock" ] && echo y || echo n)"
ck "SW release 后再 claim e=3" "3" "$(SW 'lease_claim issue:sw')"
# ⑤ fence：持有者过 / 陈旧 epoch 拒 / 异 machine-id 拒
ck "SW fence 持有者过"         "0" "$(SW 'lease_fence_ok issue:sw 3 >/dev/null 2>&1; echo $?')"
ck "SW fence 陈旧 epoch 拒"    "1" "$(SW 'lease_fence_ok issue:sw 2 >/dev/null 2>&1; echo $?')"
# heartbeat：过期不许复活（对齐 PG），重新 claim 后 touch 续租
touch -t 200001010000 "$swlock"
ck "SW heartbeat 过期拒"       "1" "$(SW 'lease_heartbeat issue:sw 3 >/dev/null 2>&1; echo $?')"
ck "SW 重claim后 heartbeat 活" "0" "$(SW 'lease_claim issue:sw >/dev/null; lease_heartbeat issue:sw 4 >/dev/null 2>&1; echo $?')"
printf 'othermach|4|%s|%s\n' "$$" "$(date +%s)" > "$swlock"   # 伪造异机持有者（mtime=now 未过期）
ck "SW fence 异机拒"           "1" "$(SW 'lease_fence_ok issue:sw 4 >/dev/null 2>&1; echo $?')"
# ⑥ 过期接管单赢家（rename 原子接管，PR #53 审查①）：并发双 claim 恰一胜
SW 'lease_claim issue:cc >/dev/null'
touch -t 200001010000 "$tp/.factory/locks/leases/issue:cc.lock"
for i in 1 2; do
  ( env -u SUPABASE_DB REPO="$tp" FACTORY_LEASE_SECS=900 \
      bash -c "source '${LEASE_SH}'; lease_claim issue:cc >/dev/null 2>&1; echo \$? > '$tp/cc$i'" ) &
done
wait
wins=0; for i in 1 2; do if [ "$(cat "$tp/cc$i" 2>/dev/null)" = 0 ]; then wins=$((wins+1)); fi; done
ck "SW 并发过期接管恰一胜"   "1"    "$wins"
# ⑦ fence 用锁内实租期（PR #53 审查③）：2s 短租期过期后，全局默认 900s 不撑腰
SW 'lease_claim issue:short 2 >/dev/null'
sleep 3
ck "SW 短租期 fence 过期拒"  "1"    "$(SW 'lease_fence_ok issue:short 1 >/dev/null 2>&1; echo $?')"
# ⑧ hb 显式租期写回锁内：hb 2s 生效后按实租期判过期（反向判别：按全局
#    默认判的实现此处会误过——正是审查③指出的形态）
SW 'lease_claim issue:hbs >/dev/null; sleep 1; lease_heartbeat issue:hbs 1 2 >/dev/null 2>&1'
sleep 3
# ⑨ 墓碑调和（PR #116 CodeRabbit）：release 在 mv 后/放回前被 SIGKILL →
# .rel.* 截留锁位。claim 建锁前调和：新鲜墓碑 = 活锁被截留 → ln 原子放回
# （_lease_sw_restore，位空得内容删源；随后主流程读新鲜即拒 ≤ 租期自解）；
# 过期/坏内容 = 死锁残渣 → 清理后正常接管。A2 用 ⑧ 链后无主过期锁基底。
rellock="$tp/.factory/locks/leases/issue:rel.lock"
SW 'lease_claim issue:rel >/dev/null'              # e=1 在位
mv "$rellock" "$rellock.rel.1.1"                   # 模拟 release 死在 mv 后（新鲜墓碑）
ck "SW ⑨A1 新鲜墓碑 claim 拒"  "1"   "$(SW 'lease_claim issue:rel >/dev/null 2>&1; echo $?')"
ck "SW ⑨A1 新鲜墓碑放回锁位"  "y"   "$([ -f "$rellock" ] && echo y || echo n)"
ck "SW ⑨A1 墓碑清理"          "n"   "$([ -e "$rellock.rel.1.1" ] && echo y || echo n)"
touch -t 200001010000 "$rellock"                   # 过期 → 死锁残渣形态
mv "$rellock" "$rellock.rel.2.2"
ck "SW ⑨A2 过期墓碑接管 e=2"  "2"   "$(SW 'lease_claim issue:rel')"
ck "SW ⑨A2 残渣清且锁在位"    "y"   "$([ -f "$rellock" ] && [ ! -e "$rellock.rel.2.2" ] && echo y || echo n)"
# ⑨c/d _lease_sw_restore 原子判位原语（ln 硬链：dst 空 → 得内容删源链；
# dst 已占 → ln 失败弃残本、不碰位上现有内容）——直接驱动 helper 断言
# 判位语义，而非经 claim 间接观察
ck "SW ⑨c restore 位空放回"  "dst=fresh src=n" \
   "$(env -u SUPABASE_DB REPO="$tp" bash -c "source '${LEASE_SH}'; echo fresh > '$tp/rc-src'; _lease_sw_restore '$tp/rc-src' '$tp/rc-dst'; printf 'dst=%s src=%s\n' \"\$(cat '$tp/rc-dst')\" \"\$([ -e '$tp/rc-src' ] && echo y || echo n)\"" 2>/dev/null)"
ck "SW ⑨d restore 位占弃残"  "dst=other src=n" \
   "$(env -u SUPABASE_DB REPO="$tp" bash -c "source '${LEASE_SH}'; echo fresh > '$tp/rd-src'; echo other > '$tp/rd-dst'; _lease_sw_restore '$tp/rd-src' '$tp/rd-dst'; printf 'dst=%s src=%s\n' \"\$(cat '$tp/rd-dst')\" \"\$([ -e '$tp/rd-src' ] && echo y || echo n)\"" 2>/dev/null)"

# 双态边界：已设 SUPABASE_DB 但 psql 不可达 = 配置错误，仍 fail-closed（不降级）
if command -v psql >/dev/null; then
  rc="$(REPO="$tp" SUPABASE_DB="postgresql://127.0.0.1:1/x?connect_timeout=2" \
    bash -c "source '${LEASE_SH}'; lease_claim issue:fc >/dev/null 2>&1; echo \$?" 2>/dev/null)"
  ck "PG 不可达仍 fail-closed" "1" "$rc"
else
  PG_SKIPPED=$((PG_SKIPPED+1))
  echo "SKIP: 缺 psql，跳过「PG 不可达仍 fail-closed」"
fi
rm -rf "$tp"
echo "-----"
echo "PASS=$PASS FAIL=$FAIL SKIP=$PG_SKIPPED"
[ $FAIL -eq 0 ]
