// notify-unsub 纯逻辑层（无 IO，便于单测）。
// 依赖注入：DB 读写通过 Store 传入，便于 mock。
//
// 职责：一键退订。按 unsub_token 匹配 notify_prefs → 置 email_enabled=false → 幂等。
// token 无需登录即可用（随机不可枚举），因此本函数以 service_role 写库（绕 RLS）。

// ---- 数据库写抽象（单测用 mock 实现）----
export interface Store {
  // 按 unsub_token 将对应 notify_prefs 行置 email_enabled=false。
  // 返回受影响行数（0 表示 token 无匹配）。
  disableByToken(token: string): Promise<number>;
}

export type UnsubOutcome = "ok" | "not_found" | "missing_token";

export interface UnsubResult {
  outcome: UnsubOutcome;
}

// 从请求 URL 取 token 参数（空/缺失 → null）。
export function extractToken(url: string): string | null {
  try {
    const t = new URL(url).searchParams.get("token");
    return t && t.trim() !== "" ? t.trim() : null;
  } catch {
    return null;
  }
}

// 核心退订流程。缺 token → missing_token；token 无匹配 → not_found；否则 ok（幂等）。
export async function handleUnsub(url: string, store: Store): Promise<UnsubResult> {
  const token = extractToken(url);
  if (token === null) {
    return { outcome: "missing_token" };
  }
  const affected = await store.disableByToken(token);
  return { outcome: affected > 0 ? "ok" : "not_found" };
}

// 面向人的 HTML 文案（合规：仅客观描述，无操作动词）。
export function renderHtml(outcome: UnsubOutcome): { body: string; status: number } {
  switch (outcome) {
    case "ok":
      return {
        body: "<h2>已退订</h2><p>你将不再收到每日变化摘要邮件。</p>" +
          "<p style='color:#888;font-size:13px'>如需重新开启，可在会员中心打开推送开关。</p>",
        status: 200,
      };
    case "not_found":
      return {
        body: "<h2>链接无效</h2><p>该退订链接已失效或不存在。若你仍在收到邮件，" +
          "请通过最新一封邮件中的退订链接操作。</p>",
        status: 200,
      };
    case "missing_token":
      return {
        body: "<h2>缺少参数</h2><p>退订链接不完整，请使用邮件中的完整退订链接。</p>",
        status: 400,
      };
  }
}
