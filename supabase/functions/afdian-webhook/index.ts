// afdian-webhook Supabase Edge Function 入口。
// 职责：接 afdian 回调 → 拿 out_trade_no → 反向调 query-order 核实 → 委托 logic.handlePayload → 恒返回 200。
// 所有密钥仅从 Deno.env 读取，绝不硬编码。

import { createClient, SupabaseClient } from "@supabase/supabase-js";
import {
  AfdianOrder,
  AfdianPayload,
  BindCodeRow,
  buildAlert,
  computeAfdianSign,
  Deps,
  handlePayload,
  OrderVerifier,
  shouldAlert,
  Store,
  SubscriptionRow,
} from "./logic.ts";

// 基于 service_role client 的 Store 实现（绕过 RLS 写库）。
export function createSupabaseStore(client: SupabaseClient): Store {
  return {
    async findSubscriptionByTradeNo(tradeNo) {
      const { data } = await client
        .from("subscriptions")
        .select("user_id, current_period_end, afdian_trade_no")
        .eq("afdian_trade_no", tradeNo)
        .maybeSingle();
      return (data as SubscriptionRow) ?? null;
    },
    async findSubscriptionByUser(userId) {
      const { data } = await client
        .from("subscriptions")
        .select("user_id, current_period_end, afdian_trade_no")
        .eq("user_id", userId)
        .maybeSingle();
      return (data as SubscriptionRow) ?? null;
    },
    async findUnconsumedBindCode(code) {
      const { data } = await client
        .from("bind_codes")
        .select("id, user_id, code")
        .eq("code", code)
        .eq("consumed", false)
        .maybeSingle();
      return (data as BindCodeRow) ?? null;
    },
    async upsertSubscription(row) {
      const { error } = await client
        .from("subscriptions")
        .upsert(row, { onConflict: "user_id" });
      if (error) throw error;
    },
    async consumeBindCode(id) {
      const { error } = await client
        .from("bind_codes")
        .update({ consumed: true })
        .eq("id", id);
      if (error) throw error;
    },
    async insertWebhookEvent(row) {
      // 审计写入失败不应阻断 200 返回，仅打日志。
      const { error } = await client.from("webhook_events").insert({
        source: "afdian",
        ...row,
      });
      if (error) console.error("webhook_events 写入失败:", error.message);
    },
  };
}

// 调 afdian query-order API 核实订单的 Verifier 实现。
// 权威数据源：以此返回的订单为准，而非 webhook body（防伪造）。
export function createAfdianVerifier(cfg: {
  token: string;
  userId: string;
  now: () => Date;
  fetchImpl?: typeof fetch; // 便于测试注入
}): OrderVerifier {
  const doFetch = cfg.fetchImpl ?? fetch;
  return {
    async fetchOrder(outTradeNo) {
      const params = JSON.stringify({ out_trade_no: outTradeNo });
      const ts = Math.floor(cfg.now().getTime() / 1000);
      const sign = computeAfdianSign(cfg.token, params, ts, cfg.userId);
      const body = JSON.stringify({ user_id: cfg.userId, params, ts, sign });
      let json: { ec?: number; data?: { list?: AfdianOrder[] } };
      try {
        const resp = await doFetch("https://afdian.com/api/open/query-order", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body,
        });
        json = await resp.json();
      } catch (e) {
        console.error("query-order 调用失败:", (e as Error).message);
        return null;
      }
      if (json?.ec !== 200) {
        // ec≠200 通常是 sign/token 问题(如 400005 sign validation failed)。
        // 单独打日志, 避免与"订单查无"混为一条含糊记录。
        const j = json as { ec?: number; em?: string };
        console.error(`query-order 拒绝: ec=${j.ec} em=${j.em ?? ""}`);
        return null;
      }
      const list = json.data?.list ?? [];
      // 在返回列表中精确匹配本单号（query-order 可能返回多单）。
      return list.find((o) => o.out_trade_no === outTradeNo) ?? null;
    },
  };
}

