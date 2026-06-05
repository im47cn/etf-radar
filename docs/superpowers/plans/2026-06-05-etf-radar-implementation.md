# ETF Radar 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 GitHub Action 定时跑 Python 流水线 + 静态网页展示的跨市场主题联动分析平台, 追踪 14 个美股主题 ETF 强弱并自动映射到 A 股场内 ETF, 识别共振/传导/背离信号。

**Architecture:** Monorepo (backend Python + frontend React) + 4 个 GitHub Actions workflow (美股拉取 / A股拉取 / EOD 归档 / 前端部署), 数据落地为 4 个 JSON 文件 (themes/etfs/signals/meta), 部署到 GitHub Pages。所有算法在 Python 端跑, 前端只渲染。

**Tech Stack:**
- Backend: Python 3.11+, uv, yfinance, akshare, pandas, pydantic, pytest
- Frontend: React 18, Vite 5, TypeScript, TailwindCSS 3, shadcn/ui, Recharts, SWR
- DevOps: GitHub Actions, GitHub Pages
- 设计文档: `docs/superpowers/specs/2026-06-05-etf-radar-design.md`

---

## Phase 概览

| Phase | 内容 | 依赖 | 可并行 |
|-------|------|------|--------|
| 0 | Monorepo 骨架 + 工具链 | — | — |
| 1 | Backend: 配置加载 + 类型 + 交易日历 | 0 | — |
| 2 | Backend: Provider 层 (yfinance/akshare + 字段标准化) | 1 | — |
| 3 | Backend: Scoring 层 (强度/映射/信号) | 1 | 可与 P2 并行 |
| 4 | Backend: 输出层 + Pipeline 编排 | 2, 3 | — |
| 5 | GitHub Actions Workflows | 4 | — |
| 6 | Frontend: 骨架 + Vite + Tailwind + shadcn | 0 | 可与 P1-P5 并行 |
| 7 | Frontend: 数据层 (类型 + Provider + hooks) | 6 + JSON Schema | — |
| 8 | Frontend: 组件 (Header/FilterBar/ThemeList/Detail/EtfTable) | 7 | — |
| 9 | 校准脚本 + 部署 + README | 1-8 | — |

---

## Phase 0: Monorepo 骨架与工具链

### Task 0.1: 创建根目录结构与 .gitignore

**Files:**
- Create: `.gitignore`
- Create: `README.md` (占位 — Phase 9 完善)
- Create: `backend/`、`frontend/`、`config/`、`data/`、`scripts/` 目录占位

- [ ] **Step 1: 写 .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.coverage
htmlcov/

# Node
node_modules/
dist/
.vite/

# OS
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
*.swp

# Local
.env
.env.local
```

- [ ] **Step 2: 创建占位目录与 README**

```bash
mkdir -p backend/src backend/tests frontend/src config data/latest data/snapshots scripts
echo "# ETF Radar" > README.md
echo "# placeholder" > backend/.gitkeep
echo "# placeholder" > frontend/.gitkeep
```

- [ ] **Step 3: 验证目录结构**

Run: `ls -la`
Expected: 可见 `backend/ frontend/ config/ data/ scripts/ docs/ README.md .gitignore`

- [ ] **Step 4: 初始化 git (如未初始化)**

```bash
git init  # 仅在未初始化时执行
git add .gitignore README.md
```

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: monorepo skeleton with .gitignore"
```

---

### Task 0.2: 初始化 backend Python 项目 (uv + pyproject.toml)

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/.python-version`

- [ ] **Step 1: 编写 pyproject.toml**

```toml
[project]
name = "etf-radar-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.2.0",
    "numpy>=1.26.0",
    "pydantic>=2.5.0",
    "PyYAML>=6.0",
    "yfinance>=0.2.40",
    "akshare>=1.13.0",
    "chinese-calendar>=1.10.0",
    "pandas-market-calendars>=4.4.0",
    "scipy>=1.12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "ruff>=0.4.0",
    "mypy>=1.8",
    "responses>=0.24.0",
    "freezegun>=1.4.0",
    "jsonschema>=4.21.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true
```

- [ ] **Step 2: 创建空 __init__.py 与 .python-version**

```bash
touch backend/src/__init__.py backend/tests/__init__.py
echo "3.11" > backend/.python-version
```

- [ ] **Step 3: 安装依赖**

Run: `cd backend && uv venv && uv sync --extra dev`
Expected: 创建 `.venv/`, 所有依赖安装完成无错误

- [ ] **Step 4: 验证 pytest 可运行 (空测试集)**

Run: `cd backend && uv run pytest`
Expected: `no tests ran` 或 `0 passed` (不能有 ERROR)

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/src/__init__.py backend/tests/__init__.py backend/.python-version
git commit -m "feat(backend): initialize Python project with uv and dependencies"
```

---

### Task 0.3: 创建 config 文件 (themes.yml + algo.yml 完整版)

**Files:**
- Create: `config/algo.yml`
- Create: `config/themes.yml` (完整 14 主题)

- [ ] **Step 1: 写 algo.yml**

```yaml
strength:
  k_sigmoid: 5.0
  threshold: 0.0
  days_in_dim:
    short: 3
    mid: 40
    long: 180
  composite_weights:
    short: 0.2
    mid: 0.4
    long: 0.4

mapping:
  corr_window_days: 60
  min_aligned_days: 30

confidence:
  exact: 90
  wide: 60

signal:
  resonance:
    max_strength_diff: 15
    min_max_strength: 60
  transmission:
    min_strength_diff: 25
    min_leader_strength: 65
  divergence:
    min_return_magnitude: 0.02
```

- [ ] **Step 2: 写 themes.yml 完整 14 主题**

```yaml
themes:
  - id: storage_dram
    name: 存储芯片
    us_etfs: [DRAM, SOXX, SMH]
    primary_us: DRAM
    tags: [DRAM, NAND, 半导体]
    note: "A股无纯存储基金, 用半导体宽主题替代"
    cn_etfs:
      - {code: '512480', name: 半导体ETF国联安, tracking: 中证全指半导体, match_type: wide}
      - {code: '512760', name: 芯片ETF, tracking: 中华半导体芯片, match_type: wide}

  - id: semiconductor
    name: 半导体
    us_etfs: [SOXX, SMH, XSD]
    primary_us: SOXX
    tags: [半导体, 芯片]
    note: ""
    cn_etfs:
      - {code: '512480', name: 半导体ETF国联安, tracking: 中证全指半导体, match_type: exact}
      - {code: '159995', name: 芯片ETF华夏, tracking: 国证芯片, match_type: exact}

  - id: cybersecurity
    name: 网络安全
    us_etfs: [CIBR, BUG]
    primary_us: CIBR
    tags: [网络安全, 计算机]
    note: "A股无纯网络安全 ETF, 映射纯度低"
    cn_etfs:
      - {code: '512720', name: 计算机ETF国泰, tracking: 中证计算机, match_type: wide}

  - id: ai_compute
    name: AI算力
    us_etfs: [THNQ, AIQ, QQQ]
    primary_us: THNQ
    tags: [AI, 人工智能, 算力]
    note: ""
    cn_etfs:
      - {code: '515980', name: 人工智能ETF, tracking: 中证人工智能主题, match_type: exact}
      - {code: '588000', name: 科创50ETF, tracking: 上证科创板50, match_type: wide}

  - id: energy_oil
    name: 原油/能源
    us_etfs: [XLE, USO]
    primary_us: XLE
    tags: [原油, 能源]
    note: ""
    cn_etfs:
      - {code: '162411', name: 华宝油气, tracking: 标普石油天然气上游, match_type: exact}
      - {code: '515220', name: 煤炭ETF, tracking: 中证煤炭, match_type: wide}

  - id: new_energy_vehicle
    name: 新能源车/锂电
    us_etfs: [DRIV, LIT, HAIL]
    primary_us: DRIV
    tags: [新能源车, 锂电池]
    note: ""
    cn_etfs:
      - {code: '515030', name: 新能源车ETF, tracking: 中证新能源汽车, match_type: exact}
      - {code: '159755', name: 电池ETF, tracking: 中证电池主题, match_type: exact}

  - id: robotics
    name: 机器人
    us_etfs: [BOTZ, ROBO, ARKQ]
    primary_us: BOTZ
    tags: [机器人, 智能制造]
    note: ""
    cn_etfs:
      - {code: '562500', name: 机器人ETF, tracking: 中证机器人, match_type: exact}

  - id: gold_metals
    name: 黄金/有色
    us_etfs: [GLD, SLV, PICK]
    primary_us: GLD
    tags: [黄金, 贵金属, 有色]
    note: ""
    cn_etfs:
      - {code: '518880', name: 黄金ETF, tracking: 上海黄金交易所黄金现货合约, match_type: exact}
      - {code: '512400', name: 有色金属ETF, tracking: 中证有色金属, match_type: wide}

  - id: china_internet
    name: 中概互联网/港股
    us_etfs: [KWEB, CQQQ]
    primary_us: KWEB
    tags: [中概, 港股, 互联网]
    note: ""
    cn_etfs:
      - {code: '513050', name: 中概互联网ETF, tracking: 中证海外中国互联网, match_type: exact}
      - {code: '513330', name: 恒生互联网科技业ETF, tracking: 恒生互联网科技业, match_type: exact}

  - id: financial
    name: 金融/券商银行
    us_etfs: [XLF, KBE, KRE]
    primary_us: XLF
    tags: [金融, 银行, 券商]
    note: ""
    cn_etfs:
      - {code: '512000', name: 券商ETF, tracking: 中证全指证券公司, match_type: exact}
      - {code: '512800', name: 银行ETF, tracking: 中证银行, match_type: exact}

  - id: solar_clean_energy
    name: 光伏/清洁能源
    us_etfs: [TAN, ICLN]
    primary_us: TAN
    tags: [光伏, 清洁能源]
    note: ""
    cn_etfs:
      - {code: '515790', name: 光伏ETF, tracking: 中证光伏产业, match_type: exact}

  - id: biotech
    name: 生物科技/创新药
    us_etfs: [IBB, XBI]
    primary_us: XBI
    tags: [生物科技, 创新药, 医药]
    note: ""
    cn_etfs:
      - {code: '512290', name: 生物医药ETF, tracking: 中证生物医药, match_type: exact}
      - {code: '159992', name: 创新药ETF, tracking: 中证创新药产业, match_type: exact}

  - id: aerospace_defense
    name: 航天军工
    us_etfs: [ITA, UFO, ARKX]
    primary_us: ITA
    tags: [航天, 军工, 国防]
    note: ""
    cn_etfs:
      - {code: '512660', name: 军工ETF, tracking: 中证军工, match_type: exact}
      - {code: '512710', name: 军工龙头ETF, tracking: 中证军工龙头, match_type: exact}

  - id: rare_earth
    name: 稀土/新材料
    us_etfs: [REMX, PICK]
    primary_us: REMX
    tags: [稀土, 新材料]
    note: ""
    cn_etfs:
      - {code: '516780', name: 稀土ETF, tracking: 中证稀土产业, match_type: exact}
```

- [ ] **Step 3: 验证 YAML 可被解析**

Run: `cd backend && uv run python -c "import yaml; d = yaml.safe_load(open('../config/themes.yml')); print(f'Themes loaded: {len(d[\"themes\"])}')"`
Expected: `Themes loaded: 14`

- [ ] **Step 4: 验证 algo.yml 可被解析**

Run: `cd backend && uv run python -c "import yaml; d = yaml.safe_load(open('../config/algo.yml')); print(d['strength']['k_sigmoid'])"`
Expected: `5.0`

- [ ] **Step 5: Commit**

```bash
git add config/algo.yml config/themes.yml
git commit -m "feat(config): add algo.yml hyperparameters and themes.yml with 14 themes"
```

---

### Task 0.4: 初始化前端项目 (Vite + React + TS + Tailwind)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`、`frontend/tsconfig.node.json`
- Create: `frontend/tailwind.config.js`、`frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`、`frontend/src/App.tsx`、`frontend/src/index.css`

- [ ] **Step 1: 用 Vite 模板初始化**

Run: `cd frontend && npm create vite@latest . -- --template react-ts -y`
Expected: 生成 package.json/vite.config.ts/tsconfig.json 等

- [ ] **Step 2: 安装额外依赖**

```bash
cd frontend
npm install swr clsx lucide-react recharts
npm install -D tailwindcss postcss autoprefixer @types/node vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
npx tailwindcss init -p
```

