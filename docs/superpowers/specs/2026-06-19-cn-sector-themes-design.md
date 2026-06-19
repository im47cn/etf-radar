# A股独立行业主题融合 · 设计文档

- **日期**: 2026-06-19
- **作者**: brainstorm 推导（dreambt + Claude）
- **状态**: 已通过设计评审，待写实施计划
- **关联问题**: 主题轮动当前仅覆盖 14 个中美映射主题，未覆盖白酒/消费/医疗器械/家电/地产/传媒/红利等 A 股主流行业 ETF 赛道

---

## 1. 背景

### 1.1 现状

- `config/themes.yml` 共 14 个主题，全部为"美股主题 → A 股 ETF"映射型，`ThemeConfig` 强制要求 `us_etfs` 与 `primary_us`。
- 主题列表（`ThemeList`）、轮动散点图（`RotationScatterWithTrails`）的核心数据 `strength` 实际来源是**美股 ETF 池**的相对强度。
- 多个 A 股主流行业（如白酒、消费、医疗器械、家电、地产、传媒、红利）因无对应美股纯主题 ETF，未进入产品。

### 1.2 业务诉求

让"主题轮动"在产品语义上覆盖 A 股主流行业 ETF，弥补盲区；同时不破坏现有 14 主题的行为与历史快照兼容性。

### 1.3 非目标

- **不**改变现有 14 主题的 strength 计算口径（保持向后兼容）
- **不**引入与 theme 并列的 sector 抽象（避免认知负担与双 schema）
- **不**追求 A 股全行业覆盖（YAGNI，本期仅 7 个高优先级赛道）

---

## 2. 决策汇总

| 维度 | 选择 | 理由 |
|---|---|---|
| 展示形态 | 融合到现有主题列表 | 复用 ThemeList/Rotation/前端组件，最低改动 |
| 行业范围 | 精选 7 个：白酒、主要消费、医疗器械、家电、地产、传媒、红利 | 覆盖最缺失的主流大类，避免稀释 strength 排名 |
| 行业分类标准 | 自定义热门赛道集 | 与现有 14 主题风格一致；标准行业分类（中证/申万）颗粒过粗或过细 |
| Strength 策略 | 双 strength（保留 US，新增 CN），全主题双算 | 散点图模式切换数据现成，逻辑对称 |
| 配置文件组织 | 单文件扩展 `config/themes.yml` | 单一数据源，加载逻辑零改动 |
| 数据模型放宽 | `us_etfs/primary_us` 改 Optional + 新增 `primary_cn` | 向后兼容，pipeline 加分支即可 |
| 散点图模式 UI | Tab 切换（默认美股） | 最简单，沿用现有默认行为 |

---

## 3. 架构与改动范围

### 3.1 改动文件清单

```
Phase 1（本设计主体）
├─ config/themes.yml                            +~50 行（7 个新主题）
├─ backend/src/models.py                        ~20 行（ThemeConfig/Theme schema）
├─ backend/src/pipeline.py                      ~40 行（CN 池 strength、Optional 分支）
├─ backend/src/scoring/signals.py               ~5 行（None 兜底）
├─ backend/tests/schemas/themes.schema.json     schema 1.1
├─ backend/tests/fixtures/themes_minimal.yml    +1 cn_only 条目
├─ backend/tests/test_config_loader.py          补充用例
├─ backend/tests/test_models.py                 补充用例
├─ backend/tests/test_pipeline_compute_outputs.py  新增 cn_only fixture 用例
├─ backend/tests/test_pipeline_provider_chain.py   纯 A 股主题 provider chain
├─ backend/tests/test_output_schemas.py         schema 1.1 校验
├─ backend/tests/test_signals.py                None 兜底
├─ frontend/src/types/themes.ts                 字段扩展
├─ frontend/src/lib/rotation.ts                 模式参数
├─ frontend/src/components/rotation/ModeToggle.tsx       新组件
├─ frontend/src/components/rotation/__tests__/ModeToggle.test.tsx
├─ frontend/src/components/rotation/__tests__/rotation.test.ts  补充用例
├─ frontend/src/components/ThemeList/ThemeRow.tsx        A 股专属 pill
├─ frontend/src/components/ThemeList/__tests__/ThemeRow.test.tsx
├─ frontend/src/components/ThemeDetail/MappingPanel.tsx  无映射兜底
├─ frontend/src/components/FilterBar/index.tsx           新增 checkbox
└─ frontend/src/__fixtures__/snapshots.ts       fixture 扩充

Phase 2（独立 PR，不阻塞 Phase 1）
├─ config/themes.yml                            cybersecurity/storage_dram 标注与微调
└─ backend/scripts/audit_theme_etf_health.py    新脚本（~80 行）
```

