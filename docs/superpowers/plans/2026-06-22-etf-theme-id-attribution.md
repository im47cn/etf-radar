# ETF theme_id 主题归属穿透 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让持仓界面同一主题下的所有 A 股 ETF（不只是 primary_cn）都能正确显示"归属主题/双轨强度/narrative"，并把渲染条件拆开避免"半残卡片"。

**Architecture:** 后端 `EtfOutput` 新增 `theme_id` 字段（pipeline 在循环里 t.id 直接可拿，零成本）→ 前端 zod schema 加 optional theme_id（向后兼容历史快照）→ engine 把"按 primary_cn 索引主题"改为"按 etf.theme_id 反查 themes by id"→ HoldingScoreCard 把 `themeName && (主题+双轨+narrative)` 一锅端的渲染拆成三个独立条件，让缺主题归属时也能显示 ETF 自身百分位与 narrative。

**Tech Stack:** Python 3.11 (pydantic v2, pytest) / TypeScript (zod, vitest, React Testing Library)

**ETF→主题归属语义：** 沿用 `pipeline.py:408-414` 的 `cn_codes_seen` 首次出现归属规则（512480 跨 storage_dram + semiconductor，归 storage_dram）。

---

### Task 1: 后端 `EtfOutput` 增加 `theme_id` 字段

**Files:**
- Modify: `backend/src/models.py:105-112`
- Modify: `backend/src/pipeline.py:408-431`
- Modify: `backend/tests/schemas/etfs.schema.json:13`
- Modify: `backend/tests/test_models.py`
- Modify: `backend/tests/test_pipeline_compute_outputs.py`

- [ ] **Step 1: 写失败测试 — pipeline 产出的 etf 必须带正确 theme_id**

在 `backend/tests/test_pipeline_compute_outputs.py` 末尾追加：

```python
def test_compute_outputs_etf_has_theme_id(monkeypatch):
    """每个 ETF 在 etfs.json 里必须带 theme_id，按 themes 列表首次出现归属。"""
    from src.pipeline import compute_outputs, PipelineMode
    from src.models import ThemeConfig, CnEtfConfig, AlgoConfig
    from datetime import datetime
    from src.etl.calendar import BJT
    import yaml
    from pathlib import Path

    # 用真实 themes.yml 配置（含跨主题 ETF 512480 → storage_dram/semiconductor 首次归 storage_dram）
    raw = yaml.safe_load(Path('config/themes.yml').read_text())
    themes = [ThemeConfig(**t) for t in raw['themes']]
    algo = AlgoConfig(**yaml.safe_load(Path('config/algo.yml').read_text()))

    themes_json, etfs_json, _, _ = compute_outputs(
        themes, us_ohlc={}, cn_ohlc={}, us_failed=[], cn_failed=[], algo=algo,
        asof_bjt=datetime(2026, 6, 22, 16, 0, tzinfo=BJT), mode=PipelineMode.FULL,
    )
    code_to_theme = {e['code']: e['theme_id'] for e in etfs_json['etfs']}

    # 机器人主题两只 ETF 都归 robotics
    assert code_to_theme['562500'] == 'robotics'
    assert code_to_theme['159559'] == 'robotics'
    # 跨主题 ETF 按 themes 列表首次出现归属（storage_dram 在 semiconductor 之前）
    assert code_to_theme['512480'] == 'storage_dram'
    # 所有 etf 都有 theme_id
    assert all(e.get('theme_id') for e in etfs_json['etfs'])
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd backend && uv run --all-extras pytest tests/test_pipeline_compute_outputs.py::test_compute_outputs_etf_has_theme_id -v 2>&1 | tail -10
```
预期 FAIL：`KeyError: 'theme_id'`

- [ ] **Step 3: 改 `backend/src/models.py:105-112` 给 EtfOutput 加 theme_id**

```python
class EtfOutput(BaseModel):
    code: str
    name: str
    tracking_index: str
    theme_id: str
    returns: Returns
    amount_yi: Optional[float] = None
    price: Optional[float] = None
    strength: Strength
```

