// notify-unsub Supabase Edge Function 入口。
// 职责：GET ?token=<unsub_token> → 以 service_role 匹配 notify_prefs 置 email_enabled=false
//        → 返回人可读 HTML。委托 logic.handleUnsub（纯逻辑），本文件仅做 IO 与 HTTP。
// 所有密钥仅从 Deno.env 读取，绝不硬编码。

import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { handleUnsub, renderHtml, Store } from "./logic.ts";

// 基于 service_role client 的 Store 实现（绕过 RLS 写库）。
export function createSupabaseStore(client: SupabaseClient): Store {
  return {
    async disableByToken(token) {
      const { data, error } = await client
        .from("notify_prefs")
        .update({ email_enabled: false })
        .eq("unsub_token", token)
        .select("user_id");
      if (error) throw error;
      return (data ?? []).length;
    },
  };
}

// 读取运行时环境（缺失即抛）。
function loadEnv() {
  const get = (k: string): string => {
    const v = Deno.env.get(k);
    if (!v) throw new Error(`缺少环境变量: ${k}`);
    return v;
  };
  return {
    supabaseUrl: get("SUPABASE_URL"),
    serviceRoleKey: get("SUPABASE_SERVICE_ROLE_KEY"),
  };
}

// 面向人（浏览器打开）的极简 HTML 响应。
function htmlResp(body: string, status = 200): Response {
  return new Response(
    `<!doctype html><meta charset=utf-8>` +
      `<meta name=viewport content="width=device-width,initial-scale=1">` +
      `<body style="font-family:system-ui;max-width:640px;margin:40px auto;padding:0 16px;line-height:1.7">` +
      `${body}</body>`,
    { status, headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

export async function serveRequest(req: Request): Promise<Response> {
  // 仅接受 GET（退订链接为可点击链接）。
  if (req.method !== "GET") {
    const { body, status } = renderHtml("missing_token");
    return htmlResp(body, status);
  }
  const env = loadEnv();
  const client = createClient(env.supabaseUrl, env.serviceRoleKey, {
    auth: { persistSession: false },
  });
  const store = createSupabaseStore(client);

  try {
    const result = await handleUnsub(req.url, store);
    const { body, status } = renderHtml(result.outcome);
    return htmlResp(body, status);
  } catch (e) {
    // 写库异常 → 通用错误页（不泄露内部信息），返回 500 便于监控。
    console.error("退订处理失败:", (e as Error).message);
    return htmlResp("<h2>处理失败</h2><p>请稍后重试。</p>", 500);
  }
}

// Edge Function 运行时入口。
if (import.meta.main) {
  Deno.serve(serveRequest);
}