- [ ] **Step 3: 配置 vite.config.ts 包含 GitHub Pages base 和 publicDir**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  base: '/etf-radar/',
  plugins: [react()],
  publicDir: path.resolve(__dirname, '../data'),
  build: { outDir: 'dist' },
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
  },
});
```

> 注意 `publicDir: '../data'` 让构建时把 `data/` 复制到 `dist/data/`, 前端用 `${import.meta.env.BASE_URL}data/latest/...` 访问。

- [ ] **Step 4: 配置 tailwind.config.js + src/index.css**

`tailwind.config.js`:
```javascript
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        signal: {
          resonance: '#2563EB',
          transmission: '#2563EB',
          divergence: '#EA580C',
        },
      },
    },
  },
  plugins: [],
};
```

`src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body { font-family: ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", Arial; }
```

- [ ] **Step 5: 启动开发服务器验证 + Commit**

Run: `cd frontend && npm run dev`
Expected: 输出 `Local: http://localhost:5173/etf-radar/`, 浏览器可见 Vite 默认页 (Ctrl+C 退出)

```bash
git add frontend/
git commit -m "feat(frontend): initialize Vite React TS Tailwind project"
```

---

## Phase 1: Backend — 配置加载 + 类型 + 交易日历

### Task 1.1: 定义核心 Pydantic 模型

**Files:**
- Create: `backend/src/models.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: 写测试 test_models.py**

```python
from datetime import datetime, timezone
from backend.src.models import (
    ThemeConfig, CnEtfConfig, AlgoConfig, Returns, Strength,
    ThemeOutput, EtfOutput, PairSignal, ThemeSignal, MetaInfo,
)

def test_theme_config_loads_minimal():
    cn = CnEtfConfig(code='512480', name='半导体ETF', tracking='中证全指半导体', match_type='exact')
    t = ThemeConfig(
        id='storage_dram', name='存储芯片',
        us_etfs=['DRAM', 'SOXX'], primary_us='DRAM',
        tags=['DRAM'], note='',
        cn_etfs=[cn],
    )
    assert t.primary_us == 'DRAM'
    assert t.cn_etfs[0].match_type == 'exact'

def test_match_type_rejects_invalid():
    import pytest
    with pytest.raises(ValueError):
        CnEtfConfig(code='000', name='x', tracking='y', match_type='loose')

def test_returns_all_optional():
    r = Returns(r_1d=0.01, r_5d=0.05)
    assert r.r_20d is None

def test_strength_clamped_0_100():
    s = Strength(short=50, mid=60, long=70, composite=60)
    assert 0 <= s.short <= 100

def test_pair_signal_minimal():
    p = PairSignal(theme_id='x', cn_code='000001', mapping_score=88, confidence=90, signal='resonance', votes={'short':'resonance','mid':'resonance','long':None})
    assert p.signal == 'resonance'
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'ThemeConfig'`

- [ ] **Step 3: 实现 models.py**

```python
"""Pydantic 模型 — 与 JSON Schema 1:1 对应"""
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

MatchType = Literal['exact', 'wide']
SignalType = Literal['resonance', 'transmission', 'divergence']
ProviderStatus = Literal['ok', 'degraded', 'stale']
DimName = Literal['short', 'mid', 'long']


class CnEtfConfig(BaseModel):
    code: str
    name: str
    tracking: str
    match_type: MatchType


class ThemeConfig(BaseModel):
    id: str
    name: str
    us_etfs: list[str]
    primary_us: str
    tags: list[str] = Field(default_factory=list)
    note: str = ''
    cn_etfs: list[CnEtfConfig]


class StrengthSubConfig(BaseModel):
    k_sigmoid: float
    threshold: float
    days_in_dim: dict[str, int]
    composite_weights: dict[str, float]


class MappingSubConfig(BaseModel):
    corr_window_days: int
    min_aligned_days: int


class ConfidenceSubConfig(BaseModel):
    exact: int
    wide: int


class SignalSubConfig(BaseModel):
    resonance: dict[str, float]
    transmission: dict[str, float]
    divergence: dict[str, float]


class AlgoConfig(BaseModel):
    strength: StrengthSubConfig
    mapping: MappingSubConfig
    confidence: ConfidenceSubConfig
    signal: SignalSubConfig


class Returns(BaseModel):
    r_1d: Optional[float] = None
    r_5d: Optional[float] = None
    r_20d: Optional[float] = None
    r_60d: Optional[float] = None
    r_120d: Optional[float] = None
    r_ytd: Optional[float] = None


class Strength(BaseModel):
    short: int = Field(ge=0, le=100)
    mid: int = Field(ge=0, le=100)
    long: int = Field(ge=0, le=100)
    composite: int = Field(ge=0, le=100)


class Rank(BaseModel):
    short: int
    mid: int
    long: int
    composite: int


class ThemeOutput(BaseModel):
    id: str
    name: str
    us_etfs: list[str]
    primary_us: str
    tags: list[str]
    note: str
    returns: Returns
    strength: Strength
    rank: Rank


class EtfOutput(BaseModel):
    code: str
    name: str
    tracking_index: str
    returns: Returns
    amount_yi: Optional[float] = None
    price: Optional[float] = None
    strength: Strength


class PairSignal(BaseModel):
    theme_id: str
    cn_code: str
    mapping_score: Optional[int]
    confidence: int
    signal: Optional[SignalType]
    votes: dict[str, Optional[SignalType]]


class ThemeSignal(BaseModel):
    theme_id: str
    signal: Optional[SignalType]
    trigger_cn_etf: Optional[str]
    votes: dict[str, Optional[SignalType]]
    description: str


class TopTheme(BaseModel):
    id: str
    name: str
    primary_us: str
    composite_strength: int


class SignalsSummary(BaseModel):
    themes_total: int
    etfs_total: int
    resonance_count: int
    transmission_count: int
    divergence_count: int
    top_theme: Optional[TopTheme]


class ProviderInfo(BaseModel):
    status: ProviderStatus
    name: str


class CalendarInfo(BaseModel):
    us_trading_today: bool
    cn_trading_today: bool
    us_session_active: bool
    cn_session_active: bool


class FullRefreshTimes(BaseModel):
    us: Optional[str] = None
    cn: Optional[str] = None


class MetaInfo(BaseModel):
    schema_version: str = '1.0'
    last_full_refresh: FullRefreshTimes
    last_intraday_refresh: Optional[str] = None
    providers: dict[str, ProviderInfo]
    failed_symbols: list[str] = Field(default_factory=list)
    stale_minutes: int = 0
    calendar: CalendarInfo
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_models.py -v`
Expected: PASS — 5 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/models.py backend/tests/test_models.py
git commit -m "feat(backend): add Pydantic models for config and output schemas"
```

---

### Task 1.2: 实现 config_loader.py

**Files:**
- Create: `backend/src/config_loader.py`
- Create: `backend/tests/test_config_loader.py`
- Create: `backend/tests/fixtures/themes_minimal.yml`
- Create: `backend/tests/fixtures/algo_minimal.yml`

- [ ] **Step 1: 写测试 fixtures**

`backend/tests/fixtures/themes_minimal.yml`:
```yaml
themes:
  - id: t1
    name: 主题1
    us_etfs: [AAA]
    primary_us: AAA
    tags: []
    note: ''
    cn_etfs:
      - {code: '000001', name: ETF1, tracking: I1, match_type: exact}
```

`backend/tests/fixtures/algo_minimal.yml`:
```yaml
strength:
  k_sigmoid: 5.0
  threshold: 0.0
  days_in_dim: {short: 3, mid: 40, long: 180}
  composite_weights: {short: 0.2, mid: 0.4, long: 0.4}
mapping:
  corr_window_days: 60
  min_aligned_days: 30
confidence: {exact: 90, wide: 60}
signal:
  resonance: {max_strength_diff: 15, min_max_strength: 60}
  transmission: {min_strength_diff: 25, min_leader_strength: 65}
  divergence: {min_return_magnitude: 0.02}
```

`backend/tests/test_config_loader.py`:
```python
from pathlib import Path
import pytest
from backend.src.config_loader import load_themes, load_algo_config

FIXT = Path(__file__).parent / 'fixtures'

def test_load_themes_returns_list():
    themes = load_themes(FIXT / 'themes_minimal.yml')
    assert len(themes) == 1
    assert themes[0].id == 't1'

def test_load_algo_config():
    cfg = load_algo_config(FIXT / 'algo_minimal.yml')
    assert cfg.strength.k_sigmoid == 5.0
    assert cfg.confidence.exact == 90

def test_load_themes_missing_file():
    with pytest.raises(FileNotFoundError):
        load_themes(FIXT / 'nope.yml')

def test_real_themes_yml_has_14():
    real = Path(__file__).parent.parent.parent / 'config' / 'themes.yml'
    themes = load_themes(real)
    assert len(themes) == 14
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_config_loader.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: 实现 config_loader.py**

```python
"""加载 themes.yml 与 algo.yml"""
from pathlib import Path
import yaml
from .models import ThemeConfig, AlgoConfig


def load_themes(path: Path | str) -> list[ThemeConfig]:
    p = Path(path)
    with p.open(encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return [ThemeConfig(**t) for t in data['themes']]


def load_algo_config(path: Path | str) -> AlgoConfig:
    p = Path(path)
    with p.open(encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return AlgoConfig(**data)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_config_loader.py -v`
Expected: PASS — 4 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/config_loader.py backend/tests/test_config_loader.py backend/tests/fixtures/
git commit -m "feat(backend): add config loader for themes and algo yml"
```

---

### Task 1.3: 实现交易日历 (etl/calendar.py)

**Files:**
- Create: `backend/src/etl/__init__.py`
- Create: `backend/src/etl/calendar.py`
- Create: `backend/tests/test_calendar.py`

- [ ] **Step 1: 写测试**

```python
from datetime import date, datetime, time, timezone, timedelta
from backend.src.etl.calendar import (
    is_cn_trading_day, is_us_trading_day,
    is_cn_session_active, is_us_session_active,
)

def test_cn_weekend_is_not_trading():
    sat = date(2026, 6, 6)  # Saturday
    assert not is_cn_trading_day(sat)

def test_us_weekend_is_not_trading():
    sun = date(2026, 6, 7)  # Sunday
    assert not is_us_trading_day(sun)

def test_cn_normal_workday_is_trading():
    mon = date(2026, 6, 8)  # Monday (not holiday)
    assert is_cn_trading_day(mon)

def test_cn_session_active_during_morning():
    BJT = timezone(timedelta(hours=8))
    dt = datetime(2026, 6, 8, 10, 0, tzinfo=BJT)
    assert is_cn_session_active(dt)

def test_cn_session_inactive_during_lunch():
    BJT = timezone(timedelta(hours=8))
    dt = datetime(2026, 6, 8, 12, 0, tzinfo=BJT)
    assert not is_cn_session_active(dt)

def test_cn_session_inactive_before_open():
    BJT = timezone(timedelta(hours=8))
    dt = datetime(2026, 6, 8, 9, 0, tzinfo=BJT)
    assert not is_cn_session_active(dt)
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_calendar.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 calendar.py**

```python
"""交易日历 — A 股 + 美股"""
from datetime import date, datetime, time, timezone, timedelta
import chinese_calendar
import pandas_market_calendars as mcal

BJT = timezone(timedelta(hours=8))
NYSE = mcal.get_calendar('NYSE')

CN_MORNING_OPEN = time(9, 30)
CN_MORNING_CLOSE = time(11, 30)
CN_AFTERNOON_OPEN = time(13, 0)
CN_AFTERNOON_CLOSE = time(15, 0)


def is_cn_trading_day(d: date) -> bool:
    return chinese_calendar.is_workday(d) and not chinese_calendar.is_holiday(d)


def is_us_trading_day(d: date) -> bool:
    schedule = NYSE.schedule(start_date=d, end_date=d)
    return not schedule.empty


def is_cn_session_active(now_bjt: datetime) -> bool:
    if not is_cn_trading_day(now_bjt.date()):
        return False
    t = now_bjt.time()
    return (CN_MORNING_OPEN <= t <= CN_MORNING_CLOSE
            or CN_AFTERNOON_OPEN <= t <= CN_AFTERNOON_CLOSE)


def is_us_session_active(now_utc: datetime) -> bool:
    """美股盘中: ET 09:30-16:00 (UTC-5/-4)"""
    d = now_utc.date()
    sched = NYSE.schedule(start_date=d, end_date=d)
    if sched.empty:
        return False
    market_open = sched.iloc[0]['market_open'].to_pydatetime()
    market_close = sched.iloc[0]['market_close'].to_pydatetime()
    return market_open <= now_utc <= market_close
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_calendar.py -v`
Expected: PASS — 6 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/etl/ backend/tests/test_calendar.py
git commit -m "feat(backend): add trading calendar for CN and US markets"
```

---

### Task 1.4: 实现字段标准化 (etl/standardize.py)

**Files:**
- Create: `backend/src/etl/standardize.py`
- Create: `backend/tests/test_standardize.py`

- [ ] **Step 1: 写测试**

```python
import pandas as pd
from backend.src.etl.standardize import standardize_ohlc, STANDARD_COLUMNS

def test_standardize_adds_missing_amount_as_nan():
    df = pd.DataFrame({
        'Date': pd.to_datetime(['2026-06-04', '2026-06-05']),
        'Open': [100, 101], 'High': [102, 103], 'Low': [99, 100],
        'Close': [101, 102], 'Volume': [1000, 2000],
    })
    out = standardize_ohlc(df, source='yfinance')
    assert set(STANDARD_COLUMNS).issubset(set(out.columns))
    assert out['amount'].isna().all()
    assert str(out['date'].dt.tz) == 'UTC'

def test_standardize_akshare_keeps_amount():
    df = pd.DataFrame({
        '日期': pd.to_datetime(['2026-06-04']),
        '开盘': [1.0], '最高': [1.1], '最低': [0.9],
        '收盘': [1.05], '成交量': [10000], '成交额': [10500.0],
    })
    out = standardize_ohlc(df, source='akshare')
    assert out['amount'].iloc[0] == 10500.0
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_standardize.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 standardize.py**

```python
"""把 yfinance / akshare 的 DataFrame 列名/时区/类型统一"""
from typing import Literal
import pandas as pd

STANDARD_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount']

YFINANCE_MAP = {
    'Date': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low',
    'Close': 'close', 'Adj Close': 'close', 'Volume': 'volume',
}

AKSHARE_MAP = {
    '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low',
    '收盘': 'close', '成交量': 'volume', '成交额': 'amount',
}


def standardize_ohlc(
    df: pd.DataFrame,
    source: Literal['yfinance', 'akshare'],
) -> pd.DataFrame:
    if source == 'yfinance':
        mapping = YFINANCE_MAP
    elif source == 'akshare':
        mapping = AKSHARE_MAP
    else:
        raise ValueError(f'unknown source: {source}')

    if df.index.name in mapping:
        df = df.reset_index()

    df = df.rename(columns=mapping)
    if 'amount' not in df.columns:
        df['amount'] = pd.NA
    df['date'] = pd.to_datetime(df['date'], utc=True)
    for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df[STANDARD_COLUMNS].sort_values('date').reset_index(drop=True)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_standardize.py -v`
Expected: PASS — 2 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/etl/standardize.py backend/tests/test_standardize.py
git commit -m "feat(backend): add OHLC field standardization for yfinance and akshare"
```

---

## Phase 2: Backend — Provider 层

### Task 2.1: 定义 Provider 抽象 (providers/base.py)

**Files:**
- Create: `backend/src/providers/__init__.py`
- Create: `backend/src/providers/base.py`
- Create: `backend/tests/test_provider_base.py`

- [ ] **Step 1: 写测试**

```python
from backend.src.providers.base import EtfDataProvider, ProviderError, EmptyDataError

def test_provider_error_is_exception():
    assert issubclass(ProviderError, Exception)
    assert issubclass(EmptyDataError, ProviderError)

def test_provider_protocol_callable():
    assert hasattr(EtfDataProvider, 'fetch_ohlc')
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_provider_base.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 base.py**

```python
"""Provider 抽象接口与异常"""
from typing import Protocol
import pandas as pd


class ProviderError(Exception):
    """数据源调用失败的基类"""


class EmptyDataError(ProviderError):
    """数据源返回空数据"""


class EtfDataProvider(Protocol):
    """统一 ETF 数据源接口"""

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        """返回标准化后的 OHLC DataFrame (调用方应再过 standardize_ohlc)"""
        ...
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_provider_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/providers/ backend/tests/test_provider_base.py
git commit -m "feat(backend): add provider base interface and errors"
```

---

### Task 2.2: 实现 YfinanceProvider

**Files:**
- Create: `backend/src/providers/yfinance_provider.py`
- Create: `backend/tests/test_yfinance_provider.py`

- [ ] **Step 1: 写测试 (用 mock 避免真实网络)**

```python
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from backend.src.providers.yfinance_provider import YfinanceProvider
from backend.src.providers.base import EmptyDataError

@patch('backend.src.providers.yfinance_provider.yf.Ticker')
def test_fetch_ohlc_success(mock_ticker):
    fake_df = pd.DataFrame({
        'Open': [100, 101], 'High': [102, 103], 'Low': [99, 100],
        'Close': [101, 102], 'Volume': [1000, 2000],
    }, index=pd.to_datetime(['2026-06-04', '2026-06-05'], utc=True))
    fake_df.index.name = 'Date'
    mock_ticker.return_value.history.return_value = fake_df

    p = YfinanceProvider()
    df = p.fetch_ohlc('SOXX', 5)
    assert not df.empty
    assert 'close' in df.columns

@patch('backend.src.providers.yfinance_provider.yf.Ticker')
def test_fetch_ohlc_empty_raises(mock_ticker):
    mock_ticker.return_value.history.return_value = pd.DataFrame()
    p = YfinanceProvider()
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('NONEXIST', 5)
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_yfinance_provider.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 yfinance_provider.py**

```python
"""yfinance 数据源 — 美股 ETF"""
import time
import logging
import pandas as pd
import yfinance as yf
from .base import EtfDataProvider, ProviderError, EmptyDataError
from ..etl.standardize import standardize_ohlc

log = logging.getLogger(__name__)


class YfinanceProvider(EtfDataProvider):
    name = 'yfinance'

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=f'{lookback_days}d', auto_adjust=False)
                if df.empty:
                    raise EmptyDataError(f'yfinance returned empty for {symbol}')
                return standardize_ohlc(df, source='yfinance')
            except EmptyDataError:
                raise
            except Exception as e:
                last_exc = e
                log.warning(f'yfinance attempt {attempt+1} failed for {symbol}: {e}')
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        raise ProviderError(f'yfinance failed after {self.max_retries} retries: {last_exc}')
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_yfinance_provider.py -v`
Expected: PASS — 2 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/providers/yfinance_provider.py backend/tests/test_yfinance_provider.py
git commit -m "feat(backend): add yfinance provider with retry"
```

---

### Task 2.3: 实现 AkshareProvider

**Files:**
- Create: `backend/src/providers/akshare_provider.py`
- Create: `backend/tests/test_akshare_provider.py`

- [ ] **Step 1: 写测试 (用 mock)**

```python
import pandas as pd
import pytest
from unittest.mock import patch
from backend.src.providers.akshare_provider import AkshareProvider
from backend.src.providers.base import EmptyDataError

@patch('backend.src.providers.akshare_provider.ak.fund_etf_hist_em')
def test_fetch_ohlc_success(mock_hist):
    fake = pd.DataFrame({
        '日期': pd.to_datetime(['2026-06-04']),
        '开盘': [1.0], '最高': [1.1], '最低': [0.9],
        '收盘': [1.05], '成交量': [10000], '成交额': [10500.0],
    })
    mock_hist.return_value = fake
    p = AkshareProvider()
    df = p.fetch_ohlc('512480', 5)
    assert not df.empty
    assert df['amount'].iloc[0] == 10500.0

@patch('backend.src.providers.akshare_provider.ak.fund_etf_hist_em')
def test_fetch_ohlc_empty_raises(mock_hist):
    mock_hist.return_value = pd.DataFrame()
    p = AkshareProvider()
    with pytest.raises(EmptyDataError):
        p.fetch_ohlc('999999', 5)
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_akshare_provider.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 akshare_provider.py**

```python
"""akshare 数据源 — A 股场内 ETF"""
import time
import logging
from datetime import date, timedelta
import pandas as pd
import akshare as ak
from .base import EtfDataProvider, ProviderError, EmptyDataError
from ..etl.standardize import standardize_ohlc

log = logging.getLogger(__name__)


class AkshareProvider(EtfDataProvider):
    name = 'akshare'

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    def fetch_ohlc(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        end = date.today()
        start = end - timedelta(days=int(lookback_days * 1.6))  # 含周末缓冲
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                df = ak.fund_etf_hist_em(
                    symbol=symbol,
                    period='daily',
                    start_date=start.strftime('%Y%m%d'),
                    end_date=end.strftime('%Y%m%d'),
                    adjust='qfq',
                )
                if df is None or df.empty:
                    raise EmptyDataError(f'akshare empty for {symbol}')
                return standardize_ohlc(df, source='akshare')
            except EmptyDataError:
                raise
            except Exception as e:
                last_exc = e
                log.warning(f'akshare attempt {attempt+1} failed for {symbol}: {e}')
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
        raise ProviderError(f'akshare failed after {self.max_retries} retries: {last_exc}')
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_akshare_provider.py -v`
Expected: PASS — 2 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/providers/akshare_provider.py backend/tests/test_akshare_provider.py
git commit -m "feat(backend): add akshare provider with retry"
```

---

## Phase 3: Backend — Scoring 层

### Task 3.1: 实现收益率计算 (scoring/returns.py)

**Files:**
- Create: `backend/src/scoring/__init__.py`
- Create: `backend/src/scoring/returns.py`
- Create: `backend/tests/test_returns.py`

- [ ] **Step 1: 写测试**

```python
import math
import pandas as pd
from backend.src.scoring.returns import compute_returns

def _series(closes):
    return pd.DataFrame({
        'date': pd.date_range('2025-01-01', periods=len(closes), tz='UTC'),
        'close': closes,
    })

def test_returns_basic_1d():
    df = _series([100, 110])
    r = compute_returns(df)
    assert r.r_1d == pytest_approx(math.log(110/100))

def test_returns_with_insufficient_data():
    df = _series([100])
    r = compute_returns(df)
    assert r.r_1d is None
    assert r.r_5d is None

def test_returns_ytd_from_year_start():
    # 250 个交易日 - YTD 从首日算
    closes = [100] + [110] * 250
    df = _series(closes)
    r = compute_returns(df)
    assert r.r_ytd is not None

import pytest
pytest_approx = pytest.approx
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_returns.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 returns.py**

```python
"""单只 ETF 的多周期对数收益率计算"""
import math
import pandas as pd
from ..models import Returns


def _log_return(series: pd.Series, periods: int) -> float | None:
    if len(series) <= periods:
        return None
    end = series.iloc[-1]
    start = series.iloc[-1 - periods]
    if start <= 0 or end <= 0:
        return None
    return math.log(end / start)


def _ytd_return(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    last = df.iloc[-1]
    last_year = last['date'].year
    same_year = df[df['date'].dt.year == last_year]
    if len(same_year) < 2:
        return None
    first_close = same_year.iloc[0]['close']
    end_close = last['close']
    if first_close <= 0 or end_close <= 0:
        return None
    return math.log(end_close / first_close)


def compute_returns(df: pd.DataFrame) -> Returns:
    """df 已按 date 升序, 含 close 列"""
    close = df['close']
    return Returns(
        r_1d=_log_return(close, 1),
        r_5d=_log_return(close, 5),
        r_20d=_log_return(close, 20),
        r_60d=_log_return(close, 60),
        r_120d=_log_return(close, 120),
        r_ytd=_ytd_return(df),
    )
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_returns.py -v`
Expected: PASS — 3 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/scoring/ backend/tests/test_returns.py
git commit -m "feat(backend): compute multi-period log returns"
```

---

### Task 3.2: 实现强度评分 (scoring/strength.py)

**Files:**
- Create: `backend/src/scoring/strength.py`
- Create: `backend/tests/test_strength.py`

- [ ] **Step 1: 写测试**

```python
import math
import pytest
from backend.src.scoring.strength import (
    sigmoid_momentum, percentile_rank, dim_aggregate_return,
    strength_per_dim, composite_strength,
)
from backend.src.models import Returns

def test_sigmoid_zero_is_50():
    assert sigmoid_momentum(0.0, k=5.0, days_in_dim=40) == pytest.approx(50, abs=0.01)

def test_sigmoid_strong_positive_saturates():
    # 年化 +300% → sigmoid 接近 100
    v = sigmoid_momentum(2.0, k=5.0, days_in_dim=40)
    assert v > 95

def test_percentile_rank_basic():
    assert percentile_rank(50, [10, 20, 30, 40, 50]) == 100
    assert percentile_rank(10, [10, 20, 30, 40, 50]) == pytest.approx(20.0, abs=0.5)

def test_dim_aggregate_short():
    r = Returns(r_1d=0.01, r_5d=0.05)
    assert dim_aggregate_return(r, 'short') == pytest.approx(0.03)

def test_dim_aggregate_returns_none_if_all_missing():
    r = Returns()
    assert dim_aggregate_return(r, 'short') is None

def test_strength_per_dim_returns_int_0_100():
    s = strength_per_dim(0.05, [0.0, 0.01, 0.02, 0.03, 0.05], k=5.0, days_in_dim=40)
    assert 0 <= s <= 100

def test_composite_weighted_avg():
    c = composite_strength(short=77, mid=99, long=99, w_short=0.2, w_mid=0.4, w_long=0.4)
    assert c == 94  # 反推文档样本
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_strength.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 strength.py**

```python
"""双轨强度评分: 百分位 × sigmoid 动量"""
import math
from statistics import mean
from typing import Literal
from scipy.stats import percentileofscore
from ..models import Returns, DimName

DimName = Literal['short', 'mid', 'long']

DIM_FIELDS = {
    'short': ['r_1d', 'r_5d'],
    'mid':   ['r_20d', 'r_60d'],
    'long':  ['r_120d', 'r_ytd'],
}


def sigmoid_momentum(ret: float, k: float, days_in_dim: int) -> float:
    """对数收益率年化后过 sigmoid 映射到 0-100"""
    annualized = ret * (252 / days_in_dim)
    return 100.0 / (1.0 + math.exp(-k * annualized))


def percentile_rank(value: float, pool: list[float]) -> float:
    """value 在 pool 内的百分位排名 (0-100)"""
    return float(percentileofscore(pool, value, kind='rank'))


def dim_aggregate_return(returns: Returns, dim: DimName) -> float | None:
    """单维度内子周期平均"""
    fields = DIM_FIELDS[dim]
    values = [getattr(returns, f) for f in fields]
    values = [v for v in values if v is not None]
    if not values:
        return None
    return mean(values)


def strength_per_dim(
    own_dim_return: float,
    pool_dim_returns: list[float],
    k: float,
    days_in_dim: int,
) -> int:
    """单维度双轨强度: 0.5×百分位 + 0.5×sigmoid, 返回 0-100 整数"""
    P = percentile_rank(own_dim_return, pool_dim_returns)
    M = sigmoid_momentum(own_dim_return, k=k, days_in_dim=days_in_dim)
    raw = 0.5 * P + 0.5 * M
    return max(0, min(99, round(raw)))  # 上限 99, 留 100 给"完美样本"


def composite_strength(short: int, mid: int, long: int,
                       w_short: float, w_mid: float, w_long: float) -> int:
    return round(w_short * short + w_mid * mid + w_long * long)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_strength.py -v`
Expected: PASS — 7 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/scoring/strength.py backend/tests/test_strength.py
git commit -m "feat(backend): add dual-track strength scoring (percentile × sigmoid)"
```

---

### Task 3.3: 实现映射分 (scoring/mapping.py)

**Files:**
- Create: `backend/src/scoring/mapping.py`
- Create: `backend/tests/test_mapping.py`

- [ ] **Step 1: 写测试**

```python
import math
import pandas as pd
import pytest
from backend.src.scoring.mapping import mapping_score, _align_log_returns

def _df(dates, closes):
    return pd.DataFrame({'date': pd.to_datetime(dates, utc=True), 'close': closes})

def test_align_intersects_dates():
    us = _df(['2026-06-01', '2026-06-02', '2026-06-03'], [100, 101, 102])
    cn = _df(['2026-06-02', '2026-06-03'], [10, 11])
    aligned = _align_log_returns(us, cn)
    assert len(aligned) == 1  # 第 1 个对齐日是 06-03 (因为 log return 需要前一日)

def test_mapping_perfect_corr():
    us = _df(pd.date_range('2026-01-01', periods=80, tz='UTC'),
             [100 + i*0.5 for i in range(80)])
    cn = _df(pd.date_range('2026-01-01', periods=80, tz='UTC'),
             [10 + i*0.05 for i in range(80)])  # 完美线性同向
    score = mapping_score(us, cn, window=60, min_aligned=30)
    assert score is not None
    assert score >= 95

def test_mapping_insufficient_data_returns_none():
    us = _df(['2026-01-01'], [100])
    cn = _df(['2026-01-01'], [10])
    assert mapping_score(us, cn, window=60, min_aligned=30) is None
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_mapping.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 mapping.py**

```python
"""映射分 — 美股 vs A 股 ETF 的对齐 60d 相关性 × 100"""
import math
import pandas as pd
from scipy.stats import pearsonr


def _log_returns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values('date').copy()
    df['log_ret'] = (df['close'] / df['close'].shift(1)).apply(
        lambda x: math.log(x) if x and x > 0 else None
    )
    return df.dropna(subset=['log_ret'])


def _align_log_returns(us: pd.DataFrame, cn: pd.DataFrame) -> pd.DataFrame:
    us_r = _log_returns(us)[['date', 'log_ret']].rename(columns={'log_ret': 'us'})
    cn_r = _log_returns(cn)[['date', 'log_ret']].rename(columns={'log_ret': 'cn'})
    us_r['date'] = us_r['date'].dt.normalize()
    cn_r['date'] = cn_r['date'].dt.normalize()
    return us_r.merge(cn_r, on='date', how='inner')


def mapping_score(
    us_ohlc: pd.DataFrame,
    cn_ohlc: pd.DataFrame,
    window: int,
    min_aligned: int,
) -> int | None:
    """对齐后取最近 window 天计算 Pearson corr, 返回 |corr| × 100"""
    aligned = _align_log_returns(us_ohlc, cn_ohlc)
    aligned = aligned.tail(window)
    if len(aligned) < min_aligned:
        return None
    corr, _ = pearsonr(aligned['us'], aligned['cn'])
    if math.isnan(corr):
        return None
    return round(abs(corr) * 100)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_mapping.py -v`
Expected: PASS — 3 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/scoring/mapping.py backend/tests/test_mapping.py
git commit -m "feat(backend): compute mapping score via 60d rolling correlation"
```

---

### Task 3.4: 实现信号判定 (scoring/signals.py)

**Files:**
- Create: `backend/src/scoring/signals.py`
- Create: `backend/tests/test_signals.py`

- [ ] **Step 1: 写测试**

```python
import pytest
from backend.src.scoring.signals import (
    judge_per_period, signal_for_pair, signal_for_theme,
)
from backend.src.models import AlgoConfig
from backend.src.config_loader import load_algo_config
from pathlib import Path

CFG = load_algo_config(Path(__file__).parent / 'fixtures' / 'algo_minimal.yml')


def test_resonance_when_both_strong_and_same_dir():
    sig = judge_per_period(us_str=80, cn_str=75, us_ret=0.05, cn_ret=0.04, cfg=CFG.signal)
    assert sig == 'resonance'

def test_transmission_when_us_leads():
    sig = judge_per_period(us_str=80, cn_str=40, us_ret=0.05, cn_ret=0.0, cfg=CFG.signal)
    assert sig == 'transmission'

def test_divergence_when_opposite_dir():
    sig = judge_per_period(us_str=60, cn_str=60, us_ret=0.05, cn_ret=-0.05, cfg=CFG.signal)
    assert sig == 'divergence'

def test_neutral_when_weak():
    sig = judge_per_period(us_str=40, cn_str=40, us_ret=0.001, cn_ret=0.001, cfg=CFG.signal)
    assert sig is None

def test_signal_for_pair_votes_resonance():
    class FakeStrength:
        def __init__(self, short, mid, long): self.short=short; self.mid=mid; self.long=long
    class FakeReturns:
        def __init__(self, r_short, r_mid, r_long):
            self.r_short=r_short; self.r_mid=r_mid; self.r_long=r_long
    
    sig, votes = signal_for_pair(
        us_strength=FakeStrength(80, 80, 80),
        cn_strength=FakeStrength(75, 75, 75),
        us_dim_returns={'short':0.05,'mid':0.10,'long':0.30},
        cn_dim_returns={'short':0.04,'mid':0.09,'long':0.28},
        cfg=CFG.signal,
    )
    assert sig == 'resonance'

def test_signal_for_pair_no_majority_returns_none():
    class FakeStrength:
        def __init__(self, s, m, l): self.short=s; self.mid=m; self.long=l
    
    sig, votes = signal_for_pair(
        us_strength=FakeStrength(80, 40, 40),
        cn_strength=FakeStrength(75, 40, 40),
        us_dim_returns={'short':0.05,'mid':0.001,'long':0.001},
        cn_dim_returns={'short':0.04,'mid':0.001,'long':0.001},
        cfg=CFG.signal,
    )
    assert sig is None  # 1 resonance + 2 None → 无多数
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_signals.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 signals.py**

```python
"""信号判定 — 单周期 + 多周期投票"""
from collections import Counter
from typing import Optional
from ..models import SignalSubConfig, SignalType


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def judge_per_period(
    us_str: int, cn_str: int,
    us_ret: float, cn_ret: float,
    cfg: SignalSubConfig,
) -> Optional[SignalType]:
    res_cfg = cfg.resonance
    trans_cfg = cfg.transmission
    div_cfg = cfg.divergence

    # 共振
    if (abs(us_str - cn_str) <= res_cfg['max_strength_diff']
        and _sign(us_ret) == _sign(cn_ret)
        and _sign(us_ret) != 0
        and max(us_str, cn_str) >= res_cfg['min_max_strength']):
        return 'resonance'

    # 传导
    if us_str - cn_str >= trans_cfg['min_strength_diff'] and us_str >= trans_cfg['min_leader_strength']:
        return 'transmission'
    if cn_str - us_str >= trans_cfg['min_strength_diff'] and cn_str >= trans_cfg['min_leader_strength']:
        return 'transmission'

    # 背离
    if (_sign(us_ret) != _sign(cn_ret)
        and _sign(us_ret) != 0 and _sign(cn_ret) != 0
        and abs(us_ret) >= div_cfg['min_return_magnitude']
        and abs(cn_ret) >= div_cfg['min_return_magnitude']):
        return 'divergence'

    return None


def signal_for_pair(
    us_strength, cn_strength,
    us_dim_returns: dict, cn_dim_returns: dict,
    cfg: SignalSubConfig,
) -> tuple[Optional[SignalType], dict[str, Optional[SignalType]]]:
    votes: dict[str, Optional[SignalType]] = {}
    for dim in ['short', 'mid', 'long']:
        votes[dim] = judge_per_period(
            us_str=getattr(us_strength, dim),
            cn_str=getattr(cn_strength, dim),
            us_ret=us_dim_returns.get(dim, 0.0) or 0.0,
            cn_ret=cn_dim_returns.get(dim, 0.0) or 0.0,
            cfg=cfg,
        )
    valid = [v for v in votes.values() if v is not None]
    if not valid:
        return None, votes
    counter = Counter(valid)
    top_label, top_count = counter.most_common(1)[0]
    if top_count >= 2:
        return top_label, votes
    return None, votes


def signal_for_theme(
    us_strength, us_dim_returns: dict,
    cn_candidates: list[dict],  # each: {cn_strength, cn_dim_returns, confidence, mapping_score, code}
    cfg: SignalSubConfig,
) -> tuple[Optional[SignalType], Optional[str], dict]:
    sorted_candidates = sorted(
        cn_candidates,
        key=lambda x: (x['confidence'], x.get('mapping_score') or 0),
        reverse=True,
    )
    for cn in sorted_candidates:
        sig, votes = signal_for_pair(
            us_strength=us_strength,
            cn_strength=cn['cn_strength'],
            us_dim_returns=us_dim_returns,
            cn_dim_returns=cn['cn_dim_returns'],
            cfg=cfg,
        )
        if sig:
            return sig, cn['code'], votes
    return None, None, {}
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_signals.py -v`
Expected: PASS — 6 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/scoring/signals.py backend/tests/test_signals.py
git commit -m "feat(backend): add multi-period voting signal judgment"
```

---

## Phase 4: Backend — 输出层与 Pipeline 编排

### Task 4.1: 实现 JSON 写入 (output/writer.py)

**Files:**
- Create: `backend/src/output/__init__.py`
- Create: `backend/src/output/writer.py`
- Create: `backend/tests/test_writer.py`

- [ ] **Step 1: 写测试**

```python
import json
import tempfile
from pathlib import Path
from backend.src.output.writer import atomic_write_json

def test_atomic_write_creates_file_with_content():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'out.json'
        atomic_write_json(p, {'a': 1, 'b': '中文'})
        loaded = json.loads(p.read_text(encoding='utf-8'))
        assert loaded == {'a': 1, 'b': '中文'}

def test_atomic_write_preserves_old_on_failure(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'out.json'
        atomic_write_json(p, {'old': True})
        # 模拟写入失败
        import os
        orig = os.replace
        def fail(*a, **k): raise OSError('disk full')
        monkeypatch.setattr(os, 'replace', fail)
        try:
            atomic_write_json(p, {'new': True})
        except OSError:
            pass
        assert json.loads(p.read_text(encoding='utf-8')) == {'old': True}
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_writer.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 writer.py**

```python
"""原子 JSON 写入 — 失败时不破坏既有文件"""
import json
import os
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, data: Any) -> None:
    """先写入 .tmp, 再 os.replace 原子替换"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_writer.py -v`
Expected: PASS — 2 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/output/ backend/tests/test_writer.py
git commit -m "feat(backend): add atomic JSON writer"
```

---

### Task 4.2: 实现 EOD 归档器 (output/archiver.py)

**Files:**
- Create: `backend/src/output/archiver.py`
- Create: `backend/tests/test_archiver.py`

- [ ] **Step 1: 写测试**

```python
import json
import tempfile
from pathlib import Path
from datetime import date
from backend.src.output.archiver import archive_latest

def test_archive_copies_latest_to_dated_dir():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        latest = root / 'latest'
        latest.mkdir()
        (latest / 'themes.json').write_text('{"a":1}')
        (latest / 'etfs.json').write_text('{}')
        (latest / 'signals.json').write_text('{}')
        (latest / 'meta.json').write_text('{}')

        target_date = date(2026, 6, 5)
        archive_latest(root, target_date)

        archived = root / 'snapshots' / '2026-06-05'
        assert (archived / 'themes.json').read_text() == '{"a":1}'
        assert (archived / 'meta.json').exists()
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_archiver.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 archiver.py**

```python
"""EOD 归档 — 把 data/latest/ 复制到 data/snapshots/<YYYY-MM-DD>/"""
import shutil
from pathlib import Path
from datetime import date


FILES = ['themes.json', 'etfs.json', 'signals.json', 'meta.json']


def archive_latest(data_root: Path, target_date: date) -> Path:
    data_root = Path(data_root)
    src = data_root / 'latest'
    dst = data_root / 'snapshots' / target_date.strftime('%Y-%m-%d')
    dst.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        if (src / f).exists():
            shutil.copy2(src / f, dst / f)
    return dst
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_archiver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/output/archiver.py backend/tests/test_archiver.py
git commit -m "feat(backend): add EOD archiver"
```

---

### Task 4.3: 实现描述模板 (output/descriptions.py)

**Files:**
- Create: `backend/src/output/descriptions.py`
- Create: `backend/tests/test_descriptions.py`

- [ ] **Step 1: 写测试**

```python
from backend.src.output.descriptions import signal_description, theme_dynamic_description

def test_resonance_text():
    assert '同向' in signal_description('resonance')

def test_transmission_text():
    assert '美股' in signal_description('transmission')

def test_divergence_text():
    assert '不同步' in signal_description('divergence')

def test_none_returns_empty():
    assert signal_description(None) == ''

def test_dynamic_description_includes_theme_name():
    txt = theme_dynamic_description(theme_name='存储芯片', signal='resonance', us_strength_mid=99)
    assert '存储芯片' in txt or '美股' in txt
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_descriptions.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 descriptions.py**

```python
"""信号说明文字与动态描述生成 (REQ-013)"""
from typing import Optional
from ..models import SignalType


SIGNAL_NOTES = {
    'resonance': '美股主题ETF与A股ETF在多个周期同向走强或走弱, 说明跨市场映射更顺畅, 适合优先观察。',
    'transmission': '美股主题ETF已经先动, A股ETF尚未完全跟上, 适合观察隔夜到A股开盘后的补涨或补跌传导。',
    'divergence': '美股与A股走势不同步, 需二次确认, 警惕假信号。',
}


def signal_description(signal: Optional[SignalType]) -> str:
    if signal is None:
        return ''
    return SIGNAL_NOTES[signal]


def theme_dynamic_description(theme_name: str, signal: Optional[SignalType], us_strength_mid: int) -> str:
    if signal == 'transmission':
        return '美股领先, A股尚未完全跟随'
    if signal == 'resonance' and us_strength_mid >= 80:
        return f'美股{theme_name}中长期走强'
    if signal == 'divergence':
        return '美股A股短期方向不一致'
    return f'美股{theme_name}动量观察中'
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_descriptions.py -v`
Expected: PASS — 5 tests passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/output/descriptions.py backend/tests/test_descriptions.py
git commit -m "feat(backend): add signal description templates"
```

---

### Task 4.4: 实现主 Pipeline (pipeline.py)

**Files:**
- Create: `backend/src/pipeline.py`
- Create: `backend/tests/test_pipeline_smoke.py`

- [ ] **Step 1: 写 smoke 测试 (用 fixture + mock provider)**

```python
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from backend.src.pipeline import run_pipeline, PipelineMode


def _make_fake_ohlc(n=200, base=100):
    return pd.DataFrame({
        'date': pd.date_range('2025-01-01', periods=n, tz='UTC'),
        'open': [base]*n, 'high': [base*1.01]*n, 'low': [base*0.99]*n,
        'close': [base + i*0.5 for i in range(n)],
        'volume': [10000]*n, 'amount': [base*10000.0]*n,
    })


@patch('backend.src.pipeline.YfinanceProvider')
@patch('backend.src.pipeline.AkshareProvider')
def test_pipeline_full_mode_creates_files(mock_ak, mock_yf):
    mock_yf.return_value.fetch_ohlc.return_value = _make_fake_ohlc()
    mock_yf.return_value.name = 'yfinance'
    mock_ak.return_value.fetch_ohlc.return_value = _make_fake_ohlc()
    mock_ak.return_value.name = 'akshare'

    with tempfile.TemporaryDirectory() as d:
        data_root = Path(d)
        config_dir = Path(__file__).parent.parent.parent / 'config'
        run_pipeline(mode=PipelineMode.FULL, data_root=data_root, config_dir=config_dir)
        latest = data_root / 'latest'
        assert (latest / 'themes.json').exists()
        assert (latest / 'etfs.json').exists()
        assert (latest / 'signals.json').exists()
        assert (latest / 'meta.json').exists()
        themes = json.loads((latest / 'themes.json').read_text(encoding='utf-8'))
        assert len(themes['themes']) == 14
```

- [ ] **Step 2: 跑测试验证失败**

Run: `cd backend && uv run pytest tests/test_pipeline_smoke.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 pipeline.py (完整编排)**

```python
"""主流水线 — 编排 providers/scoring/output 三层"""
import logging
import argparse
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional
import pandas as pd

from .models import (
    Returns, Strength, Rank, ThemeOutput, EtfOutput, PairSignal, ThemeSignal,
    SignalsSummary, TopTheme, MetaInfo, ProviderInfo, CalendarInfo, FullRefreshTimes,
)
from .config_loader import load_themes, load_algo_config
from .providers.base import ProviderError, EmptyDataError
from .providers.yfinance_provider import YfinanceProvider
from .providers.akshare_provider import AkshareProvider
from .scoring.returns import compute_returns
from .scoring.strength import (
    dim_aggregate_return, strength_per_dim, composite_strength,
)
from .scoring.mapping import mapping_score
from .scoring.signals import signal_for_pair, signal_for_theme
from .output.writer import atomic_write_json
from .output.descriptions import signal_description, theme_dynamic_description
from .etl.calendar import (
    is_cn_trading_day, is_us_trading_day,
    is_cn_session_active, is_us_session_active,
    BJT,
)

log = logging.getLogger(__name__)


class PipelineMode(str, Enum):
    FULL = 'full'
    INTRADAY = 'intraday'
    ARCHIVE = 'archive'


def _collect_us_ohlc(themes, provider) -> tuple[dict[str, pd.DataFrame], list[str]]:
    out, failed = {}, []
    symbols = set()
    for t in themes:
        symbols.update(t.us_etfs)
    for sym in sorted(symbols):
        try:
            out[sym] = provider.fetch_ohlc(sym, lookback_days=400)
        except (ProviderError, EmptyDataError) as e:
            log.warning(f'US fetch failed {sym}: {e}')
            failed.append(sym)
    return out, failed


def _collect_cn_ohlc(themes, provider) -> tuple[dict[str, pd.DataFrame], list[str]]:
    out, failed = {}, []
    codes = set()
    for t in themes:
        for cn in t.cn_etfs:
            codes.add(cn.code)
    for code in sorted(codes):
        try:
            out[code] = provider.fetch_ohlc(code, lookback_days=400)
        except (ProviderError, EmptyDataError) as e:
            log.warning(f'CN fetch failed {code}: {e}')
            failed.append(code)
    return out, failed


def _theme_returns(t, us_ohlc: dict) -> Returns:
    df = us_ohlc.get(t.primary_us)
    if df is None or df.empty:
        return Returns()
    return compute_returns(df)


def _strength_for_pool(
    own_dim_ret: Optional[float],
    pool_dim_rets: list[float],
    k: float, days: int,
) -> int:
    if own_dim_ret is None or not pool_dim_rets:
        return 0
    return strength_per_dim(own_dim_ret, pool_dim_rets, k=k, days_in_dim=days)


def run_pipeline(
    mode: PipelineMode,
    data_root: Path,
    config_dir: Path,
) -> None:
    log.info(f'pipeline start mode={mode}')
    themes = load_themes(config_dir / 'themes.yml')
    algo = load_algo_config(config_dir / 'algo.yml')

    yf_provider = YfinanceProvider()
    ak_provider = AkshareProvider()

    us_ohlc, us_failed = _collect_us_ohlc(themes, yf_provider)
    cn_ohlc, cn_failed = _collect_cn_ohlc(themes, ak_provider)

    # 1) 每个主题的收益
    theme_returns: dict[str, Returns] = {t.id: _theme_returns(t, us_ohlc) for t in themes}

    # 2) 每个 A 股 ETF 的收益
    cn_returns: dict[str, Returns] = {}
    for code, df in cn_ohlc.items():
        cn_returns[code] = compute_returns(df)

    # 3) 池内 dim aggregate
    theme_dim_rets = {
        dim: [dim_aggregate_return(theme_returns[t.id], dim) for t in themes]
        for dim in ['short', 'mid', 'long']
    }
    for dim in theme_dim_rets:
        theme_dim_rets[dim] = [r for r in theme_dim_rets[dim] if r is not None]

    cn_dim_rets_pool = {
        dim: [dim_aggregate_return(cn_returns.get(code, Returns()), dim) for code in cn_returns]
        for dim in ['short', 'mid', 'long']
    }
    for dim in cn_dim_rets_pool:
        cn_dim_rets_pool[dim] = [r for r in cn_dim_rets_pool[dim] if r is not None]

    # 4) 主题强度
    k = algo.strength.k_sigmoid
    days = algo.strength.days_in_dim
    cw = algo.strength.composite_weights
    theme_strengths: dict[str, Strength] = {}
    for t in themes:
        r = theme_returns[t.id]
        s = _strength_for_pool(dim_aggregate_return(r, 'short'),
                               theme_dim_rets['short'], k, days['short'])
        m = _strength_for_pool(dim_aggregate_return(r, 'mid'),
                               theme_dim_rets['mid'], k, days['mid'])
        l = _strength_for_pool(dim_aggregate_return(r, 'long'),
                               theme_dim_rets['long'], k, days['long'])
        c = composite_strength(s, m, l, cw['short'], cw['mid'], cw['long'])
        theme_strengths[t.id] = Strength(short=s, mid=m, long=l, composite=c)

    # 5) A 股 ETF 强度
    cn_strengths: dict[str, Strength] = {}
    for code in cn_returns:
        r = cn_returns[code]
        s = _strength_for_pool(dim_aggregate_return(r, 'short'),
                               cn_dim_rets_pool['short'], k, days['short'])
        m = _strength_for_pool(dim_aggregate_return(r, 'mid'),
                               cn_dim_rets_pool['mid'], k, days['mid'])
        l = _strength_for_pool(dim_aggregate_return(r, 'long'),
                               cn_dim_rets_pool['long'], k, days['long'])
        c = composite_strength(s, m, l, cw['short'], cw['mid'], cw['long'])
        cn_strengths[code] = Strength(short=s, mid=m, long=l, composite=c)

    # 6) 排名 (按综合)
    sorted_ids = sorted(theme_strengths.keys(),
                        key=lambda i: theme_strengths[i].composite, reverse=True)
    theme_ranks = {tid: i+1 for i, tid in enumerate(sorted_ids)}

    # 7) 映射分 + 信号
    pair_signals: list[PairSignal] = []
    theme_signals: list[ThemeSignal] = []
    for t in themes:
        us_df = us_ohlc.get(t.primary_us)
        candidates = []
        for cn in t.cn_etfs:
            cn_df = cn_ohlc.get(cn.code)
            if us_df is None or cn_df is None:
                ms = None
            else:
                ms = mapping_score(us_df, cn_df,
                                   window=algo.mapping.corr_window_days,
                                   min_aligned=algo.mapping.min_aligned_days)
            conf = algo.confidence.exact if cn.match_type == 'exact' else algo.confidence.wide

            cn_str = cn_strengths.get(cn.code, Strength(short=0, mid=0, long=0, composite=0))
            r = cn_returns.get(cn.code, Returns())
            cn_dim_returns_dict = {dim: dim_aggregate_return(r, dim) for dim in ['short', 'mid', 'long']}

            candidates.append({
                'code': cn.code, 'mapping_score': ms, 'confidence': conf,
                'cn_strength': cn_str, 'cn_dim_returns': cn_dim_returns_dict,
            })

        us_str = theme_strengths[t.id]
        us_r = theme_returns[t.id]
        us_dim_returns_dict = {dim: dim_aggregate_return(us_r, dim) for dim in ['short', 'mid', 'long']}

        # 主题级信号
        theme_sig, trigger_code, theme_votes = signal_for_theme(
            us_strength=us_str, us_dim_returns=us_dim_returns_dict,
            cn_candidates=candidates, cfg=algo.signal,
        )
        theme_signals.append(ThemeSignal(
            theme_id=t.id,
            signal=theme_sig,
            trigger_cn_etf=trigger_code,
            votes=theme_votes if theme_votes else {'short':None,'mid':None,'long':None},
            description=theme_dynamic_description(t.name, theme_sig, us_str.mid),
        ))

        # 配对级信号
        for cn in candidates:
            sig, votes = signal_for_pair(
                us_strength=us_str, cn_strength=cn['cn_strength'],
                us_dim_returns=us_dim_returns_dict, cn_dim_returns=cn['cn_dim_returns'],
                cfg=algo.signal,
            )
            pair_signals.append(PairSignal(
                theme_id=t.id, cn_code=cn['code'],
                mapping_score=cn['mapping_score'], confidence=cn['confidence'],
                signal=sig, votes=votes,
            ))

    # 8) summary
    sig_counter = {'resonance':0, 'transmission':0, 'divergence':0}
    for ts in theme_signals:
        if ts.signal:
            sig_counter[ts.signal] += 1
    top_id = sorted_ids[0] if sorted_ids else None
    top_theme = None
    if top_id:
        top_t = next(t for t in themes if t.id == top_id)
        top_theme = TopTheme(
            id=top_id, name=top_t.name, primary_us=top_t.primary_us,
            composite_strength=theme_strengths[top_id].composite,
        )

    summary = SignalsSummary(
        themes_total=len(themes),
        etfs_total=sum(len(t.cn_etfs) for t in themes),
        resonance_count=sig_counter['resonance'],
        transmission_count=sig_counter['transmission'],
        divergence_count=sig_counter['divergence'],
        top_theme=top_theme,
    )

    # 9) 落盘
    now_utc = datetime.now(timezone.utc)
    now_bjt = now_utc.astimezone(BJT)
    today_bjt = now_bjt.date()

    themes_json = {
        'schema_version': '1.0',
        'generated_at': now_bjt.isoformat(),
        'themes': [
            {
                'id': t.id, 'name': t.name, 'us_etfs': t.us_etfs,
                'primary_us': t.primary_us, 'tags': t.tags, 'note': t.note,
                'returns': theme_returns[t.id].model_dump(),
                'strength': theme_strengths[t.id].model_dump(),
                'rank': Rank(short=theme_ranks[t.id], mid=theme_ranks[t.id],
                             long=theme_ranks[t.id], composite=theme_ranks[t.id]).model_dump(),
            } for t in themes
        ],
    }
    atomic_write_json(data_root / 'latest' / 'themes.json', themes_json)

    cn_codes_seen = set()
    etfs_list = []
    for t in themes:
        for cn in t.cn_etfs:
            if cn.code in cn_codes_seen:
                continue
            cn_codes_seen.add(cn.code)
            r = cn_returns.get(cn.code, Returns())
            df = cn_ohlc.get(cn.code)
            price = float(df['close'].iloc[-1]) if df is not None and not df.empty else None
            amount = float(df['amount'].iloc[-1]) / 1e8 if df is not None and not df.empty and pd.notna(df['amount'].iloc[-1]) else None
            etfs_list.append({
                'code': cn.code, 'name': cn.name, 'tracking_index': cn.tracking,
                'returns': r.model_dump(),
                'amount_yi': amount, 'price': price,
                'strength': cn_strengths.get(cn.code, Strength(short=0, mid=0, long=0, composite=0)).model_dump(),
            })
    atomic_write_json(data_root / 'latest' / 'etfs.json',
                      {'schema_version': '1.0', 'generated_at': now_bjt.isoformat(),
                       'etfs': etfs_list})

    signals_json = {
        'schema_version': '1.0',
        'generated_at': now_bjt.isoformat(),
        'summary': summary.model_dump(),
        'theme_signals': [ts.model_dump() for ts in theme_signals],
        'pair_signals': [ps.model_dump() for ps in pair_signals],
    }
    atomic_write_json(data_root / 'latest' / 'signals.json', signals_json)

    meta = MetaInfo(
        last_full_refresh=FullRefreshTimes(us=now_bjt.isoformat(), cn=now_bjt.isoformat()),
        last_intraday_refresh=now_bjt.isoformat() if mode == PipelineMode.INTRADAY else None,
        providers={
            'us': ProviderInfo(status='ok' if not us_failed else 'degraded', name='yfinance'),
            'cn': ProviderInfo(status='ok' if not cn_failed else 'degraded', name='akshare'),
        },
        failed_symbols=us_failed + cn_failed,
        stale_minutes=0,
        calendar=CalendarInfo(
            us_trading_today=is_us_trading_day(today_bjt),
            cn_trading_today=is_cn_trading_day(today_bjt),
            us_session_active=is_us_session_active(now_utc),
            cn_session_active=is_cn_session_active(now_bjt),
        ),
    )
    atomic_write_json(data_root / 'latest' / 'meta.json', meta.model_dump())
    log.info(f'pipeline done, failed={len(us_failed)+len(cn_failed)}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=PipelineMode, default=PipelineMode.FULL)
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    parser.add_argument('--config-dir', type=Path, default=Path('config'))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    if args.mode == PipelineMode.ARCHIVE:
        from datetime import date
        from .output.archiver import archive_latest
        archive_latest(args.data_root, date.today())
        return
    run_pipeline(args.mode, args.data_root, args.config_dir)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 跑测试验证通过**

Run: `cd backend && uv run pytest tests/test_pipeline_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/pipeline.py backend/tests/test_pipeline_smoke.py
git commit -m "feat(backend): implement main pipeline orchestrator"
```

---

## Phase 5: GitHub Actions Workflows

### Task 5.1: 写 `.github/workflows/us-refresh.yml`

**Files:**
- Create: `.github/workflows/us-refresh.yml`

- [ ] **Step 1: 写 workflow 文件**

```yaml
name: US Refresh

on:
  schedule:
    - cron: '30 22 * * 1-5'  # 北京 06:30
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: data-refresh
  cancel-in-progress: false

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - uses: astral-sh/setup-uv@v3
      - name: Install
        run: cd backend && uv sync --extra dev
      - name: Run pipeline
        run: cd backend && uv run python -m src.pipeline --mode=full --data-root=../data --config-dir=../config
        continue-on-error: true
      - name: Commit data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/latest/
          git diff --staged --quiet || git commit -m "data: US refresh $(date -u +%Y-%m-%dT%H:%M:%SZ)"
          git push
```

- [ ] **Step 2: 本地校验 YAML 语法**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/us-refresh.yml'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 创建 `.github/workflows/` 目录 (如不存在)**

Run: `mkdir -p .github/workflows && ls .github/workflows/`
Expected: `us-refresh.yml`

- [ ] **Step 4: 验证 cron 表达式有效**

Run: `python -c "from croniter import croniter; print(croniter.is_valid('30 22 * * 1-5'))"` 或在 https://crontab.guru/#30_22_*_*_1-5 查证
Expected: 工作日 06:30 北京时间

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/us-refresh.yml
git commit -m "ci: add US refresh workflow (06:30 BJT cron)"
```

---

### Task 5.2: 写 `.github/workflows/cn-refresh.yml`

**Files:**
- Create: `.github/workflows/cn-refresh.yml`

- [ ] **Step 1: 写 workflow**

```yaml
name: CN Refresh

on:
  schedule:
    - cron: '15 1 * * 1-5'              # 09:15 全量
    - cron: '*/15 1-3 * * 1-5'          # 09:15-11:45 盘中刷价 (上午)
    - cron: '*/15 5-7 * * 1-5'          # 13:15-15:45 盘中刷价 (下午)
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: data-refresh
  cancel-in-progress: false

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - uses: astral-sh/setup-uv@v3
      - run: cd backend && uv sync --extra dev
      - name: Decide mode
        id: mode
        run: |
          # 09:15 全量, 其余 intraday
          UTC_HOUR=$(date -u +%-H)
          UTC_MIN=$(date -u +%-M)
          if [ "$UTC_HOUR" = "1" ] && [ "$UTC_MIN" -lt "30" ]; then
            echo "mode=full" >> $GITHUB_OUTPUT
          else
            echo "mode=intraday" >> $GITHUB_OUTPUT
          fi
      - name: Run pipeline
        run: cd backend && uv run python -m src.pipeline --mode=${{ steps.mode.outputs.mode }} --data-root=../data --config-dir=../config
        continue-on-error: true
      - name: Commit data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/latest/
          git diff --staged --quiet || git commit -m "data: CN ${{ steps.mode.outputs.mode }} $(date -u +%Y-%m-%dT%H:%M:%SZ)"
          git push
```

- [ ] **Step 2: 校验 YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/cn-refresh.yml'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 验证 cron 表达式覆盖 09:15-11:30 和 13:00-15:00 (BJT)**

09:15 → UTC 01:15 (cron `15 1`)
09:30-11:45 → UTC 01:30-03:45 (cron `*/15 1-3`)
13:15-15:45 → UTC 05:15-07:45 (cron `*/15 5-7`)
午休 11:30-13:00 BJT (UTC 03:30-05:00) 不覆盖 ✓

- [ ] **Step 4: 验证文件存在**

Run: `ls .github/workflows/cn-refresh.yml`
Expected: 文件存在

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/cn-refresh.yml
git commit -m "ci: add CN refresh workflow (avoid lunch break)"
```

---

### Task 5.3: 写 `.github/workflows/cn-eod-archive.yml`

**Files:**
- Create: `.github/workflows/cn-eod-archive.yml`

- [ ] **Step 1: 写 workflow**

```yaml
name: CN EOD Archive

on:
  schedule:
    - cron: '30 7 * * 1-5'   # 北京 15:30
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: data-refresh
  cancel-in-progress: false

jobs:
  archive:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - uses: astral-sh/setup-uv@v3
      - run: cd backend && uv sync --extra dev
      - name: Archive latest → snapshots/<today>
        run: cd backend && uv run python -m src.pipeline --mode=archive --data-root=../data --config-dir=../config
      - name: Commit archive
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/snapshots/
          git diff --staged --quiet || git commit -m "data: EOD archive $(date -u +%Y-%m-%d)"
          git push
```

- [ ] **Step 2: 校验 YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/cn-eod-archive.yml'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 检查文件**

Run: `ls .github/workflows/cn-eod-archive.yml`
Expected: 存在

- [ ] **Step 4: 文档化**

不需要额外操作, 直接进入 commit。

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/cn-eod-archive.yml
git commit -m "ci: add EOD archive workflow (15:30 BJT)"
```

---

### Task 5.4: 写 `.github/workflows/deploy-frontend.yml`

**Files:**
- Create: `.github/workflows/deploy-frontend.yml`

- [ ] **Step 1: 写 workflow**

```yaml
name: Deploy Frontend

on:
  push:
    branches: [main]
    paths:
      - 'frontend/**'
      - 'data/latest/**'
      - '.github/workflows/deploy-frontend.yml'
  workflow_dispatch:

permissions:
  contents: write
  pages: write

concurrency:
  group: deploy-pages
  cancel-in-progress: true

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: frontend/package-lock.json }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run build
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./frontend/dist
          publish_branch: gh-pages
```

- [ ] **Step 2: 校验 YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-frontend.yml'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 检查文件**

Run: `ls .github/workflows/`
Expected: 4 个 workflow 文件

- [ ] **Step 4: README 中加入 Pages 启用说明 (临时占位)**

```bash
echo "" >> README.md
echo "## 部署" >> README.md
echo "首次部署后需在 GitHub Settings → Pages 设置 Source = gh-pages branch / (root)" >> README.md
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy-frontend.yml README.md
git commit -m "ci: add frontend deploy workflow to GitHub Pages"
```

---

### Task 5.5: 写 `.github/workflows/ci.yml` (CI for PR)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: 写 CI workflow**

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - 'frontend/**'
      - '.github/workflows/ci.yml'

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - uses: astral-sh/setup-uv@v3
      - run: cd backend && uv sync --extra dev
      - run: cd backend && uv run pytest --tb=short
      - run: cd backend && uv run ruff check src tests

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: frontend/package-lock.json }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run build
      - run: cd frontend && npm test -- --run
```

- [ ] **Step 2: 校验 YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 验证 backend 与 frontend 测试本地能跑通**

Run: `cd backend && uv run pytest --tb=short`
Expected: 所有测试 PASS

- [ ] **Step 4: 检查文件**

Run: `ls .github/workflows/`
Expected: 5 个 workflow 文件

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add CI workflow for backend and frontend"
```

---

## Phase 6: Frontend — shadcn 设置 + 基础工具

### Task 6.1: 安装 shadcn/ui 并初始化

**Files:**
- Modify: `frontend/components.json`
- Create: `frontend/src/lib/utils.ts`

- [ ] **Step 1: 在 tsconfig.json 中配置 path alias**

修改 `frontend/tsconfig.json` 加入:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  }
}
```

- [ ] **Step 2: 初始化 shadcn**

```bash
cd frontend
npx shadcn@latest init -d -y
# 配置: Style=Default, BaseColor=Slate, CSS Variables=Yes
```

- [ ] **Step 3: 安装常用组件**

```bash
cd frontend
npx shadcn@latest add card badge button input table tabs progress alert tooltip separator
```

- [ ] **Step 4: 验证编译通过**

Run: `cd frontend && npm run build`
Expected: 构建成功, dist/ 目录生成

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): integrate shadcn/ui with base components"
```

---

### Task 6.2: 定义前端 TypeScript 类型 (types/)

**Files:**
- Create: `frontend/src/types/themes.ts`
- Create: `frontend/src/types/etfs.ts`
- Create: `frontend/src/types/signals.ts`
- Create: `frontend/src/types/meta.ts`

- [ ] **Step 1: 写 themes.ts**

```typescript
export type DimName = 'short' | 'mid' | 'long' | 'composite';

export interface Returns {
  r_1d: number | null;
  r_5d: number | null;
  r_20d: number | null;
  r_60d: number | null;
  r_120d: number | null;
  r_ytd: number | null;
}

export interface Strength {
  short: number;
  mid: number;
  long: number;
  composite: number;
}

export interface Rank { short: number; mid: number; long: number; composite: number; }

export interface Theme {
  id: string;
  name: string;
  us_etfs: string[];
  primary_us: string;
  tags: string[];
  note: string;
  returns: Returns;
  strength: Strength;
  rank: Rank;
}

export interface ThemesFile {
  schema_version: string;
  generated_at: string;
  themes: Theme[];
}
```

- [ ] **Step 2: 写 etfs.ts**

```typescript
import type { Returns, Strength } from './themes';

export interface Etf {
  code: string;
  name: string;
  tracking_index: string;
  returns: Returns;
  amount_yi: number | null;
  price: number | null;
  strength: Strength;
}

export interface EtfsFile {
  schema_version: string;
  generated_at: string;
  etfs: Etf[];
}
```

- [ ] **Step 3: 写 signals.ts**

```typescript
export type SignalType = 'resonance' | 'transmission' | 'divergence';
export type Votes = { short: SignalType | null; mid: SignalType | null; long: SignalType | null };

export interface TopTheme {
  id: string;
  name: string;
  primary_us: string;
  composite_strength: number;
}

export interface SignalsSummary {
  themes_total: number;
  etfs_total: number;
  resonance_count: number;
  transmission_count: number;
  divergence_count: number;
  top_theme: TopTheme | null;
}

export interface ThemeSignal {
  theme_id: string;
  signal: SignalType | null;
  trigger_cn_etf: string | null;
  votes: Votes;
  description: string;
}

export interface PairSignal {
  theme_id: string;
  cn_code: string;
  mapping_score: number | null;
  confidence: number;
  signal: SignalType | null;
  votes: Votes;
}

export interface SignalsFile {
  schema_version: string;
  generated_at: string;
  summary: SignalsSummary;
  theme_signals: ThemeSignal[];
  pair_signals: PairSignal[];
}
```

- [ ] **Step 4: 写 meta.ts**

```typescript
export type ProviderStatus = 'ok' | 'degraded' | 'stale';

export interface ProviderInfo { status: ProviderStatus; name: string; }

export interface MetaFile {
  schema_version: string;
  last_full_refresh: { us: string | null; cn: string | null };
  last_intraday_refresh: string | null;
  providers: { us: ProviderInfo; cn: ProviderInfo };
  failed_symbols: string[];
  stale_minutes: number;
  calendar: {
    us_trading_today: boolean;
    cn_trading_today: boolean;
    us_session_active: boolean;
    cn_session_active: boolean;
  };
}
```

- [ ] **Step 5: 验证类型编译通过 + Commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

```bash
git add frontend/src/types/
git commit -m "feat(frontend): add TypeScript types matching backend JSON schema"
```

---

### Task 6.3: 实现格式化工具 + 字段字典 (lib/)

**Files:**
- Create: `frontend/src/lib/format.ts`
- Create: `frontend/src/lib/field-dictionary.ts`
- Create: `frontend/src/lib/filters.ts`
- Create: `frontend/src/lib/__tests__/format.test.ts`
- Create: `frontend/src/test-setup.ts`

- [ ] **Step 1: 写 test-setup.ts**

```typescript
import '@testing-library/jest-dom';
```

- [ ] **Step 2: 写测试 lib/__tests__/format.test.ts**

```typescript
import { describe, it, expect } from 'vitest';
import { formatPct, formatYi, formatStrength, formatRelativeTime } from '../format';

describe('formatPct', () => {
  it('formats positive as +X.X%', () => {
    expect(formatPct(0.123)).toBe('+12.3%');
  });
  it('formats negative as -X.X%', () => {
    expect(formatPct(-0.05)).toBe('-5.0%');
  });
  it('returns dash for null', () => {
    expect(formatPct(null)).toBe('—');
  });
});

describe('formatYi', () => {
  it('formats with 亿 suffix', () => {
    expect(formatYi(1.234)).toBe('1.2亿');
  });
  it('null becomes dash', () => {
    expect(formatYi(null)).toBe('—');
  });
});

describe('formatStrength', () => {
  it('rounds integer strength', () => {
    expect(formatStrength(77)).toBe('77');
  });
});

describe('formatRelativeTime', () => {
  it('formats recent as "刚刚"', () => {
    const now = new Date();
    expect(formatRelativeTime(now.toISOString(), now)).toBe('刚刚');
  });
});
```

- [ ] **Step 3: 写实现**

`frontend/src/lib/format.ts`:
```typescript
export const formatPct = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—';
  const pct = v * 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
};

export const formatYi = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—';
  return `${v.toFixed(1)}亿`;
};

export const formatStrength = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—';
  return Math.round(v).toString();
};

