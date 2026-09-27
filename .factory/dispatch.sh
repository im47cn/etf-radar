#!/usr/bin/env bash
# dispatch.sh — S2 派发器入口 shim（零 LLM，设计 A3/§7）。
#
# 进程编排（后台链并发槽/收割、mkdir+PID 硬锁、watch 循环、TERM/HUP 放锁）
# 已下沉 factory_lib.py dispatch 子命令（docs/adr/ADR-005-dispatch-orchestration-python.md：
# bash 进程原语缺陷类在 Python 形态下结构性不可表达）。本文件只保留入口：
# CLI/env 契约不变——--dry-run（DRY=1 同义）/--watch/--interval N
# （INTERVAL 同义，默认 300s）/MAX_PARALLEL/FACTORY_MERGE_METHOD/
# FACTORY_AUTO_MERGE/GH_REPO/NODE_TIMEOUT，退出码语义不变（2=环境缺失、
# 0=锁忙或正常、3/1=熔断透传）。
#
# 职责边界（唯一命令式写标签的地方）不变：
#   - claim：accepted → in-progress（consume 队列；GitHub 无原子换标签，
#     单机互斥=本入口硬锁，跨机=租约仲裁层，README「租约仲裁」）
#   - 重派：needs-fix（且非 needs-human）→ 关联 issue re-claim（计数契约：
#     claim 时移除 needs-fix，label 事件只在添加时触发）
#   - merge：仅当 reviewDecision=APPROVED 且 A5 门开
#   - 其余一切标签由 factory-state.sh sync 从事实推导（声明式）
exec python3 "$(dirname "$0")/factory_lib.py" dispatch "$@"