- [ ] **Step 4: 改 `backend/src/pipeline.py:424-431` 在 etf dict 写入 theme_id**

定位 `etfs_list.append({` 那一段，把 dict 改成：

```python
            etfs_list.append({
                'code': cn.code, 'name': cn.name, 'tracking_index': cn.tracking,
                'theme_id': t.id,
                'returns': r.model_dump(),
                'amount_yi': amount, 'price': price,
                'strength': cn_strengths.get(
                    cn.code, Strength(short=0, mid=0, long=0, composite=0),
                ).model_dump(),
            })
```

- [ ] **Step 5: 改 `backend/tests/schemas/etfs.schema.json` 把 theme_id 加进 required + properties**

把第 13 行 required 数组扩到：
```json
"required": ["code", "name", "tracking_index", "theme_id", "returns", "amount_yi", "price", "strength"],
```

并在 properties 里 `"tracking_index": { "type": "string" },` 下方加：
```json
          "theme_id": { "type": "string", "minLength": 1 },
```

- [ ] **Step 6: 在 `backend/tests/test_models.py` 加 EtfOutput 校验测试**

在该文件末尾追加：

```python
def test_etf_output_requires_theme_id():
    """EtfOutput.theme_id 是必填，缺失应触发 pydantic 校验错误。"""
    from pydantic import ValidationError
    from src.models import EtfOutput, Returns, Strength
    with pytest.raises(ValidationError):
        EtfOutput(
            code='562500', name='机器人ETF', tracking_index='中证机器人',
            returns=Returns(), strength=Strength(short=0, mid=0, long=0, composite=0),
        )
    # 带 theme_id 通过
    e = EtfOutput(
        code='562500', name='机器人ETF', tracking_index='中证机器人',
        theme_id='robotics',
        returns=Returns(), strength=Strength(short=0, mid=0, long=0, composite=0),
    )
    assert e.theme_id == 'robotics'
```

文件顶部如果还没 `import pytest`，需要补上。

- [ ] **Step 7: 跑后端全部测试确认绿**

```bash
cd backend && uv run --all-extras pytest 2>&1 | tail -15
```
预期 PASS。重点关注 `test_output_schemas.py`（schema 校验）+ `test_pipeline_smoke.py` 应全绿。

- [ ] **Step 8: 实跑一次 pipeline 验证 latest/etfs.json 真实落盘了 theme_id**

```bash
cd backend && uv run python -m src.pipeline --mode=full --data-root=../data --config-dir=../config 2>&1 | tail -5
python3 -c "
import json
e = json.load(open('data/latest/etfs.json'))
sample = e['etfs'][0]
print('字段:', list(sample.keys()))
print('159559 →', next(x for x in e['etfs'] if x['code']=='159559')['theme_id'])
print('512480 →', next(x for x in e['etfs'] if x['code']=='512480')['theme_id'])
"
```
预期：字段含 `theme_id`，159559=robotics，512480=storage_dram。

> **失败回退**：网络问题导致 pipeline 抓不到数据时，可跳过此步直接相信 Task 1 单元测试。

- [ ] **Step 9: 提交**

```bash
git add backend/src/models.py backend/src/pipeline.py backend/tests/schemas/etfs.schema.json backend/tests/test_models.py backend/tests/test_pipeline_compute_outputs.py data/latest/etfs.json
git commit -m "$(cat <<'EOF'
feat(backend): add theme_id to EtfOutput for portfolio attribution

让前端持仓界面同主题下非 primary_cn 的 ETF 也能反查归属主题。
首次出现归属语义沿用 pipeline cn_codes_seen 去重逻辑。
EOF
)"
```

---

### Task 2: 前端 EtfSchema 增加 theme_id（向后兼容历史快照）

**Files:**
- Modify: `frontend/src/types/etfs.ts`
- Modify: `frontend/src/types/__tests__/schemas.test.ts`

