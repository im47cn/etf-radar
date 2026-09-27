#!/usr/bin/env bash
# breaker.sh — R4 成本熔断门（fix-issue.sh / dispatch.sh / cron-dispatch.sh
# 共用接线点）。此前 breaker 子命令与测试俱在而三入口零调用，R4
# 「超限熔断停摆」不生效——本脚本是唯一接线收口，新增入口接此处，勿旁路。
#
# 用法: bash breaker.sh <locks-dir>   （目录内 floor.json + ledger.jsonl）
# 退出码透传 factory_lib.py breaker 约定：
#   0 = 放行；3 = 熔断（当日超限 / 连续失败超限）；
#   1 = 门自身故障（floor.json 缺失或损坏、ledger 行损坏）——python 堆栈
#       已先行打到 stderr，fail-closed 同样停摆，不吞异常。
# DRY 语义归调用方：干跑无副作用，调用方自行跳过本门。
set -u
LOCKSDIR="${1:?用法: bash breaker.sh <locks-dir>}"
LIB="$(dirname "$0")/factory_lib.py"
python3 "${LIB}" breaker "${LOCKSDIR}/floor.json" "${LOCKSDIR}/ledger.jsonl" && exit 0
rc=$?
if [ "${rc}" -eq 3 ]; then
  # 熔断原因已由 factory_lib breaker_check 打到 stderr（"熔断：连续失败 N 次
  # （上限 M），需人工介入" 或 "熔断：今日已跑 N 次（上限 M）"）。此处不再包装：
  # 曾固定输出"成本熔断 ledger 累计超 floor 上限"，与连续失败类熔断事实不符，
  # 误导排查方向（2026-09-05 实证）。
  :
else
  echo "breaker 门自身故障（floor.json/ledger.jsonl 缺失或损坏，见上方堆栈）：fail-closed 停止派发；人工复核 floor.json 与 ledger.jsonl" >&2
fi
exit "${rc}"
