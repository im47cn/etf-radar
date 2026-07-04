// afdian-webhook 逻辑层单测。用 mock Store + mock OrderVerifier + 假 token，覆盖：
// ping、md5 已知答案向量、订单核实通过激活、核实失败(order_verify_failed)、status≠2、
// 幂等重放、绑定码缺失/无效、月/年周期、续订叠加、plan 白名单不匹配。

import {
  assertEquals,
  assertExists,
} from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  AfdianOrder,
  AfdianPayload,
  BindCodeRow,
  computeAfdianSign,
  computePeriodEnd,
  Deps,
  extractBindCode,
  handlePayload,
  normalizeMonths,
  OrderVerifier,
  resolvePlan,
  Store,
  SubscriptionRow,
} from "./logic.ts";

// ---- 内存 Store（记录调用）----
interface FakeState {
  subsByTrade: Record<string, SubscriptionRow>;
  subsByUser: Record<string, SubscriptionRow>;
  bindCodes: Record<string, BindCodeRow>; // key=code
  events: { outcome: string; out_trade_no: string | null; note: string | null }[];
  upserts: {
    user_id: string;
    plan: string;
    current_period_end: string;
    afdian_trade_no: string;
  }[];
  consumed: string[]; // bind code ids
}

function makeStore(init: Partial<FakeState> = {}): { store: Store; state: FakeState } {
  const state: FakeState = {
    subsByTrade: init.subsByTrade ?? {},
    subsByUser: init.subsByUser ?? {},
    bindCodes: init.bindCodes ?? {},
    events: [],
    upserts: [],
    consumed: [],
  };
  const store: Store = {
    findSubscriptionByTradeNo: (t) =>
      Promise.resolve(state.subsByTrade[t] ?? null),
    findSubscriptionByUser: (u) => Promise.resolve(state.subsByUser[u] ?? null),
    findUnconsumedBindCode: (c) => Promise.resolve(state.bindCodes[c] ?? null),
    upsertSubscription: (row) => {
      state.upserts.push(row);
      return Promise.resolve();
    },
    consumeBindCode: (id) => {
      state.consumed.push(id);
      return Promise.resolve();
    },
    insertWebhookEvent: (row) => {
      state.events.push({
        outcome: row.outcome,
        out_trade_no: row.out_trade_no,
        note: row.note,
      });
      return Promise.resolve();
    },
  };
  return { store, state };
}

// mock verifier：按 out_trade_no 返回预置权威订单（模拟 query-order 结果）。
function makeVerifier(orders: Record<string, AfdianOrder | null>): OrderVerifier {
  return {
    fetchOrder: (tradeNo) => Promise.resolve(orders[tradeNo] ?? null),
  };
}

function makeDeps(
  store: Store,
  verifier: OrderVerifier,
  now = new Date("2026-01-01T00:00:00Z"),
): Deps {
  return { store, verifier, now: () => now };
}

// webhook 回调体：仅含 out_trade_no（真实 afdian webhook 无 sign 字段）。
function webhook(outTradeNo: string): AfdianPayload {
  return { ec: 200, em: "", data: { order: { out_trade_no: outTradeNo } } };
}

// ================= md5 已知答案向量（关键：不用被测代码反向自证）=================

Deno.test("afdian sign 已知答案向量", () => {
  // 官方向量：token=123, params={"a":333}, ts=1624339905, user_id=abc
  const sign = computeAfdianSign("123", '{"a":333}', 1624339905, "abc");
  assertEquals(sign, "a4acc28b81598b7e5d84ebdc3e91710c");
});

// ================= 纯函数单测 =================

Deno.test("extractBindCode 宽松提取 8 位 base32", () => {
  assertEquals(extractBindCode("我的码 ABCD2345 谢谢"), "ABCD2345");
  assertEquals(extractBindCode("abcd2345"), "ABCD2345"); // 小写归一
  assertEquals(extractBindCode("无码"), null);
  assertEquals(extractBindCode(undefined), null);
  assertEquals(extractBindCode("含0189IO非法字符ABCD2345"), "ABCD2345");
});

Deno.test("resolvePlan / normalizeMonths", () => {
  assertEquals(resolvePlan(1), "monthly");
  assertEquals(resolvePlan(11), "monthly");
  assertEquals(resolvePlan(12), "yearly");
  assertEquals(normalizeMonths({ out_trade_no: "x", month: 12 }), 12);
  assertEquals(normalizeMonths({ out_trade_no: "x" }), 1); // 兜底
  assertEquals(normalizeMonths({ out_trade_no: "x", month: 0 }), 1);
});

