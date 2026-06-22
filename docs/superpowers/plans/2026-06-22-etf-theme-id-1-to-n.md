# ETF Theme 1:N 归属改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 ETF → theme 的关系从 1:1 升级为 1:N，使跨主题 ETF（如 512480 同属 storage_dram + semiconductor）能被前端识别并展示为「也属于」次要归属。

**Architecture:**
- 后端 `EtfOutput` 增加 `theme_ids: list[str]`，保留 `theme_id: str` 作为主归属（首次出现）。不变量：`theme_id ∈ theme_ids`
- pipeline 预扫 themes 建 `cn_code → list[theme_id]` 映射，etfs 记录每条仍唯一（保留 `cn_codes_seen` 去重），但每条记录携带完整 theme_ids
- 前端 zod 加 `theme_ids?: string[]` 向后兼容；portfolio engine 计算 `secondaryThemes`；HoldingScoreCard 渲染 chip 行 + 边界提示

**Tech Stack:** Python / pydantic v2 / pytest, TypeScript / React / zod / vitest

---

## Task 1: 后端 models.py — EtfOutput 加 theme_ids

**Files:**
- Modify: `backend/src/models.py`
- Test: `backend/tests/test_models.py`

- [x] 加 `theme_ids: list[str] = Field(min_length=1)` 必填，至少 1 项
- [x] 加 `model_validator` 校验 `theme_id ∈ theme_ids`
- [x] 测试：theme_ids 空数组拒绝、不变量校验、跨主题示例

## Task 2: pipeline.py — 填充 theme_ids

**Files:**
- Modify: `backend/src/pipeline.py`

- [x] 在 etfs_list 构建前，扫 themes 建 `cn_code → [theme_id, ...]` 映射（按 themes.yml 配置顺序）
- [x] etfs_list 每条记录 `theme_id` = 映射首项；`theme_ids` = 完整列表
- [x] 保留 `cn_codes_seen` 去重，etfs 数组语义不变（每个 code 一条）

## Task 3: JSON Schema + pipeline 单测

**Files:**
- Modify: `backend/tests/schemas/etfs.schema.json`
- Modify: `backend/tests/test_pipeline_compute_outputs.py`

- [x] schema required 加 theme_ids；properties 加 array of string，minItems 1
- [x] 测试：512480 → `['storage_dram', 'semiconductor']`，theme_id 为首项；不变量对所有 ETF 成立

## Task 4: 回填 data/latest/etfs.json

**Files:**
- Modify: `data/latest/etfs.json`

- [x] Python 脚本读 `config/themes.yml`，按配置顺序构建 cn_code → theme_ids 映射
- [x] 回填所有 34 个 ETF 的 theme_ids 字段（含本地仅 1 个跨主题 ETF 512480）

## Task 5: 前端 zod — EtfSchema

**Files:**
- Modify: `frontend/src/types/etfs.ts`
- Modify: `frontend/src/types/__tests__/schemas.test.ts`

- [x] EtfSchema 加 `theme_ids: z.array(z.string()).optional()`（向后兼容历史快照）
- [x] 测试：缺省可解析、`['storage_dram', 'semiconductor']` 可解析

## Task 6: portfolio engine — secondaryThemes

**Files:**
- Modify: `frontend/src/lib/portfolio/types.ts`
- Modify: `frontend/src/lib/portfolio/engine.ts`
- Modify: `frontend/src/hooks/usePortfolioScores.ts`
- Modify: `frontend/src/lib/portfolio/__tests__/__fixtures__/etfs-mock.ts`
- Modify: `frontend/src/lib/portfolio/__tests__/__fixtures__/themes-mock.ts`
- Modify: `frontend/src/lib/portfolio/__tests__/engine.test.ts`

- [x] EtfMetric 加 `theme_ids?: string[]`
- [x] HoldingScore 加 `secondaryThemes?: { id, name }[]`
- [x] engine 中：secondaryThemes = `theme_ids \ {theme_id}` ∩ themeById，过滤未知主题
- [x] usePortfolioScores 透传 `theme_ids`
- [x] 4 个新测试：跨主题、单主题、未知主题过滤、历史快照（无 theme_ids）

## Task 7: HoldingScoreCard UI — 也属于 chip 行

**Files:**
- Modify: `frontend/src/components/portfolio/HoldingScoreCard.tsx`
- Modify: `frontend/src/components/portfolio/__tests__/HoldingScoreCard.test.tsx`

- [x] 主归属下方渲染「也属于 [chip] [chip] ... · 百分位仅基于主归属计算」
- [x] 最多显示 3 个 chip，超出折叠为 `+N`
- [x] 仅当 `secondaryThemes.length > 0` 才渲染该行（YAGNI）
- [x] 3 个新测试：含次要归属 + 边界提示 / 折叠 +N / 无次要归属时不渲染

## 后续阶段（YAGNI 暂不实现）

- 跨主题共振分析：narrative 引入「次要归属主题信号」描述
- "任一主题共振即提示"的卡片视觉强化
- `is_primary: true` 显式主归属配置（当前依赖 themes.yml 顺序）

## 已知约束

- 历史快照（无 theme_ids 字段）退化为单主题行为，secondaryThemes = undefined
- 主题强度仍只用主归属计算（卡片提示已明确边界）
- 本地 themes.yml 拆分（10683 记录）落地后，跨主题 ETF 数量会变化
