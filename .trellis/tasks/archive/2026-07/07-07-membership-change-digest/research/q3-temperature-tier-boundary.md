# Research: Q3 — 全市场温度「4 档」分档边界常量位置

- **Query**: C 触发要复用 /temperature 页现有 4 档温度分档逻辑；定位边界常量/函数确切文件:行，供实现直接复用避免新魔数。
- **Scope**: internal
- **Date**: 2026-07-07

## 结论（一句话）

分档单一真源是 **`frontend/src/lib/breadthColor.ts`**：`TIERS` 常量（L22-27）+ `breadthTier()` 函数（L58-64），边界 **30 / 50 / 70**。**但这是前端 TS，digest 计算在 Python**，后端**无对应常量**（已 grep 确认）——「复用」= 按同一 30/50/70 边界在 Python 侧实现，务必保持数值与 TS 一致以免双真源漂移。

## 证据

### 分档真源：`frontend/src/lib/breadthColor.ts`

```ts
// L22-27  4 档单一来源（图例/tier/纹理/文案全部由此派生）
export const TIERS = [
  { key: 'cold', label: '冰点', min: 0,  max: 30,  mid: 15, hatch: 45 },
  { key: 'cool', label: '偏冷', min: 30, max: 50,  mid: 40, hatch: 0  },
  { key: 'warm', label: '偏暖', min: 50, max: 70,  mid: 60, hatch: 90 },
  { key: 'hot',  label: '过热', min: 70, max: 100, mid: 85, hatch: 135 },
] as const;

// L57-64  站上率 -> tier；阈值 30/50/70
export function breadthTier(rate) {
  if (rate == null || Number.isNaN(rate)) return null;
  if (rate >= 70) return TIERS[3]; // 过热
  if (rate >= 50) return TIERS[2]; // 偏暖
  if (rate >= 30) return TIERS[1]; // 偏冷
  return TIERS[0];                 // 冰点
}
```

- 档位定义：`[0,30) 冰点`、`[30,50) 偏冷`、`[50,70) 偏暖`、`[70,100] 过热`。边界 **30 / 50 / 70**（含左端，`>=`）。
- 消费方（确认这是全站唯一真源）：`frontend/src/components/temperature/BreadthThermometer.tsx`、`BreadthLegend.tsx`（L1 `import { TIERS, breadthColor, breadthTextureCss }`）、`breadthLabel()` 派生文案。

### 输入指标：全市场站上率

- C 用「全市场温度」→ 取 `market_temperature.json → periods.ma20.market` 的最新 `rate`（0-100），喂给上面 4 档判定。
  - 实测 `data/latest`：`ma20.market` 末值 `{date:'2026-07-06', rate:37.5}` → 落 `偏冷`。
- 周期取 ma20（/temperature 温度计默认展示项，见 BreadthThermometer）；实现前可与 design 对齐是否固定 ma20。

### 后端无对应常量（需按同值移植）

- `grep -rniE "冰点|偏冷|偏暖|过热|breadth.*tier|30|50|70(tier上下文)" backend/src` → **无温度分档常量**。
- digest 在 Python（`backend/src/notify/`）跑，故 C 实现需在 Python 侧写一份 30/50/70 → 4 档映射。**风险：与 TS 双真源**。建议在 Python 常量处注释指向 `breadthColor.ts:TIERS`，并加单测钉死边界值，防未来漂移。

## 对 design / implement 的影响

- design §2.2 C「复用其边界常量」需澄清：**跨语言无法直接 import，只能同值移植**。design/implement 里「复用现有分档边界常量」应改述为「按 `frontend/src/lib/breadthColor.ts` 的 30/50/70 边界在 Python 侧对齐实现，单测钉边界」。
- C 还需处理 **mt 文件缺失**（见 Q1 §3：mt 非每日产出，昨日常缺）→ 缺失则跳过 C，不报错（符合 prd「数据缺失安全降级」）。

## Caveats / Not Found

- 未找到把 TIERS 边界抽到跨端共享（如 JSON schema / 后端产出注入）的机制——当前前端硬编码。若想根治双真源，需另开任务把边界下沉到数据产出层，超出本任务范围。