---

## 4. 详细设计

### 4.1 配置增量 (`config/themes.yml`)

在现有 14 主题后追加 7 个条目：

```yaml
- id: cn_liquor
  name: 白酒
  tags: [白酒, 主要消费]
  primary_cn: '512690'
  cn_etfs:
    - { code: '512690', name: '酒ETF', tracking: '中证酒', match_type: exact }

- id: cn_consumer_staples
  name: 主要消费
  tags: [消费, 食品饮料]
  primary_cn: '159928'
  cn_etfs:
    - { code: '159928', name: '消费ETF', tracking: '中证主要消费', match_type: exact }

- id: cn_medical_devices
  name: 医疗器械
  tags: [医疗器械, 医药]
  primary_cn: '159883'
  cn_etfs:
    - { code: '159883', name: '医疗器械ETF', tracking: '中证全指医疗器械', match_type: exact }

- id: cn_home_appliances
  name: 家电
  tags: [家电, 可选消费]
  primary_cn: '159996'
  cn_etfs:
    - { code: '159996', name: '家电ETF', tracking: '中证全指家电', match_type: exact }

- id: cn_real_estate
  name: 房地产
  tags: [地产]
  primary_cn: '512200'
  cn_etfs:
    - { code: '512200', name: '地产ETF', tracking: '中证800地产', match_type: exact }

- id: cn_media
  name: 传媒
  tags: [传媒, 游戏, TMT]
  primary_cn: '159805'
  cn_etfs:
    - { code: '159805', name: '传媒ETF', tracking: '中证传媒', match_type: exact }

- id: cn_dividend
  name: 红利
  tags: [红利, 高股息]
  primary_cn: '510880'
  cn_etfs:
    - { code: '510880', name: '红利ETF', tracking: '上证红利', match_type: exact }
```

**实施前必须**：用 AkshareEM 拉一次实时数据二次核对 ETF 代码/名称/跟踪指数是否变更。

### 4.2 后端数据模型 (`backend/src/models.py`)

```diff
 class ThemeConfig(BaseModel):
     id: str
     name: str
-    us_etfs: list[str]
-    primary_us: str
+    us_etfs: list[str] = Field(default_factory=list)
+    primary_us: Optional[str] = None
+    primary_cn: Optional[str] = None
     tags: list[str]
     note: Optional[str] = None
     cn_etfs: list[CnEtfConfig]
+
+    @model_validator(mode='after')
+    def _validate_primary(self) -> 'ThemeConfig':
+        if not self.primary_us and not self.primary_cn:
+            raise ValueError(f"theme {self.id}: primary_us or primary_cn required")
+        if self.primary_us and self.primary_us not in self.us_etfs:
+            raise ValueError(f"theme {self.id}: primary_us must be in us_etfs")
+        return self

 class Theme(BaseModel):
     id: str
     name: str
-    strength: Strength
+    us_strength: Optional[Strength] = None    # 纯 A 股主题为 None
+    cn_strength: Optional[Strength] = None    # 全主题双算
+    strength: Strength                         # 兼容字段 = us_strength ?? cn_strength
     ...
```

### 4.3 Pipeline 改动 (`backend/src/pipeline.py`)

1. **符号收集**：`if t.us_etfs: symbols.update(t.us_etfs)` 容错空 us
2. **US 池 strength**：现有逻辑保留，**跳过** `primary_us is None` 的主题（不参与 US 池排名）
3. **CN 池 strength**（新增）：
   - 主题 CN 代表 ETF = `t.primary_cn or t.cn_etfs[0].code`
   - 用全部 21 个主题各自的代表 ETF 组成 CN 池子（21 个 ETF）
   - 对每个主题算其代表 ETF 相对该池的 strength → `cn_theme_strengths[theme_id]`
   - **现有 14 主题代表选择说明**：本期暂取 `cn_etfs[0]`（第一个 ETF）作为代表，不保证是该主题最纯标的。优化代表选择（如显式补 `primary_cn` 字段指明 SOXX 对应的最纯标的）放在 Phase 2 的清单中。
4. **Theme 组装**：
   ```python
   us_s = theme_strengths.get(t.id)        # 可能 None
   cn_s = cn_theme_strengths.get(t.id)     # 基本都有
   strength = us_s or cn_s                 # 向后兼容字段
   ```