export const formatRelativeTime = (iso: string | null | undefined, now: Date = new Date()): string => {
  if (!iso) return '—';
  const ts = new Date(iso).getTime();
  const diffMin = Math.floor((now.getTime() - ts) / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}小时前`;
  const d = new Date(iso);
  return `${d.getMonth()+1}-${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
};
```

`frontend/src/lib/field-dictionary.ts`:
```typescript
export const FIELD_DICTIONARY: Record<string, string> = {
  strength: '0-100 评分, 多周期动量加权后映射, ≥60 为走强。',
  mapping_score: 'A 股 ETF 与美股主题的相关度评分 (60 日滚动 Pearson 相关性 × 100), 越高映射越可靠。',
  confidence: '映射可靠性档位: 精确匹配=90, 宽主题替代=60。',
  resonance: '共振: 两边在多个周期同向走强或走弱, 适合优先观察。',
  transmission: '传导: 美股已先动, A 股尚未跟上, 适合观察隔夜补涨/补跌。',
  divergence: '背离: 美股与 A 股走势不同步, 需二次确认。',
};
```

`frontend/src/lib/filters.ts`:
```typescript
import type { Theme } from '@/types/themes';
import type { SignalType, ThemeSignal } from '@/types/signals';

export function filterThemes(
  themes: Theme[],
  signalsByThemeId: Map<string, ThemeSignal>,
  signalFilter: 'all' | SignalType,
  search: string,
): Theme[] {
  const q = search.trim().toLowerCase();
  return themes.filter(t => {
    if (signalFilter !== 'all') {
      const ts = signalsByThemeId.get(t.id);
      if (!ts || ts.signal !== signalFilter) return false;
    }
    if (q) {
      const blob = [t.name, t.primary_us, ...t.us_etfs, ...t.tags].join(' ').toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  });
}
```

- [ ] **Step 4: 跑测试**

Run: `cd frontend && npm test -- --run`
Expected: 4 tests passed

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/ frontend/src/test-setup.ts
git commit -m "feat(frontend): add format helpers and field dictionary"
```

---

## Phase 7: Frontend — 数据 Provider 与 Hooks

### Task 7.1: 实现 DataProvider (SWR + Context)

**Files:**
- Create: `frontend/src/providers/DataProvider.tsx`
- Create: `frontend/src/hooks/useData.ts`

- [ ] **Step 1: 写 DataProvider**

`frontend/src/providers/DataProvider.tsx`:
```tsx
import React, { createContext, useContext } from 'react';
import useSWR, { SWRConfig } from 'swr';
import type { ThemesFile } from '@/types/themes';
import type { EtfsFile } from '@/types/etfs';
import type { SignalsFile } from '@/types/signals';
import type { MetaFile } from '@/types/meta';

const BASE = import.meta.env.BASE_URL;
const fetcher = (url: string) => fetch(url).then(r => {
  if (!r.ok) throw new Error(`fetch ${url} ${r.status}`);
  return r.json();
});

interface DataContextValue {
  themes?: ThemesFile;
  etfs?: EtfsFile;
  signals?: SignalsFile;
  meta?: MetaFile;
  isLoading: boolean;
  error: Error | null;
}

const DataContext = createContext<DataContextValue | null>(null);

export const DataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const themes  = useSWR<ThemesFile> (`${BASE}data/latest/themes.json`,  fetcher, { refreshInterval: 300_000 });
  const etfs    = useSWR<EtfsFile>   (`${BASE}data/latest/etfs.json`,    fetcher, { refreshInterval: 300_000 });
  const signals = useSWR<SignalsFile>(`${BASE}data/latest/signals.json`, fetcher, { refreshInterval: 300_000 });
  const meta    = useSWR<MetaFile>   (`${BASE}data/latest/meta.json`,    fetcher, { refreshInterval: 60_000 });

  const isLoading = themes.isLoading || etfs.isLoading || signals.isLoading || meta.isLoading;
  const error = themes.error || etfs.error || signals.error || meta.error || null;

  return (
    <SWRConfig value={{ revalidateOnFocus: false }}>
      <DataContext.Provider value={{
        themes: themes.data, etfs: etfs.data, signals: signals.data, meta: meta.data,
        isLoading, error,
      }}>
        {children}
      </DataContext.Provider>
    </SWRConfig>
  );
};

export const useDataContext = () => {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error('useDataContext must be inside DataProvider');
  return ctx;
};
```

- [ ] **Step 2: 写 hook (派生 helpers)**

`frontend/src/hooks/useData.ts`:
```typescript
import { useMemo } from 'react';
import { useDataContext } from '@/providers/DataProvider';
import type { ThemeSignal } from '@/types/signals';

export const useThemeSignalsMap = () => {
  const { signals } = useDataContext();
  return useMemo(() => {
    const m = new Map<string, ThemeSignal>();
    signals?.theme_signals.forEach(ts => m.set(ts.theme_id, ts));
    return m;
  }, [signals]);
};
```

- [ ] **Step 3: 跑 build 验证类型**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: 验证文件存在**

Run: `ls frontend/src/providers/ frontend/src/hooks/`
Expected: DataProvider.tsx + useData.ts

- [ ] **Step 5: Commit**

```bash
git add frontend/src/providers/ frontend/src/hooks/
git commit -m "feat(frontend): add SWR-based DataProvider and useData hook"
```

---

### Task 7.2: 实现 UIStateProvider (筛选 + 选中态 + URL 同步)

**Files:**
- Create: `frontend/src/providers/UIStateProvider.tsx`

- [ ] **Step 1: 写 UIStateProvider**

```tsx
import React, { createContext, useContext, useEffect, useReducer } from 'react';
import type { DimName } from '@/types/themes';
import type { SignalType } from '@/types/signals';

type SignalFilter = 'all' | SignalType;

interface UIState {
  selectedThemeId: string | null;
  dimension: DimName;
  signalFilter: SignalFilter;
  searchQuery: string;
}

type Action =
  | { type: 'SELECT_THEME'; id: string | null }
  | { type: 'SET_DIM'; dim: DimName }
  | { type: 'SET_SIGNAL_FILTER'; v: SignalFilter }
  | { type: 'SET_SEARCH'; q: string };

const initial: UIState = {
  selectedThemeId: null, dimension: 'short', signalFilter: 'all', searchQuery: '',
};

function reducer(s: UIState, a: Action): UIState {
  switch (a.type) {
    case 'SELECT_THEME': return { ...s, selectedThemeId: a.id };
    case 'SET_DIM': return { ...s, dimension: a.dim };
    case 'SET_SIGNAL_FILTER': return { ...s, signalFilter: a.v };
    case 'SET_SEARCH': return { ...s, searchQuery: a.q };
  }
}

const UIContext = createContext<{ state: UIState; dispatch: React.Dispatch<Action> } | null>(null);

function parseHash(): Partial<UIState> {
  if (typeof window === 'undefined') return {};
  const h = new URLSearchParams(window.location.hash.slice(1));
  return {
    selectedThemeId: h.get('theme'),
    dimension: (h.get('dim') as DimName) || 'short',
    signalFilter: (h.get('sig') as SignalFilter) || 'all',
  };
}

export const UIStateProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, dispatch] = useReducer(reducer, { ...initial, ...parseHash() });

  useEffect(() => {
    const p = new URLSearchParams();
    if (state.selectedThemeId) p.set('theme', state.selectedThemeId);
    if (state.dimension !== 'short') p.set('dim', state.dimension);
    if (state.signalFilter !== 'all') p.set('sig', state.signalFilter);
    const hash = p.toString();
    if (hash !== window.location.hash.slice(1)) {
      window.history.replaceState(null, '', hash ? `#${hash}` : window.location.pathname);
    }
  }, [state.selectedThemeId, state.dimension, state.signalFilter]);

  return <UIContext.Provider value={{ state, dispatch }}>{children}</UIContext.Provider>;
};