> **决策**：theme_id 在 zod schema 用 `.optional()`。原因：历史 `data/snapshots/<date>/etfs.json` 没有该字段，强校验会让历史快照崩溃。前端 engine 在缺失时回退到无主题归属（covered 但 themeName=undefined），UI 已经能正确兜底（Task 4）。新 pipeline 产物总会带，所以默认值不会污染当下数据。

- [ ] **Step 1: 改 `frontend/src/types/etfs.ts:4-12` 加 theme_id**

```ts
export const EtfSchema = z.object({
  code: z.string(),
  name: z.string(),
  tracking_index: z.string(),
  theme_id: z.string().optional(),  // 后端 1.x 后开始填；历史 snapshot 可缺
  returns: ReturnsSchema,
  amount_yi: z.number().nonnegative().nullable(),
  price: z.number().positive().nullable(),
  strength: StrengthSchema,
});
```

- [ ] **Step 2: 看 `frontend/src/types/__tests__/schemas.test.ts` 有没有 etf 测试需要追加**

```bash
grep -n "EtfSchema\|etfs" frontend/src/types/__tests__/schemas.test.ts
```
如果已有 etfs 用例 → 追加一个 `theme_id 可缺也可填` 的断言；否则跳过。

具体追加（在 etfs describe 块内）：
```ts
it('EtfSchema 允许 theme_id 缺失（向后兼容历史快照）', () => {
  const raw = {
    code: '562500', name: '机器人ETF', tracking_index: '中证机器人',
    returns: { r_1d: null, r_5d: null, r_20d: null, r_60d: null, r_120d: null, r_ytd: null },
    amount_yi: null, price: 1.5,
    strength: { short: 50, mid: 50, long: 50, composite: 50 },
  };
  expect(() => EtfSchema.parse(raw)).not.toThrow();
  expect(() => EtfSchema.parse({ ...raw, theme_id: 'robotics' })).not.toThrow();
});
```

- [ ] **Step 3: 跑前端 schemas 测试**

```bash
cd frontend && npx vitest run src/types/__tests__/schemas.test.ts 2>&1 | tail -10
```
预期 PASS。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/types/etfs.ts frontend/src/types/__tests__/schemas.test.ts
git commit -m "feat(frontend): EtfSchema add optional theme_id (backward compat with old snapshots)"
```

---

### Task 3: engine 改为按 theme_id 反查主题（含 fixture 与新测试用例）

**Files:**
- Modify: `frontend/src/lib/portfolio/types.ts:67-73` (EtfMetric)
- Modify: `frontend/src/lib/portfolio/engine.ts:7-17,42`
- Modify: `frontend/src/hooks/usePortfolioScores.ts:44-54`
- Modify: `frontend/src/lib/portfolio/__tests__/__fixtures__/etfs-mock.ts`
- Modify: `frontend/src/lib/portfolio/__tests__/engine.test.ts`

- [ ] **Step 1: 写失败测试 — 非 primary_cn 的同主题 ETF 也能归属**

先扩充 fixture，在 `frontend/src/lib/portfolio/__tests__/__fixtures__/etfs-mock.ts` 加一只非 primary 同主题 ETF：

```ts
import type { EtfMetric } from '@/lib/portfolio/types';

export const etfsMock: EtfMetric[] = [
  {
    code: '512480',
    name: '半导体ETF国联安',
    tracking_index: '中证全指半导体',
    theme_id: 'storage_dram',
    price: 2.481,
    strength: { short: 95, mid: 99, long: 99, composite: 98 },
  },
  {
    code: '562500',
    name: '机器人ETF',
    tracking_index: '中证机器人',
    theme_id: 'robotics_theme',
    price: 1.50,
    strength: { short: 75, mid: 70, long: 65, composite: 70 },
  },
  {
    code: '159559',
    name: '机器人ETF景顺',
    tracking_index: '中证机器人产业',
    theme_id: 'robotics_theme',          // 同主题但非 primary_cn
    price: 1.44,
    strength: { short: 73, mid: 76, long: 58, composite: 68 },
  },
  {
    code: '999999',
    name: '弱势ETF',
    theme_id: 'weak_theme',
    price: 1.0,
    strength: { short: 10, mid: 10, long: 10, composite: 10 },
  },
  {
    code: '888888',
    name: '孤儿ETF（theme_id 缺失，仿历史快照）',
    price: 2.0,
    strength: { short: 50, mid: 50, long: 50, composite: 50 },
    // 故意不填 theme_id
  },
];
```

在 `frontend/src/lib/portfolio/__tests__/__fixtures__/themes-mock.ts` 加 robotics_theme：

```ts
import type { ThemeMetric, ThemeSignalEntry } from '@/lib/portfolio/types';