// 读取运行时环境（缺失即抛，避免静默降级）。
function loadEnv() {
  const get = (k: string): string => {
    const v = Deno.env.get(k);
    if (!v) throw new Error(`缺少环境变量: ${k}`);
    return v;
  };
  const supabaseUrl = get("SUPABASE_URL");
  return {
    supabaseUrl,
    // 从 https://<ref>.supabase.co 解析项目 ref，用于告警里拼 Dashboard 链接。
    supabaseRef: supabaseUrl.replace(/^https?:\/\//, "").split(".")[0] || undefined,
    serviceRoleKey: get("SUPABASE_SERVICE_ROLE_KEY"),
    afdianToken: get("AFDIAN_TOKEN"),
    afdianUserId: get("AFDIAN_USER_ID"),
    afdianPlanId: Deno.env.get("AFDIAN_PLAN_ID") || undefined,
    // 可选：Server酱 SENDKEY，用于支付失败告警。未配置则不告警（优雅降级）。
    alertSendkey: Deno.env.get("SERVERCHAN_SENDKEY") || undefined,
  };
}

// 发失败告警到 Server酱（POST sctapi.ftqq.com/<SENDKEY>.send）。
// 告警失败绝不影响 webhook 主流程——调用方需 try/catch 兜住。
async function sendServerChanAlert(
  sendkey: string,
  title: string,
  desp: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const body = new URLSearchParams({ title, desp });
  const resp = await fetchImpl(`https://sctapi.ftqq.com/${sendkey}.send`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!resp.ok) {
    console.error(`Server酱告警返回非 2xx: ${resp.status}`);
  }
}

// 200 + {ec:200}，afdian 才不会重试。
function jsonOk(outcome?: string): Response {
  return new Response(JSON.stringify({ ec: 200, em: "", outcome }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

// 面向人（微信里点链接后在浏览器打开）的极简 HTML 响应。
function htmlResp(body: string, status = 200): Response {
  return new Response(
    `<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">` +
      `<body style="font-family:system-ui;max-width:640px;margin:40px auto;padding:0 16px;line-height:1.7">${body}</body>`,
    { status, headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

// HMAC-SHA256 十六进制签名。用 service_role key 作密钥——只有本函数能生成有效重试链接。
async function hmacSign(key: string, msg: string): Promise<string> {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey(
    "raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", k, enc.encode(msg));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

type Env = ReturnType<typeof loadEnv>;

// 组装处理依赖（POST webhook 与 GET 重试共用）。
function makeDeps(env: Env): Deps {
  const client = createClient(env.supabaseUrl, env.serviceRoleKey, {
    auth: { persistSession: false },
  });
  const now = () => new Date();
  return {
    store: createSupabaseStore(client),
    verifier: createAfdianVerifier({
      token: env.afdianToken,
      userId: env.afdianUserId,
      now,
    }),
    afdianPlanId: env.afdianPlanId,
    now,
  };
}

// 生成签名重试链接（用于告警里的「一键重试」）。缺 ref/order 则返回 undefined。
async function makeRetryUrl(env: Env, outTradeNo: string | null): Promise<string | undefined> {
  if (!env.supabaseRef || !outTradeNo) return undefined;
  const sig = await hmacSign(env.serviceRoleKey, outTradeNo);
  return `https://${env.supabaseRef}.supabase.co/functions/v1/afdian-webhook` +
    `?action=retry&order=${encodeURIComponent(outTradeNo)}&sig=${sig}`;
}

// GET ?action=retry：验签后重跑该订单（一键处理）。始终走完整核实，假单/无码照样失败。
async function handleRetry(url: URL): Promise<Response> {
  const order = url.searchParams.get("order") ?? "";
  const sig = url.searchParams.get("sig") ?? "";
  const env = loadEnv();
  const expect = await hmacSign(env.serviceRoleKey, order);
  if (!order || sig !== expect) {
    return htmlResp("<h2>❌ 链接无效或已被篡改</h2><p>请从最新告警重新进入。</p>", 403);
  }
  // 合成一个仅含 out_trade_no 的 payload 重跑（重试路径不再发告警，避免循环）。
  const deps = makeDeps(env);
  const result = await handlePayload(
    { data: { order: { out_trade_no: order } } },
    deps,
  );
  if (result.outcome === "activated") {
    return htmlResp(`<h2>✅ 已激活会员</h2><p>订单 <code>${order}</code> 处理成功。</p>`);
  }
  if (result.outcome === "dup") {
    return htmlResp(`<h2>ℹ️ 该订单此前已处理</h2><p>订单 <code>${order}</code> 已是激活/处理过状态，无需重复。</p>`);
  }
  return htmlResp(
    `<h2>⚠️ 仍未激活</h2><p>订单 <code>${order}</code> 结局：<code>${result.outcome}</code></p>` +
      `<p>${result.note ?? ""}</p><p>请先修复根因（如更新 AFDIAN_TOKEN、或据留言人工补开）再重试。</p>`,
  );
}

export async function serveRequest(req: Request): Promise<Response> {
  const url = new URL(req.url);

  // GET 一键重试（人从微信告警点入）
  if (req.method === "GET" && url.searchParams.get("action") === "retry") {
    return await handleRetry(url);
  }
  if (req.method !== "POST") {
    return jsonOk("method_not_allowed");
  }

  let payload: AfdianPayload;
  try {
    payload = await req.json();
  } catch {
    // 解析失败也返回 200（afdian 校验偶发空体），不落表。
    return jsonOk("bad_json");
  }

  // ping/test 校验不依赖任何密钥，必须在 loadEnv 之前放行——
  // 否则 afdian 后台配置回调时（此时 secrets 可能尚未设全）loadEnv 抛异常→500→ping 不通。
  if (payload?.data?.type === "test") {
    return jsonOk("ping");
  }

  const env = loadEnv();
  const deps = makeDeps(env);
  const result = await handlePayload(payload, deps);

  // 支付失败告警：真实付款单未激活（no_bind_code/no_user/plan_mismatch 等）时推送，
  // 过滤 afdian 测试推送假单。告警异常吞掉，绝不影响返回 200。
  const outTradeNo = payload?.data?.order?.out_trade_no ?? null;
  if (env.alertSendkey && shouldAlert(result.outcome, outTradeNo)) {
    try {
      const retryUrl = await makeRetryUrl(env, outTradeNo);
      const { title, desp } = buildAlert(result, outTradeNo, env.supabaseRef, new Date(), retryUrl);
      await sendServerChanAlert(env.alertSendkey, title, desp);
    } catch (e) {
      console.error("告警发送失败:", (e as Error).message);
    }
  }

  return jsonOk(result.outcome);
}

// Edge Function 运行时入口。
if (import.meta.main) {
  Deno.serve(serveRequest);
}
