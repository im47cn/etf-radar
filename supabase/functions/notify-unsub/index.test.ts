// notify-unsub 逻辑层单测。用 mock Store，覆盖：
// 有效 token 退订成功、无效 token 提示、缺 token、token 提取、HTML 状态码。

import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { extractToken, handleUnsub, renderHtml, Store } from "./logic.ts";

// 内存 Store：token → 是否命中。记录被禁用的 token。
function makeStore(validTokens: Set<string>): Store & { disabled: string[] } {
  const disabled: string[] = [];
  return {
    disabled,
    async disableByToken(token: string): Promise<number> {
      if (validTokens.has(token)) {
        disabled.push(token);
        return 1;
      }
      return 0;
    },
  };
}

Deno.test("有效 token → 退订成功并置 email_enabled=false", async () => {
  const store = makeStore(new Set(["tok-abc"]));
  const result = await handleUnsub("https://x.supabase.co/functions/v1/notify-unsub?token=tok-abc", store);
  assertEquals(result.outcome, "ok");
  assertEquals(store.disabled, ["tok-abc"]);
  assertEquals(renderHtml(result.outcome).status, 200);
});

Deno.test("无效 token → not_found，不写库", async () => {
  const store = makeStore(new Set(["tok-abc"]));
  const result = await handleUnsub("https://x/notify-unsub?token=nope", store);
  assertEquals(result.outcome, "not_found");
  assertEquals(store.disabled.length, 0);
  assertEquals(renderHtml(result.outcome).status, 200);
});

Deno.test("缺 token → missing_token，400", async () => {
  const store = makeStore(new Set(["tok-abc"]));
  const result = await handleUnsub("https://x/notify-unsub", store);
  assertEquals(result.outcome, "missing_token");
  assertEquals(store.disabled.length, 0);
  assertEquals(renderHtml(result.outcome).status, 400);
});

Deno.test("空 token 参数 → missing_token", async () => {
  const store = makeStore(new Set(["tok-abc"]));
  const result = await handleUnsub("https://x/notify-unsub?token=", store);
  assertEquals(result.outcome, "missing_token");
});

Deno.test("幂等：同一有效 token 二次退订仍 ok（Store 返回>0）", async () => {
  const store = makeStore(new Set(["tok-abc"]));
  await handleUnsub("https://x?token=tok-abc", store);
  const again = await handleUnsub("https://x?token=tok-abc", store);
  assertEquals(again.outcome, "ok");
});

Deno.test("extractToken 各种输入", () => {
  assertEquals(extractToken("https://x?token=abc"), "abc");
  assertEquals(extractToken("https://x?token=%20"), null); // %20 解码为空格 → trim 后空 → null
  assertEquals(extractToken("https://x?token=%20abc%20"), "abc"); // 两侧空白被 trim
  assertEquals(extractToken("https://x"), null);
  assertEquals(extractToken("not a url"), null);
});

Deno.test("退订成功 HTML 无操作动词、含客观提示", () => {
  const { body } = renderHtml("ok");
  for (const verb of ["买入", "加仓", "卖出", "看涨", "看跌"]) {
    assertEquals(body.includes(verb), false);
  }
  assertEquals(body.includes("已退订"), true);
});