export const themesMock: ThemeMetric[] = [
  {
    id: 'storage_dram',
    name: '存储芯片',
    primary_cn: '512480',
    strength:    { short: 95, mid: 99, long: 99, composite: 98 },
    us_strength: { short: 99, mid: 96, long: 99, composite: 98 },
    cn_strength: { short: 96, mid: 99, long: 98, composite: 98 },
  },
  {
    id: 'robotics_theme',
    name: '机器人',
    primary_cn: '562500',
    strength:    { short: 70, mid: 70, long: 70, composite: 70 },
    us_strength: { short: 72, mid: 68, long: 65, composite: 68 },
    cn_strength: { short: 70, mid: 70, long: 70, composite: 70 },
  },
  {
    id: 'weak_theme',
    name: '弱势主题',
    primary_cn: '999999',
    strength:    { short: 10, mid: 10, long: 10, composite: 10 },
    us_strength: { short: 10, mid: 10, long: 10, composite: 10 },
    cn_strength: { short: 12, mid: 8,  long: 11, composite: 10 },
  },
];

export const themeSignalsMock: ThemeSignalEntry[] = [
  { theme_id: 'storage_dram',   signal: 'resonance' },
  { theme_id: 'robotics_theme', signal: 'transmission' },
  { theme_id: 'weak_theme',     signal: 'divergence' },
];
```

在 `frontend/src/lib/portfolio/__tests__/engine.test.ts` 追加：

```ts
it('非 primary_cn 同主题 ETF (159559) 也能反查到主题', () => {
  const result = scorePortfolio({
    holdings: [baseHolding('159559', 1000, 1.40)],
    themes: themesMock,
    etfs: etfsMock,
    themeSignals: themeSignalsMock,
  });
  const s = result[0];
  expect(s.status).toBe('covered');
  expect(s.themeId).toBe('robotics_theme');
  expect(s.themeName).toBe('机器人');
  expect(s.themeSignal).toBe('transmission');
  expect(s.themeUsStrength).toEqual({ short: 72, mid: 68, long: 65, composite: 68 });
});

it('theme_id 缺失（历史快照）的 ETF: status=covered, themeName=undefined', () => {
  const result = scorePortfolio({
    holdings: [baseHolding('888888', 100, 2.0)],
    themes: themesMock,
    etfs: etfsMock,
    themeSignals: themeSignalsMock,
  });
  const s = result[0];
  expect(s.status).toBe('covered');
  expect(s.themeId).toBeUndefined();
  expect(s.themeName).toBeUndefined();
  expect(s.selfStrength).toEqual({ short: 50, mid: 50, long: 50, composite: 50 });
  expect(s.l2Tag).toBeDefined();
});

