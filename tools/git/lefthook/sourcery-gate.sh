#!/usr/bin/env bash
# Sourcery pre-push 硬闸（awesome-rules tools/git 分发，由 lefthook 调用）
# opt-in 门禁：仅当仓库根存在 .sourcery.yaml（主动声明，同 xx-java-sdk gate 模式）才启用；
# push 文件含实测支持语言时跑 review --check（同 .sourcery.yaml 配置），有未解决 issue → 阻断 push。
# fail-safe：未 opt-in / 未装 sourcery CLI 均跳过（不因环境缺失误伤）；CLI 在装
# 但认证/订阅失效 → 显式降级跳过（防拦死一切 push 的砖化，见尾部分支注释）。
# 语言口径（issue #123）：以 CLI 实测为准，不照抄宣称支持面——
#   实测有效：.py/.ts/.js（sourcery 1.45.0 review --check 实跑产出评审）
#   实测不扫描：.php（送审零输出，静默空转 = fail-open，不再进闸面）
#   未实测：.go/.java/.cs（保持送审面外显式披露，不默认放行进闸）
# 纯面外语 → 显式降级说明后 exit 0（可审计，非静默）；混合 → 对有效子集
# review，并打印未送审数与清单。升级 CLI 须复测口径并同步本注释与 CI pin。
# 跳过门禁: git push --no-verify
set -u

# opt-in 信号：仓库根 .sourcery.yaml（评审保留清单的载体，主动声明才启用硬闸）
[ -f .sourcery.yaml ] || { echo "[sourcery] 无 .sourcery.yaml（未 opt-in），跳过"; exit 0; }

command -v sourcery >/dev/null 2>&1 || { echo "[sourcery] 未安装 sourcery CLI，跳过"; exit 0; }

# 语言过滤（{push_files} 以参数列表传入）
# .lefthook/ 是上游管理的分发面（install.sh 拷贝产物，真源已过本仓同名闸）：
# 消费仓 .sourcery.yaml 是项目级裁决（如 low-code-quality 开关逐仓不同），
# 不审判上游工具——否则每仓阈值差异会逼出下游补丁，违反零拷贝漂移治理
# （先例：消费仓配置对 .factory/ 上游镜像面同样 ignore）。
SUPPORTED=()   # 实测有效：进 review 闸面
UNSENT=()      # 实测不扫描 / 未实测：显式披露，不进闸面
for f in "$@"; do
  # 纯删除 push：文件已不存在，不在任何评审面（2026-09-27 doc-gen 移除
  # 122 文件实证：不滤则 sourcery 对不存在路径直接 Usage error 拦死 push）
  [ -e "$f" ] || continue
  case "$f" in
    .lefthook/*) continue ;;
    *.py|*.ts|*.js) SUPPORTED+=("$f") ;;
    *.go|*.java|*.cs|*.php) UNSENT+=("$f") ;;
  esac
done

if [ ${#SUPPORTED[@]} -eq 0 ]; then
  if [ ${#UNSENT[@]} -gt 0 ]; then
    echo "[sourcery] ${#UNSENT[@]} 个变更文件在实测支持面外（.php 实测不扫描；.go/.java/.cs 未实测），降级跳过："
    printf '  %s\n' "${UNSENT[@]}"
    echo "[sourcery] 该集不经 Sourcery 评审——如需覆盖，复测 CLI 口径后扩支持面（见脚本头注）"
  else
    echo "[sourcery] 无语言文件变更，跳过"
  fi
  exit 0
fi

if [ ${#UNSENT[@]} -gt 0 ]; then
  echo "[sourcery] ⚠ ${#UNSENT[@]} 个语言文件未送审（实测支持面外）："
  printf '  %s\n' "${UNSENT[@]}"
fi
echo "[sourcery] review --check：${#SUPPORTED[@]} 个实测支持文件"
# 输出先捕获再回显（终端着色丢失无害）：rc≠0 时须区分「代码 issue」与
# 「CLI 账号不可用」——后者拦死一切含 py/ts/js 的 push（砖化），降级放行。
out=$(sourcery review --check --config .sourcery.yaml "${SUPPORTED[@]}" 2>&1)
rc=$?
printf '%s\n' "$out"
# 认证/订阅失效降级（2026-09-13）：关键词形态为预判非实证（试用期内无法
# 复现到期输出）——真实到期输出若不命中，闸保持拦截直到补匹配；届时本地
# 仍可 --no-verify 应急。CI 侧 sourcery-review-gate 刻意不加降级：订阅是
# 全局单点，失效时 CI 红是续订的正确信号，本地降级 + CI fail-closed 分层。
# 两级收紧（评审 #178 bug_risk）：宽关键词任意位置命中会把含认证词的 issue
# 诊断（如 unauthorized.py 文件名）一并放行——① issue 形态优先：输出含非零
# issue 计数（"N issue(s)…"，"No issues detected" 无前置数字不命中）时
# 一律硬拦，认证词同现不再降级；② 认证词锚定错误行形态（行首 error/fatal
# 后接认证词，或完整句式），散落在文件名/诊断里的同词不触发。
if [ "$rc" -ne 0 ]; then
  if printf '%s\n' "$out" | grep -qE '[1-9][0-9]* issue'; then
    :  # issue 形态：按代码问题硬拦（落入下方拦截提示）
  elif printf '%s\n' "$out" | grep -qiE \
    '^[[:space:]]*(error|fatal)[:!].*(authenticat|unauthorized|payment|subscri|trial|expir|token|quota)|your (trial|subscription) (has )?(ended|expired)|please (log ?in|sign ?in)|not logged in|invalid (token|api[ -]?key)|^[[:space:]]*(the sourcery cli is )?not available with this tier|^[[:space:]]*please upgrade at'; then
    # 行首锚定两形态为到期实证补匹配（2026-09-13 试用到期 live 触发：
    # 原预判词全不命中，闸按设计保持拦截直到补匹配；NC21 回归盯防）
    echo "[sourcery] ⚠ CLI 认证/订阅失效（非代码问题），显式降级跳过；CI 侧门禁仍会拦——续订后本闸自动恢复硬拦"
    exit 0
  fi
fi
[ "$rc" -ne 0 ] && echo "[sourcery] 存在未解决 issue，push 被拦：跑 skills/sourcery-autofix 修复循环后重试（跳过: git push --no-verify）"
exit "$rc"