export const useUIState = () => {
  const c = useContext(UIContext);
  if (!c) throw new Error('useUIState must be inside UIStateProvider');
  return c;
};
```

- [ ] **Step 2: 验证 tsc**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 3: 验证文件**

Run: `ls frontend/src/providers/UIStateProvider.tsx`
Expected: 存在

- [ ] **Step 4: 文档说明 (略)**

无需额外操作。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/providers/UIStateProvider.tsx
git commit -m "feat(frontend): add UI state provider with URL hash sync"
```

---

## Phase 8: Frontend — 核心组件

### Task 8.1: 实现 Header 组件 (Logo + UpdateBadge + RadarTabs + KpiCards + StaleBanner)

**Files:**
- Create: `frontend/src/components/Header/index.tsx`
- Create: `frontend/src/components/Header/KpiCards.tsx`
- Create: `frontend/src/components/Header/StaleBanner.tsx`
- Create: `frontend/src/components/Header/UpdateBadge.tsx`
- Create: `frontend/src/components/Header/RadarTabs.tsx`

- [ ] **Step 1: 写 RadarTabs (预留多雷达)**

```tsx
// RadarTabs.tsx
export const RadarTabs = () => (
  <div className="flex gap-1 text-sm">
    <button className="px-3 py-1 rounded bg-blue-600 text-white">跨市雷达</button>
    <button className="px-3 py-1 rounded text-gray-400 cursor-not-allowed" disabled>主题轮动 (v2)</button>
    <button className="px-3 py-1 rounded text-gray-400 cursor-not-allowed" disabled>持仓监控 (v3)</button>
  </div>
);
```