### 4.4 Signal 模块 (`backend/src/scoring/signals.py`)

纯 A 股主题（`primary_us is None`）：
- `resonance` / `transmission` / `divergence` 强制 `None`（无中美对比基准）
- `SignalsSummary` 计数时过滤 None

### 4.5 Schema 升级

`themes.json` schema_version: `1.0 → 1.1`

```diff
 {
   "id": "...",
-  "primary_us": "DRAM",
+  "primary_us": "DRAM",        // 1.1：可为 null
+  "primary_cn": "159928",      // 1.1：新增，可为 null
   "us_etfs": [...],            // 1.1：可为 []
-  "strength": {...}
+  "strength": {...},           // 兼容字段，= us_strength ?? cn_strength
+  "us_strength": {...} | null,
+  "cn_strength": {...} | null
 }
```

`meta.json` 增加：
```json
{
  "theme_kinds": { "mapped": 14, "cn_only": 7 }
}
```

**兼容策略**：
- 旧前端读 `strength` 字段照常工作（始终非空）
- 历史快照（schema 1.0）走 `snapshots_index` 现有的 schema_version 路由（已支持多版本）
- 不回填历史快照，backfill 只追加未来快照

### 4.6 前端类型与组件

**`frontend/src/types/themes.ts`**：
```diff
 export interface Theme {
-  primaryUs: string;
+  primaryUs: string | null;
+  primaryCn: string | null;
   usEtfs: string[];
   strength: Strength;           // 兼容字段
+  usStrength: Strength | null;
+  cnStrength: Strength | null;
 }
```

**RotationPage / RotationScatterWithTrails**：
- 顶部 Tab：`[美股强度] [A股强度]`，默认美股
- 状态：`const [mode, setMode] = useState<'us'|'cn'>('us')`
- `themesToRotationPoints(themes, mode)` 新增第二参数
- 纯 A 股主题（`usStrength === null`）在美股模式下被过滤
- Tab 旁显示当前模式主题计数：`美股 14 / A股 21`
- 轨迹（trails）同步切换；历史快照无 cnStrength 时显示空心点（沿用 staleness 视觉）

**ThemeList/ThemeRow**：
- 纯 A 股主题右侧加 pill：`A 股专属`（与 tag pill 同款样式）
- 排序仍按 `strength.composite` 倒序，融合排

**ThemeDetail/MappingPanel**：
- `primaryUs === null` 时整块替换为提示卡："本主题为 A 股本土赛道，无对应美股主题"

**FilterBar**：
- 新增 checkbox：`[ ] 仅看 A 股专属`，默认关闭

---

## 5. 错误处理与降级

| 场景 | 行为 |
|---|---|
| 纯 A 股主题的 CN provider 全链失败 | 该主题 strength 缺失，列表过滤掉，meta.fallback_symbols 记录 |
| 历史快照 schema 1.0（无 cn_strength） | 散点图 A 股模式下该日数据点缺失，轨迹断点显示空心点 |
| `primary_cn` 配置错误（不在 cn_etfs.code 中） | 加载时 ValidationError 抛出，pipeline 拒绝启动 |
| 用户切到 A 股模式但所有主题都无 cnStrength | 显示空状态："暂无 A 股强度数据" + 重置 Tab 按钮 |

---

## 6. 测试策略

### 6.1 后端（pytest）

| 测试文件 | 用例 |
|---|---|
| `test_config_loader.py` | 加载含 `primary_cn` 的 themes；缺 `primary_us` 且缺 `primary_cn` 应 ValidationError |
| `test_models.py` | `model_validator` 双向校验；`Theme` 同时含 us/cn strength 序列化往返 |
| `test_pipeline_compute_outputs.py` | 新增 `test_compute_outputs_cn_only_theme`：注入 1 个纯 A 股 fixture 主题，断言 `us_strength=None`、`cn_strength` 非空、`strength == cn_strength`；现有用例补 `cn_strength` 断言 |
| `test_pipeline_provider_chain.py` | 纯 A 股主题走 CN provider 链正常 |
| `test_output_schemas.py` | themes.json 通过 schema 1.1 校验；schema 1.0 fixture 仍能加载（兼容） |
| `test_signals.py` | 纯 A 股主题 `resonance/transmission/divergence = None`；`SignalsSummary` 计数跳过 None |
| `tests/fixtures/themes_minimal.yml` | 补 1 个 cn_only 条目作为夹具 |

### 6.2 前端（vitest）