it('theme_id 指向未知主题: status=covered, themeName=undefined（防御性）', () => {
  const result = scorePortfolio({
    holdings: [baseHolding('512480', 100, 2.0)],
    themes: themesMock,
    etfs: [{
      code: '512480', name: 'X', tracking_index: 'Y',
      theme_id: 'nonexistent_theme',
      price: 2.0, strength: { short: 50, mid: 50, long: 50, composite: 50 },
    }],
    themeSignals: themeSignalsMock,
  });
  expect(result[0].themeName).toBeUndefined();
  expect(result[0].selfStrength).toBeDefined();
});
```

- [ ] **Step 2: 跑测试确认新用例失败、旧用例的 themeId 也会因索引变更可能受影响**

```bash
cd frontend && npx vitest run src/lib/portfolio/__tests__/engine.test.ts 2>&1 | grep -E "FAIL|×|✓" | head -30
```
预期：3 个新用例 FAIL（159559 未匹配/888888 类型/未知主题 fallback）；旧用例可能继续通过（512480 既是 primary_cn 也将带 theme_id），但不一定 — 看下一步重构后是否全绿。

- [ ] **Step 3: 改 `frontend/src/lib/portfolio/types.ts:67-73` 给 EtfMetric 加 theme_id**

```ts
export interface EtfMetric {
  code:          string;
  name:          string;
  tracking_index?: string;
  theme_id?:     string;
  price:         number;
  strength:      Strength;
}
```

- [ ] **Step 4: 改 `frontend/src/lib/portfolio/engine.ts` 索引与查找逻辑**

把 `engine.ts:9-11` 的索引、第 42 行的查找一并改为按 theme_id：

```ts
export function scorePortfolio(inputs: ScoreInputs): HoldingScore[] {
  const etfByCode = new Map<string, EtfMetric>(inputs.etfs.map(e => [e.code, e]));
  const themeById = new Map<string, ThemeMetric>(
    inputs.themes.map(t => [t.id, t]),
  );
  const signalByTheme = new Map<string, ThemeSignalEntry>(
    inputs.themeSignals.map(s => [s.theme_id, s]),
  );

  return inputs.holdings.map(h => buildScore(h, etfByCode, themeById, signalByTheme));
}
```

把 `buildScore` 第三个参数重命名为 `themeById`，并将函数体内第 42 行改为：

```ts
  // covered
  const theme = etf.theme_id ? themeById.get(etf.theme_id) : undefined;
```

> 注意：原先按 primary_cn 索引时，对 cn_only 主题（primary_cn 可能为 null）已经会丢失部分主题；按 id 索引天然规避，无需 .filter。下一步 usePortfolioScores 的 .filter 也要相应调整。

- [ ] **Step 5: 改 `frontend/src/hooks/usePortfolioScores.ts:44-54` 透传 theme_id 并移除 primary_cn 过滤**

```ts
    const themes: ThemeMetric[] = data.themes.themes.map((t) => ({
      id:          t.id,
      name:        t.name,
      primary_cn:  t.primary_cn ?? '',   // 字段保留兼容，但 engine 不再依赖
      strength:    t.strength,
      us_strength: t.us_strength ?? undefined,
      cn_strength: t.cn_strength ?? undefined,
    }));

    const etfs: EtfMetric[] = data.etfs.etfs
      .filter((e) => e.price !== null)
      .map((e) => ({
        code:           e.code,
        name:           e.name,
        tracking_index: e.tracking_index,
        theme_id:       e.theme_id,
        price:          e.price!,
        strength:       e.strength,
      }));
```

> 由于 ThemeMetric.primary_cn 仍声明为 string（types.ts:61），保留 `?? ''` 兜底，避免类型错。这是 dead 字段后续可拆，此 PR 不动以最小化。

- [ ] **Step 6: 跑全部 portfolio 测试**

```bash
cd frontend && npx vitest run src/lib/portfolio 2>&1 | grep -E "Tests|FAIL|✓|✗" | tail -30
```
预期：全部 PASS。

- [ ] **Step 7: 跑 hooks 测试确认无回归**

```bash
cd frontend && npx vitest run src/hooks 2>&1 | grep -E "Tests|FAIL|✓|✗" | tail -10
```
预期 PASS。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/lib/portfolio/engine.ts frontend/src/lib/portfolio/types.ts frontend/src/hooks/usePortfolioScores.ts frontend/src/lib/portfolio/__tests__/__fixtures__/etfs-mock.ts frontend/src/lib/portfolio/__tests__/__fixtures__/themes-mock.ts frontend/src/lib/portfolio/__tests__/engine.test.ts
git commit -m "$(cat <<'EOF'
feat(portfolio): switch theme lookup to etf.theme_id reverse index

修复同主题非 primary_cn ETF (如 159559 机器人ETF景顺) 持仓卡片归属主题缺失。
theme_id 历史快照可缺，缺失时 covered 但 themeName=undefined，由 UI 兜底。
EOF
)"
```