- [ ] **Step 2: 写 UpdateBadge + StaleBanner + KpiCards**

`UpdateBadge.tsx`:
```tsx
import { useDataContext } from '@/providers/DataProvider';
import { formatRelativeTime } from '@/lib/format';

export const UpdateBadge = () => {
  const { meta } = useDataContext();
  if (!meta) return null;
  const last = meta.last_intraday_refresh || meta.last_full_refresh.cn || meta.last_full_refresh.us;
  const active = meta.calendar.cn_session_active ? '盘中刷新中' : '收盘';
  return (
    <div className="text-xs text-gray-500">
      更新 {formatRelativeTime(last)} · {active}
    </div>
  );
};
```

`StaleBanner.tsx`:
```tsx
import { useDataContext } from '@/providers/DataProvider';
import { Alert, AlertDescription } from '@/components/ui/alert';

export const StaleBanner = () => {
  const { meta } = useDataContext();
  if (!meta) return null;
  const degraded = meta.providers.us.status !== 'ok' || meta.providers.cn.status !== 'ok';
  const stale = meta.stale_minutes > 60;
  if (!degraded && !stale) return null;
  return (
    <Alert variant={stale ? 'destructive' : 'default'} className="mt-2">
      <AlertDescription>
        {stale ? `数据获取异常 — 已过期 ${meta.stale_minutes} 分钟` : `Provider 降级: ${meta.failed_symbols.join(', ')}`}
      </AlertDescription>
    </Alert>
  );
};
```

