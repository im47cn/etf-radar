// afdian-webhook Supabase Edge Function 入口。
// 职责：接 afdian 回调 → 拿 out_trade_no → 反向调 query-order 核实 → 委托 logic.handlePayload → 恒返回 200。
// 所有密钥仅从 Deno.env 读取，绝不硬编码。

import { createClient, SupabaseClient } from "@supabase/supabase-js";
import {
  AfdianOrder,
  AfdianPayload,
  BindCodeRow,
  computeAfdianSign,
  Deps,
  handlePayload,
  OrderVerifier,
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
        const resp = await doFetch("https://afdian.net/api/open/query-order", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body,
        });
        json = await resp.json();
      } catch (e) {
        console.error("query-order 调用失败:", (e as Error).message);
        return null;
      }
      if (json?.ec !== 200) return null;
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
  return {
    supabaseUrl: get("SUPABASE_URL"),
    serviceRoleKey: get("SUPABASE_SERVICE_ROLE_KEY"),
    afdianToken: get("AFDIAN_TOKEN"),
    afdianUserId: get("AFDIAN_USER_ID"),
    afdianPlanId: Deno.env.get("AFDIAN_PLAN_ID") || undefined,
  };
}

// 200 + {ec:200}，afdian 才不会重试。
function jsonOk(outcome?: string): Response {
  return new Response(JSON.stringify({ ec: 200, em: "", outcome }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

export async function serveRequest(req: Request): Promise<Response> {
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
  const client = createClient(env.supabaseUrl, env.serviceRoleKey, {
    auth: { persistSession: false },
  });
  const now = () => new Date();
  const deps: Deps = {
    store: createSupabaseStore(client),
    verifier: createAfdianVerifier({
      token: env.afdianToken,
      userId: env.afdianUserId,
      now,
    }),
    afdianPlanId: env.afdianPlanId,
    now,
  };

  const result = await handlePayload(payload, deps);
  return jsonOk(result.outcome);
}

// Edge Function 运行时入口。
if (import.meta.main) {
  Deno.serve(serveRequest);
}