Deno.test("computePeriodEnd 从 now 起算", () => {
  const now = new Date("2026-01-01T00:00:00Z");
  const end = computePeriodEnd(now, null, 1);
  assertEquals(end.toISOString(), "2026-02-01T00:00:00.000Z");
});

Deno.test("computePeriodEnd 续订叠加在未来到期日上", () => {
  const now = new Date("2026-01-01T00:00:00Z");
  const existing = "2026-06-01T00:00:00.000Z"; // 未来
  const end = computePeriodEnd(now, existing, 12);
  assertEquals(end.toISOString(), "2027-06-01T00:00:00.000Z");
});

Deno.test("computePeriodEnd 已过期则从 now 起算", () => {
  const now = new Date("2026-01-01T00:00:00Z");
  const existing = "2025-06-01T00:00:00.000Z"; // 已过期
  const end = computePeriodEnd(now, existing, 1);
  assertEquals(end.toISOString(), "2026-02-01T00:00:00.000Z");
});

// ================= handlePayload 流程 =================

Deno.test("ping/test 直接返回 200 不落表", async () => {
  const { store, state } = makeStore();
  const deps = makeDeps(store, makeVerifier({}));
  const r = await handlePayload({ data: { type: "test" } }, deps);
  assertEquals(r.outcome, "ping");
  assertEquals(r.ec, 200);
  assertEquals(state.events.length, 0);
});

Deno.test("订单核实通过 + 有效绑定码 → 激活会员", async () => {
  const bind: BindCodeRow = { id: "b1", user_id: "u1", code: "ABCD2345" };
  const { store, state } = makeStore({ bindCodes: { ABCD2345: bind } });
  // 权威订单（query-order 返回），已支付 status=2
  const order: AfdianOrder = {
    out_trade_no: "T2",
    plan_id: "plan_m",
    month: 1,
    remark: "绑定码 ABCD2345",
    status: 2,
  };
  const deps = makeDeps(store, makeVerifier({ T2: order }));
  const r = await handlePayload(webhook("T2"), deps);
  assertEquals(r.outcome, "activated");
  assertEquals(state.upserts.length, 1);
  assertEquals(state.upserts[0].user_id, "u1");
  assertEquals(state.upserts[0].plan, "monthly");
  assertEquals(state.upserts[0].afdian_trade_no, "T2");
  assertEquals(state.consumed, ["b1"]);
  assertExists(state.events.find((e) => e.outcome === "activated"));
});

Deno.test("query-order 未核实到订单 → order_verify_failed，不激活", async () => {
  const { store, state } = makeStore();
  const deps = makeDeps(store, makeVerifier({ T9: null })); // 核实返回 null
  const r = await handlePayload(webhook("T9"), deps);
  assertEquals(r.outcome, "order_verify_failed");
  assertEquals(state.events[0].outcome, "order_verify_failed");
  assertEquals(state.upserts.length, 0);
});

Deno.test("订单 status≠2（未支付）→ order_verify_failed，不激活", async () => {
  const bind: BindCodeRow = { id: "b1", user_id: "u1", code: "ABCD2345" };
  const { store, state } = makeStore({ bindCodes: { ABCD2345: bind } });
  const order: AfdianOrder = {
    out_trade_no: "T10",
    month: 1,
    remark: "ABCD2345",
    status: 0, // 未支付
  };
  const deps = makeDeps(store, makeVerifier({ T10: order }));
  const r = await handlePayload(webhook("T10"), deps);
  assertEquals(r.outcome, "order_verify_failed");
  assertEquals(state.upserts.length, 0);
});

Deno.test("年费订单判定 yearly（用权威订单 month）", async () => {
  const bind: BindCodeRow = { id: "b1", user_id: "u1", code: "ABCD2345" };
  const { store, state } = makeStore({ bindCodes: { ABCD2345: bind } });
  const order: AfdianOrder = {
    out_trade_no: "T3",
    month: 12,
    remark: "ABCD2345",
    status: 2,
  };
  const deps = makeDeps(store, makeVerifier({ T3: order }));
  await handlePayload(webhook("T3"), deps);
  assertEquals(state.upserts[0].plan, "yearly");
});

