// afdian-webhook 纯逻辑层（无 IO，便于单测）。
// 依赖注入：数据库读写通过 Store、订单核实通过 OrderVerifier、密钥/时钟通过 Deps 传入。
//
// 验真设计（重要）：afdian webhook 回调 payload 里【没有 sign 字段】，无法对回调本身验签。
// 正确做法是拿回调里的 out_trade_no 反向调 query-order API 核实订单真实存在且已支付，
// 并【以 query-order 返回的订单为权威数据源】（防伪造 webhook）。

import { md5Hex } from "./md5.ts";

// ---- afdian 订单结构（仅取用到的字段）----
export interface AfdianOrder {
  out_trade_no: string; // 订单号，幂等键
  user_id?: string; // afdian 用户 id（非我方 user）
  plan_id?: string;
  month?: number; // 订阅月数
  total_amount?: string | number;
  remark?: string; // 用户留言，含我方绑定码
  status?: number; // 2 = 已支付
}

// webhook 回调体：仅用于拿 out_trade_no 触发核实，不作为权威数据。
export interface AfdianPayload {
  ec?: number;
  em?: string;
  data?: {
    type?: string; // 'test' 表示 afdian ping 校验
    order?: { out_trade_no?: string };
  };
}

// ---- 数据库读写抽象（单测用 mock 实现）----
export interface BindCodeRow {
  id: string;
  user_id: string;
  code: string;
}

export interface SubscriptionRow {
  user_id: string;
  current_period_end: string | null; // ISO
  afdian_trade_no: string | null;
}

export interface Store {
  // 依 out_trade_no 查已有订阅（幂等判断）
  findSubscriptionByTradeNo(tradeNo: string): Promise<SubscriptionRow | null>;
  // 依 user_id 查已有订阅（续订叠加需要现有到期日）
  findSubscriptionByUser(userId: string): Promise<SubscriptionRow | null>;
  // 查未消费的绑定码
  findUnconsumedBindCode(code: string): Promise<BindCodeRow | null>;
  // upsert 订阅（user_id 唯一冲突走 update）
  upsertSubscription(row: {
    user_id: string;
    plan: "monthly" | "yearly";
    status: "active";
    current_period_end: string;
    source: "afdian";
    afdian_trade_no: string;
  }): Promise<void>;
  // 消费绑定码
  consumeBindCode(id: string): Promise<void>;
  // 写审计
  insertWebhookEvent(row: {
    out_trade_no: string | null;
    outcome: string;
    raw_payload: unknown;
    note: string | null;
  }): Promise<void>;
}

// 订单核实抽象：调 query-order API，返回已支付订单（权威数据）或 null（不存在/未支付/失败）。
export interface OrderVerifier {
  fetchOrder(outTradeNo: string): Promise<AfdianOrder | null>;
}

export interface Deps {
  store: Store;
  verifier: OrderVerifier;
  afdianPlanId?: string; // 可选白名单
  now: () => Date; // 可注入时钟，便于测试
}

// ---- afdian API 请求签名 ----
// 规范：sign = md5(token + 按 key 字母序拼接的 "params{params}ts{ts}user_id{user_id}")，
// 小写十六进制，无分隔符。已知答案向量：
//   md5('123' + 'params{"a":333}ts1624339905user_idabc') === a4acc28b81598b7e5d84ebdc3e91710c
export function computeAfdianSign(
  token: string,
  params: string,
  ts: number,
  userId: string,
): string {
  return md5Hex(`${token}params${params}ts${ts}user_id${userId}`);
}

// ---- 绑定码提取 ----
// 8 位 base32（迁移里的字母表：ABCDEFGHJKMNPQRSTVWXYZ234567，无 0/1/8/9/I/L/O/U）。
// 用户留言可能夹杂空格/中文，宽松提取第一段匹配。忽略大小写后转大写匹配库中码。
const BIND_CODE_RE = /[ABCDEFGHJKMNPQRSTVWXYZ234567]{8}/;

export function extractBindCode(remark: string | undefined): string | null {
  if (!remark) return null;
  const m = remark.toUpperCase().match(BIND_CODE_RE);
  return m ? m[0] : null;
}

// ---- 周期计算 ----
// months>=12 记为 yearly，否则 monthly。缺省月数按 1 兜底。
export function resolvePlan(months: number): "monthly" | "yearly" {
  return months >= 12 ? "yearly" : "monthly";
}