---

### Task 4: HoldingScoreCard 拆开渲染条件（避免半残卡片）

**Files:**
- Modify: `frontend/src/components/portfolio/HoldingScoreCard.tsx:135-164`
- Modify: `frontend/src/components/portfolio/__tests__/HoldingScoreCard.test.tsx`

- [ ] **Step 1: 写失败测试 — 无主题归属时仍显示自身百分位 + narrative + 提示**

在 `frontend/src/components/portfolio/__tests__/HoldingScoreCard.test.tsx` 顶部 `uncoveredScore` 下方追加：

```ts
const coveredNoThemeScore: HoldingScore = {
  etfCode: '159559',
  status: 'covered',
  name: '机器人ETF景顺',
  shares: 1000,
  costPrice: 1.40,
  currentPrice: 1.44,
  marketValue: 1440,
  pnlAbs: 40,
  pnlPct: 0.0286,
  selfStrength: { short: 73, mid: 76, long: 58, composite: 68 },
  // 故意不填 themeId/themeName/themeUsStrength —— 仿"主题归属缺失"
  quadrant: 'leading',
  l2Tag: '中性偏强',
  momentumTag: '动量向上',
  narrative: '综合 68 分位，短中周期偏强',
};
```

在 describe 内追加：

```ts
it('covered 但无主题归属: 显示 ETF 自身百分位 + narrative, 不渲染归属主题区', () => {
  render(<HoldingScoreCard score={coveredNoThemeScore} onDelete={vi.fn()} />);
  // 仍是 covered 风格
  expect(screen.getByText(/中性偏强/)).toBeInTheDocument();
  expect(screen.getByText(/动量向上/)).toBeInTheDocument();
  // 自身百分位仍可见
  expect(screen.getByText(/ETF 自身百分位/)).toBeInTheDocument();
  expect(screen.getByText(/综合 68/)).toBeInTheDocument();
  // narrative 仍可见
  expect(screen.getByText(/综合 68 分位/)).toBeInTheDocument();
  // 归属主题区域不渲染
  expect(screen.queryByText(/归属主题/)).toBeNull();
  expect(screen.queryByText(/双轨强度/)).toBeNull();
  // 不应误判为 uncovered
  expect(screen.queryByText(/无信号/)).toBeNull();
  expect(screen.queryByText(/不在信号覆盖范围/)).toBeNull();
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/HoldingScoreCard.test.tsx 2>&1 | grep -E "FAIL|×|✓" | tail -15
```
预期 FAIL：`ETF 自身百分位` 找不到（因为外层 `score.themeName &&` 拦截了整段）。

- [ ] **Step 3: 重构 `HoldingScoreCard.tsx:135-164` 拆开渲染条件**

把那段替换为：

```tsx
      {/* covered: 信号区 — 拆成三段独立条件,避免一个缺失全部不渲染 */}
      {!isUncovered && (
        <div className="mt-3 pt-2 border-t text-sm space-y-2">
          {score.themeName ? (
            <div className="text-gray-600">归属主题：<span className="font-medium text-gray-900">{score.themeName}</span></div>
          ) : (
            <div className="text-xs text-gray-400">ⓘ 未归入主题分组（暂无双轨信号）</div>
          )}

          {score.selfStrength && (
            <div className={`grid ${score.themeUsStrength ? 'grid-cols-2' : 'grid-cols-1'} gap-2 text-xs`}>
              {score.themeUsStrength && (
                <div className="border rounded p-2">
                  <div className="text-gray-500 mb-1">双轨强度（美/A）</div>
                  <div>美 短{score.themeUsStrength.short} 中{score.themeUsStrength.mid} 长{score.themeUsStrength.long}</div>
                  {score.themeCnStrength && (
                    <div>A 短{score.themeCnStrength.short} 中{score.themeCnStrength.mid} 长{score.themeCnStrength.long}</div>
                  )}
                </div>
              )}
              <div className="border rounded p-2">
                <div className="text-gray-500 mb-1">ETF 自身百分位</div>
                <div>短 {score.selfStrength.short}</div>
                <div>中 {score.selfStrength.mid}</div>
                <div>长 {score.selfStrength.long}</div>
                <div>综合 {score.selfStrength.composite}</div>
              </div>
            </div>
          )}

          {score.narrative && (
            <div className="text-gray-700 text-xs leading-relaxed bg-gray-50 p-2 rounded">
              {score.narrative}
            </div>
          )}
        </div>
      )}
```