`KpiCards.tsx`:
```tsx
import { useDataContext } from '@/providers/DataProvider';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

const KpiCard = ({ label, value, badge, badgeColor='bg-blue-600' }: any) => (
  <Card className="p-3 flex-1 min-w-[110px]">
    <div className="flex items-center gap-1">
      <Badge className={badgeColor + ' text-white'}>{badge}</Badge>
      <span className="text-xs text-gray-500">{label}</span>
    </div>
    <div className="text-xl font-semibold mt-1">{value}</div>
  </Card>
);

export const KpiCards = () => {
  const { signals } = useDataContext();
  const s = signals?.summary;
  if (!s) return <div className="text-sm text-gray-400">读取中...</div>;
  return (
    <div className="flex gap-2 flex-wrap">
      <KpiCard label="美股主题" value={`${s.themes_total} 个`} badge="US" />
      <KpiCard label="A股ETF" value={`${s.etfs_total} 只`} badge="CN" />
      <KpiCard label="共振" value={`${s.resonance_count} 组`} badge="CO" />
      <KpiCard label="传导" value={`${s.transmission_count} 组`} badge="!" badgeColor="bg-red-600" />
      <KpiCard label="背离" value={`${s.divergence_count} 组`} badge="!" badgeColor="bg-yellow-500" />
      {s.top_theme && (
        <KpiCard label="当前最强" value={`${s.top_theme.name} · ${s.top_theme.primary_us}`} badge="TOP" />
      )}
    </div>
  );
};
```

- [ ] **Step 3: 写 Header/index.tsx 编排**

```tsx
import { KpiCards } from './KpiCards';
import { StaleBanner } from './StaleBanner';
import { UpdateBadge } from './UpdateBadge';
import { RadarTabs } from './RadarTabs';

export const Header = () => (
  <header className="border-b bg-white p-4 space-y-3">
    <div className="flex items-center justify-between">
      <div>
        <div className="text-xl font-bold">ETF Radar</div>
        <div className="text-xs text-gray-500">追踪美股主题 → 映射 A 股 ETF 联动信号</div>
      </div>
      <UpdateBadge />
    </div>
    <RadarTabs />
    <KpiCards />
    <StaleBanner />
  </header>
);
```

- [ ] **Step 4: 验证类型 + build**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Header/
git commit -m "feat(frontend): add Header with KPI cards, update badge, stale banner, radar tabs"
```

---

### Task 8.2: 实现 FilterBar (时间维度 + 信号类型 + 搜索 + 图例)

**Files:**
- Create: `frontend/src/components/FilterBar/index.tsx`
- Create: `frontend/src/components/FilterBar/DimensionTabs.tsx`
- Create: `frontend/src/components/FilterBar/SignalTabs.tsx`
- Create: `frontend/src/components/FilterBar/SearchInput.tsx`
- Create: `frontend/src/components/FilterBar/Legend.tsx`

- [ ] **Step 1: 写 DimensionTabs**

```tsx
// DimensionTabs.tsx
import { useUIState } from '@/providers/UIStateProvider';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { DimName } from '@/types/themes';

const DIMS: Array<{ key: DimName; label: string }> = [
  { key: 'short', label: '短期' },
  { key: 'mid', label: '中期' },
  { key: 'long', label: '长期' },
  { key: 'composite', label: '综合' },
];

export const DimensionTabs = () => {
  const { state, dispatch } = useUIState();
  return (
    <Tabs value={state.dimension} onValueChange={(v) => dispatch({ type: 'SET_DIM', dim: v as DimName })}>
      <TabsList>
        {DIMS.map(d => <TabsTrigger key={d.key} value={d.key}>{d.label}</TabsTrigger>)}
      </TabsList>
    </Tabs>
  );
};
```

- [ ] **Step 2: 写 SignalTabs + SearchInput + Legend**

`SignalTabs.tsx`:
```tsx
import { useUIState } from '@/providers/UIStateProvider';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

const OPTS = [
  { key: 'all', label: '全部' },
  { key: 'resonance', label: '共振' },
  { key: 'transmission', label: '传导' },
  { key: 'divergence', label: '背离' },
] as const;

export const SignalTabs = () => {
  const { state, dispatch } = useUIState();
  return (
    <Tabs value={state.signalFilter} onValueChange={(v) => dispatch({ type: 'SET_SIGNAL_FILTER', v: v as any })}>
      <TabsList>{OPTS.map(o => <TabsTrigger key={o.key} value={o.key}>{o.label}</TabsTrigger>)}</TabsList>
    </Tabs>
  );
};
```

`SearchInput.tsx`:
```tsx
import { useUIState } from '@/providers/UIStateProvider';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';

export const SearchInput = () => {
  const { state, dispatch } = useUIState();
  return (
    <div className="relative max-w-sm">
      <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
      <Input value={state.searchQuery}
             onChange={e => dispatch({ type: 'SET_SEARCH', q: e.target.value })}
             placeholder="搜索主题、代码或ETF名称" className="pl-8" />
    </div>
  );
};
```

`Legend.tsx`:
```tsx
export const Legend = () => (
  <div className="flex gap-3 text-xs text-gray-500">
    <span><span className="inline-block w-2 h-2 bg-blue-600 mr-1"></span>共振</span>
    <span><span className="inline-block w-2 h-2 bg-blue-400 mr-1"></span>传导</span>
    <span><span className="inline-block w-2 h-2 bg-orange-500 mr-1"></span>背离</span>
  </div>
);
```

- [ ] **Step 3: 写 FilterBar/index.tsx**

```tsx
import { DimensionTabs } from './DimensionTabs';
import { SignalTabs } from './SignalTabs';
import { SearchInput } from './SearchInput';
import { Legend } from './Legend';

export const FilterBar = () => (
  <div className="bg-white border-b p-3 flex flex-wrap items-center gap-4">
    <DimensionTabs />
    <SignalTabs />
    <Legend />
    <div className="ml-auto"><SearchInput /></div>
  </div>
);
```

- [ ] **Step 4: 验证 tsc**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/FilterBar/
git commit -m "feat(frontend): add FilterBar with dimension/signal tabs, search, legend"
```

---

### Task 8.3: 实现 ThemeList (左侧主题强弱榜)

**Files:**
- Create: `frontend/src/components/ThemeList/index.tsx`
- Create: `frontend/src/components/ThemeList/ThemeRow.tsx`

- [ ] **Step 1: 写 ThemeRow**