export function normalizeMonths(order: AfdianOrder): number {
  const m = Number(order.month);
  if (Number.isFinite(m) && m > 0) return Math.floor(m);
  return 1; // 兜底
}

// 续订叠加：新到期 = max(now, 现有到期) + months 个月。
export function computePeriodEnd(
  now: Date,
  existingEnd: string | null,
  months: number,
): Date {
  const base = existingEnd ? new Date(existingEnd) : now;
  const start = base.getTime() > now.getTime() ? base : now;
  const end = new Date(start.getTime());
  end.setUTCMonth(end.getUTCMonth() + months);
  return end;
}

// ---- 主处理流程 ----
// 恒返回 { ec: 200 }（afdian 要求 200 否则重试），业务失败落审计表。
export interface HandleResult {
  ec: number;
  em: string;
  outcome: string; // 便于测试断言
  note?: string; // 失败原因(人类可读)，供告警拼接
  order?: AfdianOrder; // 权威订单(核实通过后可用，含 remark/金额/月数)，供告警拼接
}

// afdian 后台「测试推送」用的官方文档示例假单号，query-order 查无属正常，不告警。
export const AFDIAN_SAMPLE_ORDER = "202106232138371083454010626";

// 正常/噪音结局：无需告警。其余结局视为需要人工关注的失败。
const NON_ALERT_OUTCOMES = new Set(["activated", "dup", "ping"]);

// 是否应发失败告警：非正常结局 + 不是测试推送假单。
export function shouldAlert(outcome: string, outTradeNo: string | null | undefined): boolean {
  if (NON_ALERT_OUTCOMES.has(outcome)) return false;
  if (outTradeNo === AFDIAN_SAMPLE_ORDER) return false; // 过滤 afdian 测试推送噪音
  return true;
}

// 结局码 → 人类可读含义
const OUTCOME_MEANING: Record<string, string> = {
  no_bind_code: "用户付款成功，但订单留言未填绑定码 → 无法关联账号",
  no_user: "订单留言的绑定码无匹配或已被使用 → 无法关联账号",
  plan_mismatch: "订单 plan_id 不在白名单，未激活",
  order_verify_failed: "订单核实失败：不存在/未支付，或 afdian token/签名失效",
  error: "webhook 载荷异常（如缺 out_trade_no）",
};

// 结局码 → 处理建议
const OUTCOME_HINT: Record<string, string> = {
  no_bind_code:
    "用户已付款但没填绑定码。据下方「用户留言/afdian 用户」定位用户 → SQL Editor 手动 upsert subscriptions 补开；或联系用户按 /membership 绑定码重新填写。",
  no_user:
    "绑定码错误/过期。据「用户留言」判断用户意图 → 手动补开；或让用户在 /membership 重取绑定码。",
  plan_mismatch: "检查 AFDIAN_PLAN_ID 白名单是否遗漏了该 plan。",
  order_verify_failed:
    "多为 AFDIAN_TOKEN secret 非当前有效 token（sign 失败），或订单确不存在。核对 secret 是否为最新 token。",
  error: "检查 webhook 载荷；通常为 afdian 异常回调，可忽略。",
};

// 拼装富文本告警（Server酱 desp 支持 Markdown）。now 显式传入便于测试。
export function buildAlert(
  result: HandleResult,
  outTradeNo: string | null,
  supabaseRef: string | undefined,
  now: Date,
  retryUrl?: string, // 一键重试链接（已签名），可空
): { title: string; desp: string } {
  const o = result.order;
  const bj = new Date(now.getTime() + 8 * 3600 * 1000)
    .toISOString().replace("T", " ").slice(0, 19);
  const lines = [
    `**${OUTCOME_MEANING[result.outcome] ?? result.outcome}**`,
    "",
    `- 结局码：\`${result.outcome}\``,
    `- 订单号：\`${outTradeNo ?? "(无)"}\``,
    result.note ? `- 详情：${result.note}` : "",
    o ? `- 金额：¥${o.total_amount ?? "?"}　月数：${o.month ?? "?"}　plan：\`${o.plan_id ?? "?"}\`` : "",
    o && o.remark != null ? `- 用户留言：${JSON.stringify(o.remark)}` : "",
    o && o.user_id ? `- afdian 用户：\`${o.user_id}\`` : "",
    `- 时间：${bj}（北京）`,
    "",
    "**如何处理**",
    OUTCOME_HINT[result.outcome] ?? "查 webhook_events 明细人工判断。",
    "",
    "**快捷操作**",
    retryUrl ? `- [🔄 一键重试处理](${retryUrl})（修好根因后点此重跑该订单）` : "",
    supabaseRef
      ? `- [📋 打开 Supabase 表编辑器](https://supabase.com/dashboard/project/${supabaseRef}/editor)`
      : "",
  ].filter(Boolean);
  return { title: `⚠️ 会员支付未激活：${result.outcome}`, desp: lines.join("\n") };
}