Deno.test("续订：已有未来到期日则叠加", async () => {
  const bind: BindCodeRow = { id: "b2", user_id: "u2", code: "WXYZ2345" };
  const existing: SubscriptionRow = {
    user_id: "u2",
    current_period_end: "2026-06-01T00:00:00.000Z",
    afdian_trade_no: "OLD",
  };
  const { store, state } = makeStore({
    bindCodes: { WXYZ2345: bind },
    subsByUser: { u2: existing },
  });
  const order: AfdianOrder = {
    out_trade_no: "T4",
    month: 1,
    remark: "WXYZ2345",
    status: 2,
  };
  const deps = makeDeps(store, makeVerifier({ T4: order }));
  await handlePayload(webhook("T4"), deps);
  assertEquals(state.upserts[0].current_period_end, "2026-07-01T00:00:00.000Z");
});

Deno.test("幂等：同一 out_trade_no 已处理 → dup（在核实前短路）", async () => {
  const existing: SubscriptionRow = {
    user_id: "u1",
    current_period_end: "2026-02-01T00:00:00.000Z",
    afdian_trade_no: "T5",
  };
  const { store, state } = makeStore({ subsByTrade: { T5: existing } });
  // verifier 即使会返回订单也不该导致重复激活
  const order: AfdianOrder = {
    out_trade_no: "T5",
    month: 1,
    remark: "ABCD2345",
    status: 2,
  };
  const deps = makeDeps(store, makeVerifier({ T5: order }));
  const r = await handlePayload(webhook("T5"), deps);
  assertEquals(r.outcome, "dup");
  assertEquals(state.upserts.length, 0);
  assertEquals(state.events[0].outcome, "dup");
});

Deno.test("绑定码缺失 → no_bind_code", async () => {
  const { store, state } = makeStore();
  const order: AfdianOrder = {
    out_trade_no: "T6",
    month: 1,
    remark: "谢谢老板",
    status: 2,
  };
  const deps = makeDeps(store, makeVerifier({ T6: order }));
  const r = await handlePayload(webhook("T6"), deps);
  assertEquals(r.outcome, "no_bind_code");
  assertEquals(state.upserts.length, 0);
});

Deno.test("绑定码无匹配/已消费 → no_user", async () => {
  const { store, state } = makeStore(); // 库中无该码
  const order: AfdianOrder = {
    out_trade_no: "T7",
    month: 1,
    remark: "ABCD2345",
    status: 2,
  };
  const deps = makeDeps(store, makeVerifier({ T7: order }));
  const r = await handlePayload(webhook("T7"), deps);
  assertEquals(r.outcome, "no_user");
  assertEquals(state.upserts.length, 0);
});

Deno.test("plan 白名单不匹配 → plan_mismatch 不激活", async () => {
  const bind: BindCodeRow = { id: "b1", user_id: "u1", code: "ABCD2345" };
  const { store, state } = makeStore({ bindCodes: { ABCD2345: bind } });
  const order: AfdianOrder = {
    out_trade_no: "T8",
    plan_id: "plan_other",
    month: 1,
    remark: "ABCD2345",
    status: 2,
  };
  const deps: Deps = {
    store,
    verifier: makeVerifier({ T8: order }),
    afdianPlanId: "plan_allow",
    now: () => new Date("2026-01-01T00:00:00Z"),
  };
  const r = await handlePayload(webhook("T8"), deps);
  assertEquals(r.outcome, "plan_mismatch");
  assertEquals(state.upserts.length, 0);
});

// ---- serveRequest HTTP 层：ping 必须在 loadEnv 之前放行 ----
// 回归：afdian 配置回调时 secrets 可能尚未设全，ping 不应因缺环境变量而 500。
import { serveRequest } from "./index.ts";

Deno.test("serveRequest: 无任何 env 时 ping 仍返回 200 {ec:200}", async () => {
  // 测试进程未设 AFDIAN_*/SUPABASE_* env，模拟 secrets 未设全的场景。
  // 若 ping 未在 loadEnv 之前放行，此处会因缺环境变量抛异常 → 测试失败。
  const req = new Request("https://x/functions/v1/afdian-webhook", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ec: 200, data: { type: "test" } }),
  });
  const resp = await serveRequest(req);
  assertEquals(resp.status, 200);
  const json = await resp.json();
  assertEquals(json.ec, 200); // afdian 校验 ec===200
});