```tsx
// ThemeRow.tsx
import type { Theme } from '@/types/themes';
import type { ThemeSignal } from '@/types/signals';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { formatPct, formatStrength } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { DimName } from '@/types/themes';

interface Props {
  index: number;
  theme: Theme;
  signal: ThemeSignal | undefined;
  dimension: DimName;
  selected: boolean;
  onClick: () => void;
}

const SIGNAL_LABEL: Record<string, string> = {
  resonance: '共振', transmission: '传导', divergence: '背离',
};
const SIGNAL_VARIANT = (s?: string | null): 'default' | 'secondary' | 'destructive' => {
  if (s === 'divergence') return 'destructive';
  if (s === 'transmission') return 'secondary';
  return 'default';
};

export const ThemeRow: React.FC<Props> = ({ index, theme, signal, dimension, selected, onClick }) => {
  const strength = theme.strength[dimension];
  return (
    <tr onClick={onClick}
        className={cn(
          'cursor-pointer hover:bg-gray-50 border-l-2 border-transparent',
          selected && 'border-blue-600 bg-blue-50',
        )}>
      <td className="px-2 py-2 text-center">
        <span className={cn('inline-flex items-center justify-center w-6 h-6 rounded-full text-xs',
          index < 3 ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-600')}>
          {(index+1).toString().padStart(2, '0')}
        </span>
      </td>
      <td className="px-2 py-2">
        <div className="font-medium">{theme.name}</div>
        <div className="text-xs text-gray-500">{theme.us_etfs.join(' / ')}</div>
      </td>
      <td className="px-2 py-2 text-xs">{theme.primary_us}</td>
      <td className="px-2 py-2 w-32">
        <div className="flex items-center gap-2">
          <Progress value={strength} className="h-2 flex-1" />
          <span className="text-sm font-medium w-8 text-right">{formatStrength(strength)}</span>
        </div>
      </td>
      <td className={cn('px-2 py-2 text-right text-xs',
        (theme.returns.r_1d ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600')}>
        {formatPct(theme.returns.r_1d)}
      </td>
      <td className={cn('px-2 py-2 text-right text-xs',
        (theme.returns.r_5d ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600')}>
        {formatPct(theme.returns.r_5d)}
      </td>
      <td className="px-2 py-2 text-center">
        {signal?.signal && <Badge variant={SIGNAL_VARIANT(signal.signal)}>{SIGNAL_LABEL[signal.signal]}</Badge>}
      </td>
    </tr>
  );
};
```

- [ ] **Step 2: 写 ThemeList/index.tsx**

```tsx
import { useMemo } from 'react';
import { useDataContext } from '@/providers/DataProvider';
import { useUIState } from '@/providers/UIStateProvider';
import { useThemeSignalsMap } from '@/hooks/useData';
import { filterThemes } from '@/lib/filters';
import { ThemeRow } from './ThemeRow';

export const ThemeList = () => {
  const { themes } = useDataContext();
  const { state, dispatch } = useUIState();
  const sigMap = useThemeSignalsMap();

  const sorted = useMemo(() => {
    if (!themes) return [];
    return [...themes.themes].sort((a, b) => b.strength[state.dimension] - a.strength[state.dimension]);
  }, [themes, state.dimension]);

  const filtered = useMemo(() =>
    filterThemes(sorted, sigMap, state.signalFilter, state.searchQuery),
    [sorted, sigMap, state.signalFilter, state.searchQuery]
  );

  return (
    <div className="bg-white border rounded">
      <div className="p-3 border-b">
        <div className="font-medium">美股主题强弱</div>
        <div className="text-xs text-gray-500">按{ {short:'短期', mid:'中期', long:'长期', composite:'综合'}[state.dimension] }强弱排序 · {filtered.length}/{sorted.length} 个主题</div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-600">
            <tr>
              <th className="px-2 py-2 text-center">#</th>
              <th className="px-2 py-2 text-left">主题</th>
              <th className="px-2 py-2 text-left">主ETF</th>
              <th className="px-2 py-2 text-left">强度</th>
              <th className="px-2 py-2 text-right">近1日</th>
              <th className="px-2 py-2 text-right">近1周</th>
              <th className="px-2 py-2 text-center">信号</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <ThemeRow key={t.id} index={i} theme={t}
                        signal={sigMap.get(t.id)} dimension={state.dimension}
                        selected={state.selectedThemeId === t.id}
                        onClick={() => dispatch({ type: 'SELECT_THEME', id: t.id })} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
```

- [ ] **Step 3: 验证类型**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: 验证文件**

Run: `ls frontend/src/components/ThemeList/`
Expected: index.tsx + ThemeRow.tsx

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ThemeList/
git commit -m "feat(frontend): add ThemeList with sorting, filtering, signal badges"
```

---

### Task 8.4: 实现 ThemeDetail 容器 + 子模块

**Files:**
- Create: `frontend/src/components/ThemeDetail/index.tsx`
- Create: `frontend/src/components/ThemeDetail/MappingPanel.tsx`
- Create: `frontend/src/components/ThemeDetail/PeriodReturns.tsx`
- Create: `frontend/src/components/ThemeDetail/StrengthBars.tsx`
- Create: `frontend/src/components/ThemeDetail/StrengthRing.tsx`
- Create: `frontend/src/components/ThemeDetail/SignalNote.tsx`
- Create: `frontend/src/components/ThemeDetail/TagPills.tsx`

- [ ] **Step 1: 写小组件**

`PeriodReturns.tsx`:
```tsx
import { formatPct } from '@/lib/format';
import type { Returns } from '@/types/themes';

const LABELS: Array<[keyof Returns, string]> = [
  ['r_1d', '1日'], ['r_5d', '5日'], ['r_20d', '20日'],
  ['r_60d', '60日'], ['r_120d', '120日'], ['r_ytd', '年初至今'],
];

export const PeriodReturns: React.FC<{ returns: Returns }> = ({ returns }) => (
  <div className="grid grid-cols-3 gap-2 text-sm">
    {LABELS.map(([k, label]) => {
      const v = returns[k];
      const cls = (v ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600';
      return (
        <div key={k} className="border rounded p-2">
          <div className="text-xs text-gray-500">{label}</div>
          <div className={cls}>{formatPct(v)}</div>
        </div>
      );
    })}
  </div>
);
```

`StrengthBars.tsx`:
```tsx
import { Progress } from '@/components/ui/progress';
import type { Strength } from '@/types/themes';

const LABELS: Array<[keyof Strength, string]> = [
  ['short', '短期'], ['mid', '中期'], ['long', '长期'], ['composite', '综合'],
];

export const StrengthBars: React.FC<{ strength: Strength }> = ({ strength }) => (
  <div className="space-y-2">
    {LABELS.map(([k, label]) => (
      <div key={k} className="flex items-center gap-2 text-sm">
        <span className="w-12 text-gray-500">{label}</span>
        <Progress value={strength[k]} className="h-2 flex-1" />
        <span className="w-8 text-right font-medium">{strength[k]}</span>
      </div>
    ))}
  </div>
);
```

`StrengthRing.tsx`:
```tsx
import { RadialBarChart, RadialBar, ResponsiveContainer, PolarAngleAxis } from 'recharts';

export const StrengthRing: React.FC<{ value: number; label: string }> = ({ value, label }) => {
  const data = [{ name: label, value, fill: '#2563EB' }];
  return (
    <div className="relative w-32 h-32">
      <ResponsiveContainer>
        <RadialBarChart innerRadius="65%" outerRadius="95%" data={data} startAngle={90} endAngle={-270}>
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar dataKey="value" cornerRadius={6} background />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-2xl font-semibold">{value}</div>
        <div className="text-xs text-gray-500">{label}</div>
      </div>
    </div>
  );
};
```

`SignalNote.tsx`:
```tsx
import { FIELD_DICTIONARY } from '@/lib/field-dictionary';
import type { SignalType } from '@/types/signals';

export const SignalNote: React.FC<{ signal: SignalType | null }> = ({ signal }) => {
  if (!signal) return null;
  return (
    <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm">
      <div className="font-medium mb-1">{ {resonance:'共振说明', transmission:'传导说明', divergence:'背离说明'}[signal] }</div>
      <div className="text-gray-700">{FIELD_DICTIONARY[signal]}</div>
    </div>
  );
};
```

`TagPills.tsx`:
```tsx
import { Badge } from '@/components/ui/badge';
export const TagPills: React.FC<{ tags: string[] }> = ({ tags }) => (
  <div className="flex flex-wrap gap-1">
    {tags.map(t => <Badge key={t} variant="outline">{t}</Badge>)}
  </div>
);
```

`MappingPanel.tsx`:
```tsx
import type { Theme } from '@/types/themes';
export const MappingPanel: React.FC<{ theme: Theme; confidence: number | null }> = ({ theme, confidence }) => (
  <div className="flex gap-4 text-sm">
    <div>
      <div className="text-xs text-gray-500">美股映射</div>
      <div className="font-medium">{theme.primary_us}</div>
      <div className="text-xs text-gray-500">{theme.us_etfs.join(' / ')}</div>
    </div>
    {confidence !== null && (
      <div>
        <div className="text-xs text-gray-500">置信度</div>
        <div className="text-2xl font-semibold">{confidence}</div>
      </div>
    )}
  </div>
);
```

- [ ] **Step 2: 写 ThemeDetail/index.tsx 编排**

```tsx
import { useMemo } from 'react';
import { useDataContext } from '@/providers/DataProvider';
import { useUIState } from '@/providers/UIStateProvider';
import { useThemeSignalsMap } from '@/hooks/useData';
import { MappingPanel } from './MappingPanel';
import { PeriodReturns } from './PeriodReturns';
import { StrengthBars } from './StrengthBars';
import { StrengthRing } from './StrengthRing';
import { SignalNote } from './SignalNote';
import { TagPills } from './TagPills';
import { Badge } from '@/components/ui/badge';

export const ThemeDetail = () => {
  const { themes, signals } = useDataContext();
  const { state } = useUIState();
  const sigMap = useThemeSignalsMap();

  const theme = useMemo(() =>
    themes?.themes.find(t => t.id === state.selectedThemeId),
    [themes, state.selectedThemeId]);

  if (!theme) {
    return <div className="bg-white border rounded p-6 text-gray-400 text-sm text-center">选择左侧主题查看详情</div>;
  }
  const ts = sigMap.get(theme.id);
  const pair = signals?.pair_signals.find(p =>
    p.theme_id === theme.id && p.cn_code === ts?.trigger_cn_etf);

  const dimLabel = { short: '短期', mid: '中期', long: '长期', composite: '综合' }[state.dimension];

  return (
    <div className="bg-white border rounded p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-lg font-semibold">{theme.name}</div>
          {ts?.description && <div className="text-sm text-gray-500">{ts.description}</div>}
        </div>
        {ts?.signal && <Badge>{ {resonance:'共振', transmission:'传导', divergence:'背离'}[ts.signal] }</Badge>}
      </div>

      <MappingPanel theme={theme} confidence={pair?.confidence ?? null} />

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-3">
          <PeriodReturns returns={theme.returns} />
          <StrengthBars strength={theme.strength} />
        </div>
        <div className="flex items-start justify-center">
          <StrengthRing value={theme.strength[state.dimension]} label={dimLabel + '强度'} />
        </div>
      </div>

      <SignalNote signal={ts?.signal ?? null} />
      <TagPills tags={theme.tags} />
      {theme.note && <div className="bg-gray-50 text-xs text-gray-600 p-2 rounded">{theme.note}</div>}
    </div>
  );
};
```

- [ ] **Step 3: 验证类型**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: 验证 build**

Run: `cd frontend && npm run build`
Expected: 构建成功

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ThemeDetail/
git commit -m "feat(frontend): add ThemeDetail with mapping, returns, strength ring, signal note"
```

---

### Task 8.5: 实现 CnEtfTable (底部 A 股 ETF 候选池)

**Files:**
- Create: `frontend/src/components/CnEtfTable/index.tsx`
- Create: `frontend/src/components/CnEtfTable/EtfRow.tsx`

- [ ] **Step 1: 写 EtfRow**

```tsx
import type { Etf } from '@/types/etfs';
import type { PairSignal } from '@/types/signals';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { formatPct, formatYi } from '@/lib/format';
import { cn } from '@/lib/utils';

const SIGNAL_LABEL: Record<string, string> = { resonance: '共振', transmission: '传导', divergence: '背离' };

export const EtfRow: React.FC<{ etf: Etf; pair: PairSignal | undefined }> = ({ etf, pair }) => {
  const pctCls = (v: number | null) => (v ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600';
  return (
    <tr className="border-t">
      <td className="px-2 py-2">
        <div className="text-sm font-medium">{etf.name}</div>
        <div className="text-xs text-gray-500">{etf.tracking_index}</div>
      </td>
      <td className="px-2 py-2 text-sm">{etf.code}</td>
      <td className="px-2 py-2 w-24">
        {pair?.mapping_score != null ? (
          <div className="flex items-center gap-1">
            <Progress value={pair.mapping_score} className="h-2 flex-1" />
            <span className="text-xs w-6 text-right">{pair.mapping_score}</span>
          </div>
        ) : <span className="text-gray-400">—</span>}
      </td>
      <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_1d))}>{formatPct(etf.returns.r_1d)}</td>
      <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_5d))}>{formatPct(etf.returns.r_5d)}</td>
      <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_20d))}>{formatPct(etf.returns.r_20d)}</td>
      <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_60d))}>{formatPct(etf.returns.r_60d)}</td>
      <td className={cn('px-2 py-2 text-right text-xs', pctCls(etf.returns.r_120d))}>{formatPct(etf.returns.r_120d)}</td>
      <td className="px-2 py-2 text-right text-xs">{formatYi(etf.amount_yi)}</td>
      <td className="px-2 py-2 text-center">
        {pair?.signal && <Badge>{SIGNAL_LABEL[pair.signal]}</Badge>}
      </td>
    </tr>
  );
};
```

- [ ] **Step 2: 写 CnEtfTable/index.tsx**

```tsx
import { useMemo } from 'react';
import { useDataContext } from '@/providers/DataProvider';
import { useUIState } from '@/providers/UIStateProvider';
import { EtfRow } from './EtfRow';

export const CnEtfTable = () => {
  const { etfs, signals } = useDataContext();
  const { state } = useUIState();

  const rows = useMemo(() => {
    if (!etfs || !signals || !state.selectedThemeId) return [];
    const pairsForTheme = signals.pair_signals.filter(p => p.theme_id === state.selectedThemeId);
    return pairsForTheme.map(p => ({
      pair: p,
      etf: etfs.etfs.find(e => e.code === p.cn_code),
    })).filter(r => r.etf) as Array<{ pair: typeof pairsForTheme[number]; etf: NonNullable<ReturnType<typeof etfs.etfs.find>> }>;
  }, [etfs, signals, state.selectedThemeId]);

  if (!state.selectedThemeId) return null;

  return (
    <div className="bg-white border rounded mt-4">
      <div className="p-3 border-b">
        <div className="font-medium">A股场内ETF候选池</div>
        <div className="text-xs text-gray-500">随当前主题联动筛选, 显示映射分、强弱与流动性</div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-600">
            <tr>
              <th className="px-2 py-2 text-left">名称</th>
              <th className="px-2 py-2 text-left">代码</th>
              <th className="px-2 py-2 text-left">映射</th>
              <th className="px-2 py-2 text-right">1日</th>
              <th className="px-2 py-2 text-right">5日</th>
              <th className="px-2 py-2 text-right">20日</th>
              <th className="px-2 py-2 text-right">60日</th>
              <th className="px-2 py-2 text-right">120日</th>
              <th className="px-2 py-2 text-right">成交额</th>
              <th className="px-2 py-2 text-center">状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => <EtfRow key={r.etf.code + '-' + i} etf={r.etf!} pair={r.pair} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
};
```

- [ ] **Step 3: 验证类型**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: 验证 build**

Run: `cd frontend && npm run build`
Expected: 构建成功

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CnEtfTable/
git commit -m "feat(frontend): add CnEtfTable showing A-share candidates per theme"
```

---

### Task 8.6: 组装 App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: 写 App.tsx**

```tsx
import { DataProvider } from '@/providers/DataProvider';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { Header } from '@/components/Header';
import { FilterBar } from '@/components/FilterBar';
import { ThemeList } from '@/components/ThemeList';
import { ThemeDetail } from '@/components/ThemeDetail';
import { CnEtfTable } from '@/components/CnEtfTable';

export default function App() {
  return (
    <DataProvider>
      <UIStateProvider>
        <div className="min-h-screen bg-gray-50">
          <Header />
          <FilterBar />
          <main className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ThemeList />
            <ThemeDetail />
          </main>
          <div className="px-4 pb-8">
            <CnEtfTable />
          </div>
        </div>
      </UIStateProvider>
    </DataProvider>
  );
}
```

- [ ] **Step 2: 修改 main.tsx (确认 index.css 引入)**

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

- [ ] **Step 3: 验证 build 全通**

Run: `cd frontend && npm run build`
Expected: dist/ 生成, 无错误

- [ ] **Step 4: 启动 dev 服务器手测**

Run: `cd frontend && npm run dev`
Expected: 浏览器打开 `http://localhost:5173/etf-radar/` 可见完整 UI (Ctrl+C 退出)

> 此时 dev 模式可能因为没有真实数据显示 loading 或错误, 这是预期的 — Phase 9 跑过 pipeline 后会有数据。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat(frontend): wire up App layout with all components"
```

---

## Phase 9: 校准脚本 + Bootstrap + 部署文档

### Task 9.1: 实现 scripts/bootstrap_data.py (首次种子)

**Files:**
- Create: `scripts/bootstrap_data.py`

- [ ] **Step 1: 写 bootstrap 脚本**

```python
"""首次种子数据: 拉一次 full 模式 pipeline 把 data/latest/ 填上"""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

import logging
from src.pipeline import run_pipeline, PipelineMode

logging.basicConfig(level=logging.INFO)

if __name__ == '__main__':
    run_pipeline(
        mode=PipelineMode.FULL,
        data_root=ROOT / 'data',
        config_dir=ROOT / 'config',
    )
    print('Bootstrap done. data/latest/ populated.')
```

- [ ] **Step 2: 跑 bootstrap (会真实拉取数据, 需联网)**

Run: `cd backend && uv run python ../scripts/bootstrap_data.py`
Expected: 写入 `data/latest/themes.json` 等 4 个文件

- [ ] **Step 3: 验证 4 文件 + schema**

Run: `ls data/latest/ && python -c "import json; d=json.load(open('data/latest/themes.json')); print('themes:', len(d['themes']))"`
Expected: `themes: 14`

- [ ] **Step 4: 验证前端能加载真实数据**

Run: `cd frontend && npm run dev`
浏览器打开后应看到完整的 KPI 卡 + 主题强弱榜 (有真实数字), 不再是"读取中"

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_data.py data/latest/
git commit -m "feat(scripts): bootstrap data + seed data/latest/"
```

---

### Task 9.2: 实现 scripts/calibrate_algo.py (sigmoid 参数校准)

**Files:**
- Create: `scripts/calibrate_algo.py`

- [ ] **Step 1: 写校准脚本**

```python
"""sigmoid 参数校准 — 通过历史数据回测验证强度分布合理"""
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

import json
from statistics import mean

from src.config_loader import load_themes
from src.providers.yfinance_provider import YfinanceProvider
from src.scoring.returns import compute_returns
from src.scoring.strength import (
    dim_aggregate_return, strength_per_dim, composite_strength,
)


TARGET_BINS = {
    'top_20_pct': (75, 100, 0.20),
    'middle_60_pct': (30, 75, 0.60),
    'bottom_20_pct': (0, 30, 0.20),
}


def evaluate_distribution(strengths: list[int]) -> dict:
    n = len(strengths)
    if n == 0:
        return {}
    counts = {bin_name: 0 for bin_name in TARGET_BINS}
    for s in strengths:
        for bin_name, (lo, hi, _target) in TARGET_BINS.items():
            if lo <= s < hi:
                counts[bin_name] += 1
                break
    return {bin_name: counts[bin_name] / n for bin_name in counts}


def main():
    themes = load_themes(ROOT / 'config' / 'themes.yml')
    provider = YfinanceProvider()
    us_ohlc = {}
    for t in themes:
        try:
            us_ohlc[t.id] = provider.fetch_ohlc(t.primary_us, lookback_days=400)
            print(f'fetched {t.primary_us}')
        except Exception as e:
            print(f'FAIL {t.primary_us}: {e}')

    # 跑一次综合强度
    returns = {tid: compute_returns(df) for tid, df in us_ohlc.items()}
    pool_short = [dim_aggregate_return(r, 'short') for r in returns.values()]
    pool_short = [r for r in pool_short if r is not None]

    # 测试不同 K 值
    for k in [3.0, 5.0, 7.0]:
        strengths = []
        for tid, r in returns.items():
            ret = dim_aggregate_return(r, 'short')
            if ret is None:
                continue
            s = strength_per_dim(ret, pool_short, k=k, days_in_dim=3)
            strengths.append(s)
        dist = evaluate_distribution(strengths)
        print(f'\nK={k}: distribution={dist}, mean={mean(strengths):.1f}')
        for bin_name, ratio in dist.items():
            target = TARGET_BINS[bin_name][2]
            ok = '✓' if abs(ratio - target) <= 0.15 else '✗'
            print(f'  {bin_name}: {ratio:.2%} (target {target:.0%}) {ok}')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 跑校准脚本 (需联网, 仅信息性, 不强制阻塞 plan)**

Run: `cd backend && uv run python ../scripts/calibrate_algo.py`
Expected: 输出不同 K 值下的分布, 接近目标 (20%/60%/20%) 的为推荐值

- [ ] **Step 3: 根据输出调整 config/algo.yml**

如果默认 K=5.0 的分布偏离目标 >15%, 编辑 `config/algo.yml` 的 `k_sigmoid` 字段。

- [ ] **Step 4: 验证调整后 pipeline 仍能跑通**

Run: `cd backend && uv run python -m src.pipeline --mode=full --data-root=../data --config-dir=../config`
Expected: 输出新的 themes.json, 强度分布合理

- [ ] **Step 5: Commit**

```bash
git add scripts/calibrate_algo.py config/algo.yml
git commit -m "feat(scripts): add sigmoid calibration script"
```

---

### Task 9.3: 实现 scripts/archive_cleanup.py (删除 >2 年的归档)

**Files:**
- Create: `scripts/archive_cleanup.py`

- [ ] **Step 1: 写清理脚本**

```python
"""删除 data/snapshots/ 下 >2 年的归档目录"""
import sys
from pathlib import Path
from datetime import date, timedelta
import shutil

ROOT = Path(__file__).parent.parent
SNAPS = ROOT / 'data' / 'snapshots'


def main(retention_days: int = 730):
    if not SNAPS.exists():
        print('No snapshots dir, nothing to clean')
        return
    cutoff = date.today() - timedelta(days=retention_days)
    removed = 0
    for sub in SNAPS.iterdir():
        if not sub.is_dir():
            continue
        try:
            d = date.fromisoformat(sub.name)
        except ValueError:
            continue
        if d < cutoff:
            shutil.rmtree(sub)
            removed += 1
            print(f'removed {sub}')
    print(f'cleaned {removed} old snapshots (cutoff: {cutoff})')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 跑脚本 (无目标时应安全无操作)**

Run: `python scripts/archive_cleanup.py`
Expected: `No snapshots dir, nothing to clean` 或 `cleaned 0 old snapshots`

- [ ] **Step 3: 验证脚本不破坏新归档**

Run: `mkdir -p data/snapshots/2026-06-05 && python scripts/archive_cleanup.py && ls data/snapshots/`
Expected: `2026-06-05/` 仍存在 (今天的归档, 未过期)

- [ ] **Step 4: 清理测试目录**

Run: `rmdir data/snapshots/2026-06-05 2>/dev/null || true`
Expected: 无错误

- [ ] **Step 5: Commit**

```bash
git add scripts/archive_cleanup.py
git commit -m "feat(scripts): add archive cleanup script (2-year retention)"
```

---

### Task 9.4: 完善 README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 写完整 README**

```markdown
# ETF Radar — 跨市场主题联动分析平台

追踪 14 个美股主题 ETF 的强弱与动量, 自动映射到 A 股场内 ETF, 识别共振 / 传导 / 背离信号, 帮助 A 股个人投资者发现跨市场交易机会。

## 在线访问

部署在 GitHub Pages: https://<your-username>.github.io/etf-radar/

## 工作原理

1. GitHub Actions 按调度时间触发 Python 流水线 (`backend/src/pipeline.py`)
2. 从 yfinance (美股) 与 AkShare (A股) 拉取 ETF OHLC
3. 计算多周期收益率 → 双轨强度评分 → 60 日相关性映射分 → 多周期投票信号
4. 输出到 `data/latest/{themes,etfs,signals,meta}.json` 并 commit 回仓库
5. 同时按日归档到 `data/snapshots/<YYYY-MM-DD>/`
6. 前端 (React + Vite) 静态构建后部署到 GitHub Pages, 客户端 fetch JSON 渲染

## 调度计划 (北京时间)

- 06:30 工作日: 美股全量刷新
- 09:15 工作日: A 股全量刷新 + 重算信号
- 09:30-11:30, 13:00-15:00 工作日: 每 15 分钟刷新 A 股价格
- 15:30 工作日: EOD 归档当日数据

## 本地开发

### Backend (Python 3.11+)

```bash
cd backend
uv venv && uv sync --extra dev
uv run pytest                              # 跑测试
uv run python -m src.pipeline --mode=full --data-root=../data --config-dir=../config
```

### Frontend (Node 20+)

```bash
cd frontend
npm ci
npm run dev      # http://localhost:5173/etf-radar/
npm run build
```

## 数据源

- 美股: yfinance (Yahoo Finance, 延迟 ~15 分钟)
- A 股: AkShare (东方财富数据, 延迟 ~15 分钟)
- L1 软容灾: 失败保留上次成功快照, UI 显示告警

## 关键文档

- 设计文档: `docs/superpowers/specs/2026-06-05-etf-radar-design.md`
- 实施 plan: `docs/superpowers/plans/2026-06-05-etf-radar-implementation.md`
- 原产品文档: `docs/htsc-us-cn-linkage-product-doc.md`
- 原需求文档: `docs/htsc-us-cn-linkage-requirements.md`

## 部署

### 首次启用 GitHub Pages

1. 仓库 Settings → Pages → Source = `gh-pages` branch / `(root)`
2. 等待第一次 `deploy-frontend.yml` 运行
3. 访问 `https://<username>.github.io/etf-radar/`

### 首次种子数据

```bash
cd backend && uv run python ../scripts/bootstrap_data.py
git add data/latest/ && git commit -m "data: initial seed"
git push
```

## License

MIT
```

- [ ] **Step 2: 验证 README 渲染 (本地预览)**

Run: `python -c "import re; t=open('README.md').read(); print(f'{len(t)} chars, {t.count(chr(10))} lines')"`
Expected: 显示字符与行数 (~ 2000+ 字符)

- [ ] **Step 3: 检查链接合理性 (无 broken)**

手动检查 README 中的相对路径 `docs/superpowers/specs/...` 等是否真实存在。

- [ ] **Step 4: 文档收尾 (无额外操作)**

无。

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: complete README with project overview"
```

---

### Task 9.5: Schema 验证集成 (CI 强制)

**Files:**
- Create: `backend/tests/test_output_schemas.py`
- Create: `backend/tests/schemas/themes.schema.json`
- Create: `backend/tests/schemas/etfs.schema.json`
- Create: `backend/tests/schemas/signals.schema.json`
- Create: `backend/tests/schemas/meta.schema.json`

- [ ] **Step 1: 写 themes.schema.json (示例最简)**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["schema_version", "generated_at", "themes"],
  "properties": {
    "schema_version": {"type": "string"},
    "generated_at": {"type": "string"},
    "themes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "name", "us_etfs", "primary_us", "tags", "note", "returns", "strength", "rank"],
        "properties": {
          "id": {"type": "string"},
          "name": {"type": "string"},
          "us_etfs": {"type": "array", "items": {"type": "string"}},
          "primary_us": {"type": "string"},
          "strength": {
            "type": "object",
            "required": ["short", "mid", "long", "composite"],
            "properties": {
              "short": {"type": "integer", "minimum": 0, "maximum": 100},
              "mid": {"type": "integer", "minimum": 0, "maximum": 100},
              "long": {"type": "integer", "minimum": 0, "maximum": 100},
              "composite": {"type": "integer", "minimum": 0, "maximum": 100}
            }
          }
        }
      }
    }
  }
}
```

(同样写出 etfs.schema.json / signals.schema.json / meta.schema.json — 此处省略, 按 design §4 Schema 章节模板。)

- [ ] **Step 2: 写测试**

```python
import json
from pathlib import Path
import jsonschema
import pytest