export async function handlePayload(
  payload: AfdianPayload,
  deps: Deps,
): Promise<HandleResult> {
  // 统一收口：outcome + 可选 note/order，便于上层告警拼接细节。
  const done = (
    outcome: string,
    note?: string,
    order?: AfdianOrder,
  ): HandleResult => ({ ec: 200, em: "", outcome, note, order });

  // 1. ping/test 直接放行
  if (payload?.data?.type === "test") {
    return done("ping");
  }

  // 2. 拿回调里的 out_trade_no（webhook body 仅用于此，不作权威数据）
  const tradeNo = payload?.data?.order?.out_trade_no;
  if (!tradeNo) {
    const note = "缺少 order.out_trade_no";
    await deps.store.insertWebhookEvent({
      out_trade_no: null,
      outcome: "error",
      raw_payload: payload,
      note,
    });
    return done("error", note);
  }

  // 3. 幂等：同一订单号已处理过则跳过（在昂贵的核实调用之前）
  const dup = await deps.store.findSubscriptionByTradeNo(tradeNo);
  if (dup) {
    const note = "订单已处理，跳过";
    await deps.store.insertWebhookEvent({
      out_trade_no: tradeNo,
      outcome: "dup",
      raw_payload: payload,
      note,
    });
    return done("dup", note);
  }

  // 4. 反向核实：调 query-order 拿权威订单，要求存在且 status===2（已支付）
  const order = await deps.verifier.fetchOrder(tradeNo);
  if (!order || order.status !== 2) {
    const note = order
      ? `订单 status=${order.status ?? ""} 非已支付`
      : "query-order 未核实到订单（订单不存在 或 token/签名失败）";
    await deps.store.insertWebhookEvent({
      out_trade_no: tradeNo,
      outcome: "order_verify_failed",
      raw_payload: payload,
      note,
    });
    return done("order_verify_failed", note, order ?? undefined);
  }

  // 5. 可选 plan 白名单（用权威订单的 plan_id）
  if (deps.afdianPlanId && order.plan_id !== deps.afdianPlanId) {
    const note = `plan_id=${order.plan_id ?? ""} 不在白名单`;
    await deps.store.insertWebhookEvent({
      out_trade_no: tradeNo,
      outcome: "plan_mismatch",
      raw_payload: payload,
      note,
    });
    return done("plan_mismatch", note, order);
  }

  // 6. 绑定码（用权威订单的 remark）
  const code = extractBindCode(order.remark);
  if (!code) {
    const note = "留言未含绑定码（用户下单时未按提示填写绑定码）";
    await deps.store.insertWebhookEvent({
      out_trade_no: tradeNo,
      outcome: "no_bind_code",
      raw_payload: payload,
      note,
    });
    return done("no_bind_code", note, order);
  }

  const bind = await deps.store.findUnconsumedBindCode(code);
  if (!bind) {
    const note = `绑定码 ${code} 无匹配或已消费`;
    await deps.store.insertWebhookEvent({
      out_trade_no: tradeNo,
      outcome: "no_user",
      raw_payload: payload,
      note,
    });
    return done("no_user", note, order);
  }

  // 7. 周期计算 + 写库（数据全部取自权威订单）
  const months = normalizeMonths(order);
  const plan = resolvePlan(months);
  const existing = await deps.store.findSubscriptionByUser(bind.user_id);
  const periodEnd = computePeriodEnd(
    deps.now(),
    existing?.current_period_end ?? null,
    months,
  );

  await deps.store.upsertSubscription({
    user_id: bind.user_id,
    plan,
    status: "active",
    current_period_end: periodEnd.toISOString(),
    source: "afdian",
    afdian_trade_no: tradeNo,
  });
  await deps.store.consumeBindCode(bind.id);
  const note = `user=${bind.user_id} plan=${plan} months=${months}`;
  await deps.store.insertWebhookEvent({
    out_trade_no: tradeNo,
    outcome: "activated",
    raw_payload: payload,
    note,
  });

  return done("activated", note, order);
}