| 测试文件 | 用例 |
|---|---|
| `lib/__tests__/rotation.test.ts` | `themesToRotationPoints(themes, 'cn')` 过滤无 cnStrength；模式切换返回不同点集 |
| `components/rotation/__tests__/ModeToggle.test.tsx`（新） | Tab 切换状态、计数显示 |
| `components/ThemeList/__tests__/ThemeRow.test.tsx`（新） | 纯 A 股主题渲染 `A 股专属` pill |
| `__fixtures__/snapshots.ts` | fixture 增补 cn_only 主题样本 |

### 6.3 E2E（playwright，1 条冒烟）

- 打开 RotationPage → 默认看到散点 → 切到"A 股强度" → 出现新主题且 pill 显示

### 6.4 回归验证

跑 backfill 一个最新快照 → 对比 `data/snapshots/<today>/themes.json` 主题数 = 21，14 个有 us_strength，所有 21 个有 cn_strength。

---

## 7. Phase 2 · 美中映射优化清单

**目标**：补全/升级现有 14 个映射主题的 A 股侧覆盖与匹配纯度。

| 主题 | 现状问题 | 优化动作 |
|---|---|---|
| `cybersecurity` | `512720 计算机ETF` 是 `wide` 匹配 | 调研有无更窄的安全/信创 ETF（如 `159755 信创ETF`），加入次选；保留 wide 标注 |
| `storage_dram` | "A 股无纯存储基金"，依赖 `512480/512760` 半导体宽匹配 | 与 `semiconductor` cn_etfs 高度重叠 → 不再扩，加 `note` 说明与 semiconductor 是兄弟主题 |
| `china_internet` | 已含 `513050/513330`，覆盖 OK | 不动 |
| 其余 11 个 | 大多 `exact` 匹配 | 用 AkshareEM 拉一次实时数据核查 ETF 名称/代码现仍存活、规模未严重萎缩（< 1 亿可考虑替换） |
| 全部 14 个 | 缺 `primary_cn` 字段，CN 池代表 ETF 取 `cn_etfs[0]` 可能非最纯标的 | 评审并补全 `primary_cn` 字段，确保 CN 模式散点图的代表 ETF 最贴合主题 |

**新增工具脚本** `backend/scripts/audit_theme_etf_health.py`：
- 读取 `themes.yml`，对每个 `cn_etfs.code` 拉取最新规模/日均成交
- 输出 markdown 报告：`docs/reports/theme-etf-health-<date>.md`
- 不修改配置，只产出建议清单供人工审阅

**Phase 2 不阻塞 Phase 1**，可在 Phase 1 上线后独立排期。

---

## 8. 风险与权衡

| 风险/权衡 | 应对 |
|---|---|
| US 与 CN 池子的 strength 数值口径不同 | 通过 Tab 强分隔，并在 Tab 旁注明数据源；不在同一图上混合 |
| 21 主题摊薄 strength 排名分母 | 池子分离（US 池仍 14、CN 池 21），互不干扰 |
| 历史快照轨迹断点 | 接受，沿用现有 staleness 空心点视觉 |
| 实施前 ETF 代码失效风险 | 写入配置前用 AkshareEM 二次核对，发现失效则选替代 ETF 并回到设计评审 |
| 用户对"A 股专属"pill 视觉打扰 | 用与 tag pill 同款样式，颜色克制；若反馈强烈可后续移除 |

---

## 9. 验收标准

1. `config/themes.yml` 含 21 个主题（14 mapped + 7 cn_only），全部通过模型校验
2. 最新快照 `themes.json` schema_version=1.1，21 主题全部有 `cn_strength`，14 主题额外有 `us_strength`
3. 主题列表（ThemeList）按 `strength.composite` 融合排序，纯 A 股主题显示 `A 股专属` pill
4. 散点图默认美股模式（显示 14 点），切到 A 股模式显示 21 点
5. 所有现有测试通过，新增测试通过
6. 历史快照（schema 1.0）能正常加载，A 股模式下显示空心点轨迹
7. ThemeDetail 中纯 A 股主题的 MappingPanel 显示无映射提示

---

## 10. 后续工作（超出本设计范围）

- Phase 2 美中映射优化（见第 7 节）
- 若 Phase 1 上线后用户反馈良好，考虑加入更多 A 股赛道（如食品饮料、CXO、基建、钢铁、农业、央企）—— 走相同的设计流程
- 散点图模式切换可演进为下拉框（如未来加"宽基模式""中观模式"等）