- [ ] **Step 4: 跑 HoldingScoreCard 测试**

```bash
cd frontend && npx vitest run src/components/portfolio/__tests__/HoldingScoreCard.test.tsx 2>&1 | grep -E "Tests|FAIL|✓|×" | tail -15
```
预期：全部 PASS（含旧 covered 完整字段、uncovered 灰版、新增的无主题归属 covered）。

- [ ] **Step 5: 跑前端全部测试做回归扫描**

```bash
cd frontend && npx vitest run 2>&1 | tail -10
```
预期：Test Files / Tests 全 PASS，无 FAIL。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/components/portfolio/HoldingScoreCard.tsx frontend/src/components/portfolio/__tests__/HoldingScoreCard.test.tsx
git commit -m "$(cat <<'EOF'
fix(portfolio): split HoldingScoreCard render so missing theme doesn't blank self percentile

原 \`themeName && (整段)\` 一锅端导致同主题非 primary_cn ETF 卡片显示半残。
拆成三段独立条件：归属主题/双轨强度/narrative 各自按字段存在性渲染。
EOF
)"
```

---

### Task 5: 端到端验证

**Files:** 无修改。仅本地启动 dev server 视觉确认。

- [ ] **Step 1: 后端 + 前端同时跑通**

```bash
cd backend && uv run --all-extras pytest 2>&1 | tail -5
cd frontend && npx vitest run 2>&1 | tail -5
```
预期：两边全绿。

- [ ] **Step 2: 视觉验证（如需）**

```bash
cd frontend && npm run dev
```
然后在持仓页录入 159559（机器人ETF景顺）+ 562500（机器人ETF），对比卡片：
- 两张卡片都应显示 `归属主题：机器人`
- 两张卡片都应显示双轨强度 + 自身百分位
- 录入一个故意造的 covered 但 theme_id 缺失场景（可暂时手动改 etfs.json 测试，验证后 git checkout 还原），应显示 `ⓘ 未归入主题分组` + 自身百分位仍在

- [ ] **Step 3: 推送（按用户惯例：不要主动 push，等用户指令）**

按 CLAUDE.md 约定：**不要主动 push**。提示用户验收后再决定是否推送。

---

## Self-Review

**1. Spec coverage：**
- ✅ 后端 `etfs.json` 加 `theme_id`（Task 1）
- ✅ 前端 engine 用反查（Task 3）
- ✅ HoldingScoreCard 拆开渲染兜底（Task 4）

**2. Placeholder scan：** 无 TBD / TODO / "实现细节" 字样，所有代码块完整。

**3. Type consistency：**
- `EtfOutput.theme_id: str` (后端必填) vs `EtfSchema.theme_id?: string` (前端 optional) — 一致：后端必产、前端兼容历史。
- `EtfMetric.theme_id?: string` 与 `etf.theme_id ? themeById.get(...) : undefined` 兼容。
- `themeById` 命名在 engine.ts 与 buildScore 第三参一致。

**4. 跨主题 ETF（512480）语义：** Task 1 测试断言 `code_to_theme['512480'] == 'storage_dram'`，与 `pipeline.py:412` 首次见到归属语义对齐。