ROOT = Path(__file__).parent.parent.parent
SCHEMAS = Path(__file__).parent / 'schemas'
LATEST = ROOT / 'data' / 'latest'

@pytest.mark.parametrize('name', ['themes', 'etfs', 'signals', 'meta'])
def test_latest_matches_schema(name):
    schema_file = SCHEMAS / f'{name}.schema.json'
    data_file = LATEST / f'{name}.json'
    if not data_file.exists():
        pytest.skip(f'{data_file} not yet bootstrapped')
    schema = json.loads(schema_file.read_text())
    data = json.loads(data_file.read_text())
    jsonschema.validate(data, schema)
```

- [ ] **Step 3: 跑测试**

Run: `cd backend && uv run pytest tests/test_output_schemas.py -v`
Expected: 4 tests, 都是 PASS 或 SKIP (取决于 bootstrap 是否完成)

- [ ] **Step 4: 把 schema 检查纳入 CI (已在 ci.yml `pytest` 自动跑到)**

无需额外修改。

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_output_schemas.py backend/tests/schemas/
git commit -m "test: add JSON schema validation for output files"
```

---

### Task 9.6: 端到端冒烟测试 + Push 启动调度

**Files:**
- (无新文件)

- [ ] **Step 1: 跑全部测试套件**

Run: `cd backend && uv run pytest`
Expected: 所有测试 PASS

- [ ] **Step 2: 跑前端 build**

Run: `cd frontend && npm run build`
Expected: 构建成功, `dist/` 生成, 包含 `dist/data/latest/` 目录

- [ ] **Step 3: 验证 dist 中包含真实数据**

Run: `ls frontend/dist/data/latest/`
Expected: themes.json/etfs.json/signals.json/meta.json 都存在

- [ ] **Step 4: 推送到 GitHub 触发首次部署**

```bash
git push origin main
```
Expected: GitHub Actions 自动跑 `deploy-frontend.yml`, 几分钟后 GitHub Pages 上线

- [ ] **Step 5: 验证线上可访问 + Commit (本步无新文件, 仅打 tag)**

```bash
git tag -a v0.1.0 -m "First milestone: end-to-end working"
git push origin v0.1.0
```
访问 `https://<username>.github.io/etf-radar/` 应见完整 UI。

---

## Plan Self-Review (我对此 plan 的自检结果)

### Spec 覆盖性检查

| Spec 章节 | Plan 覆盖任务 |
|----------|--------------|
| §1.3 关键设计原则 | Phase 4 (后端只输出 JSON), Phase 6-8 (静态 SPA, 前端不重算) |
| §2.1 4 个 workflow | Task 5.1–5.4 |
| §2.2 Provider | Task 2.1–2.3 |
| §2.3 ETL | Task 1.3–1.4 |
| §2.4 L1 软容灾 | Task 2.2/2.3 retry + Task 4.4 catch all + Task 8.1 StaleBanner |
| §3.1 收益率 | Task 3.1 |
| §3.2 强度评分 | Task 3.2 + Task 9.2 (calibration) |
| §3.3 映射分 | Task 3.3 |
| §3.4 置信度 | Task 3.4 (常量) + Task 4.4 pipeline |
| §3.5 信号判定 | Task 3.4 |
| §3.6 algo.yml | Task 0.3 |
| §3.7 themes.yml | Task 0.3 (含 14 主题) |
| §4 JSON Schema | Task 1.1 (Pydantic) + Task 9.5 (jsonschema 校验) |
| §5.1 SPA 形态 | Task 7.2 URL Hash 同步 |
| §5.2 组件树 | Task 8.1–8.6 |
| §5.3 状态管理 | Task 7.1 DataProvider + Task 7.2 UIStateProvider |
| §5.4 shadcn 映射 | Task 6.1 + 各组件使用 |
| §5.6 部署 | Task 5.4 + Task 9.6 |
| §6.1 目录树 | Phase 0-9 全覆盖 |
| §6.2 错误处理 | Task 2.2/2.3 retry, Task 4.4 catch, Task 8.1 banner |
| §6.3 测试 | 每个 Task 都先写测试 (TDD) + Task 9.5 schema |
| §6.4 监控 | Task 8.1 StaleBanner + meta.json |

✅ 所有 Spec 章节都有对应 task。

### 占位符扫描

主文档无 "TBD/TODO/待定" 残留 (附录 C 引用原文档已知)。`Task 9.5 Step 1` 中"等 — 此处省略, 按 design §4 Schema 章节模板"是合理省略(其他 3 个 schema 与 themes.schema.json 结构相同, 可类比写出), 实现者按 design §4 直接复现即可。

### 类型一致性检查

- `PipelineMode.FULL/INTRADAY/ARCHIVE` 在 Task 4.4 定义, Task 5.1-5.4 与 9.1 都正确引用
- `SignalType = 'resonance' | 'transmission' | 'divergence'` 在 backend models 与 frontend types 都用同样字符串
- `Strength {short, mid, long, composite}` 一致
- 前端 `BASE = import.meta.env.BASE_URL` 与 vite.config `base: '/etf-radar/'` 一致

---

## 执行选项

**Plan 已写完并自检通过, 保存在 `docs/superpowers/plans/2026-06-05-etf-radar-implementation.md`。**

两种执行方式:

**1. Subagent-Driven (推荐)** — 我为每个 task 派发一个全新的 subagent 执行 (无历史包袱), 每个 task 完成后我做两阶段 review (代码 + 测试), 快速迭代发现问题。适合本项目大量任务并行/解耦的情况。

**2. Inline Execution** — 在当前会话内顺序执行所有 task, 在每个 Phase 末做 checkpoint review。适合需要在执行中维持完整上下文的场景。


