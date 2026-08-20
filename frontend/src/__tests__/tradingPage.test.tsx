import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/hooks/useTrading', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/useTrading')>();
  return { ...actual, useTrading: vi.fn() };
});
vi.mock('@/lib/subscription/useSubscription', () => ({ useSubscription: vi.fn() }));

import { useTrading } from '@/hooks/useTrading';
import { useSubscription } from '@/lib/subscription/useSubscription';
import { AuthContext } from '@/providers/authContext';
import { TradingPage } from '@/pages/TradingPage';
import { TradingSchema } from '@/types/trading';
import { calcPosition } from '@/components/trading/PositionCalculator';

// ── 夹具 (spec §2.3 样例) ─────────────────────────────────────────────

const mkIndex = (code: string, name: string, template_pass: number) => ({
  code,
  name,
  template_pass,
  criteria: [true, false, true, true, true, true, false, true],
  close: 3456.78,
});

const mkCandidate = (over: Record<string, unknown> = {}) => ({
  code: '600519',
  name: '贵州茅台',
  composite_score: 7.2,
  stage: 2,
  template_pass: 7,
  rs_pct: 85.0,
  vcp: { contractions: 3, depth_pct: 22.5, quality: 0.72, volume_dryup: true },
  pivot: 1710.0,
  buy_zone_low: 1710.0,
  buy_zone_high: 1795.5,
  stop: 1573.2,
  state: 'in_buy_zone',
  limit_up_unexecutable: false,
  chg_pct: -2.1,
  board: 'main',
  vol_forecast_ann: null,
  ...over,
});

const mkTrading = (over: Record<string, unknown> = {}) => ({
  schema_version: '1.0',
  generated_at: '2026-08-20T09:00:00+08:00',
  environment: {
    regime: 'offense',
    indices: [
      mkIndex('000300', '沪深300', 6),
      mkIndex('000905', '中证500', 7),
      mkIndex('399006', '创业板指', 3),
    ],
    breadth: { ma20_pct: 0.62, ma60_pct: 0.55, ma120_pct: 0.48, source: 'market_temperature.json' },
    source_status: { indices: 'ok', rs_benchmark: 'ok' },
  },
  candidates: [
    mkCandidate(),
    mkCandidate({
      code: '300750', name: '宁德时代', composite_score: 8.1, state: 'near_buy_zone',
      limit_up_unexecutable: true, chg_pct: 1.5,
    }),
    mkCandidate({
      code: '688981', name: null, composite_score: null, stage: null, template_pass: null,
      state: 'watch', vcp: null, buy_zone_low: null, buy_zone_high: null, chg_pct: null,
    }),
    mkCandidate({
      code: '000001', name: '平安银行', state: null,
      vcp: { contractions: 2, depth_pct: 18.0, quality: 0.6, volume_dryup: false },
      buy_zone_low: 1700.0, buy_zone_high: 1785.0,
    }),
  ],
  universe_stats: { total: 5552, tradable: 3200, stage2: 410, vcp: 78, top: 50 },
  ...over,
});

// ── 渲染 helper (member 态, 同 GridPage 模式) ──────────────────────────

const renderTrading = (hookOverrides: Record<string, unknown> = {}) => {
  vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
  vi.mocked(useTrading).mockReturnValue({
    data: mkTrading(),
    error: undefined,
    isLoading: false,
    ...hookOverrides,
  } as never);
  render(
    <MemoryRouter>
      <AuthContext.Provider value={{ status: 'authenticated', user: { email: 'a@b.com' } } as never}>
        <TradingPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
};

const clickTab = (label: string) => {
  fireEvent.click(screen.getByRole('tab', { name: new RegExp(label) }));
};

// ── zod schema (types/trading.ts 声明行需 parse 执行产生 DA) ───────────

describe('TradingSchema', () => {
  it('完整产物 parse 成功', () => {
    const t = TradingSchema.parse(mkTrading());
    expect(t.environment?.regime).toBe('offense');
    expect(t.environment?.indices).toHaveLength(3);
    expect(t.candidates).toHaveLength(4);
    expect(t.candidates[0]?.state).toBe('in_buy_zone');
    expect(t.candidates[0]?.vcp?.contractions).toBe(3);
    expect(t.universe_stats?.top).toBe(50);
  });

  it('数值字段 null 降级保留为 null', () => {
    const t = TradingSchema.parse(mkTrading({
      candidates: [mkCandidate({
        composite_score: null, stage: null, template_pass: null, rs_pct: null,
        pivot: null, buy_zone_low: null, buy_zone_high: null, stop: null,
        chg_pct: null, board: null, vol_forecast_ann: null, limit_up_unexecutable: null,
      })],
    }));
    const c = t.candidates[0]!;
    expect(c.composite_score).toBeNull();
    expect(c.stage).toBeNull();
    expect(c.rs_pct).toBeNull();
    expect(c.limit_up_unexecutable).toBeNull();
    expect(c.chg_pct).toBeNull();
  });

  it('environment/breadth/vcp/universe_stats 缺省或 null 转 null, 数组缺省转空', () => {
    const minimal = TradingSchema.parse({ schema_version: '1.0', generated_at: 't' });
    expect(minimal.environment).toBeNull();
    expect(minimal.candidates).toEqual([]);
    expect(minimal.universe_stats).toBeNull();

    const t = TradingSchema.parse(mkTrading({
      environment: {
        // 不带 criteria 字段: 验证 z.array().default([]) 缺省分支
        regime: null, indices: [{ code: '000300', name: '沪深300', template_pass: 6, close: 3456.78 }],
        breadth: null, source_status: {},
      },
      universe_stats: null,
    }));
    expect(t.environment?.regime).toBeNull();
    expect(t.environment?.indices[0]?.criteria).toEqual([]);
    expect(t.environment?.breadth).toBeNull();
    expect(t.universe_stats).toBeNull();
  });
});

// ── 页壳 + 环境 Tab ──────────────────────────────────────────────────

describe('TradingPage 页壳与环境 Tab', () => {
  it('渲染四 Tab 按钮, 默认环境 Tab 免费展示档位/指数/宽度', () => {
    renderTrading();
    for (const label of ['环境', '信号', '持仓', '复盘']) {
      expect(screen.getByRole('tab', { name: new RegExp(label) })).toBeInTheDocument();
    }
    expect(screen.getByText('进攻')).toBeInTheDocument();
    expect(screen.getByText('6/8')).toBeInTheDocument();
    expect(screen.getByText('沪深300')).toBeInTheDocument();
    expect(screen.getByText('+62.0%')).toBeInTheDocument();
  });

  it('宽度佐证展示 as_of 时点与陈旧标记 (与温度页对数可判断快照新旧)', () => {
    const data = mkTrading();
    (data.environment as { breadth: Record<string, unknown> }).breadth = {
      ...mkTrading().environment.breadth!,
      as_of: '2026-08-19',
      stale: false,
    };
    renderTrading({ data });
    expect(screen.getByText(/截至 2026-08-19/)).toBeInTheDocument();
    expect(screen.queryByText(/数据陈旧/)).toBeNull();
    const staleData = mkTrading();
    (staleData.environment as { breadth: Record<string, unknown> }).breadth = {
      ...staleData.environment.breadth!,
      as_of: '2026-08-10',
      stale: true,
    };
    renderTrading({ data: staleData });
    expect(screen.getByText(/数据陈旧/)).toBeInTheDocument();
  });

  it('regime null 显示数据缺失徽标, breadth null 显示 —', () => {
    const data = mkTrading();
    (data.environment as Record<string, unknown>).regime = null;
    (data.environment as Record<string, unknown>).breadth = null;
    renderTrading({ data });
    expect(screen.getByText('数据缺失')).toBeInTheDocument();
    expect(screen.queryByText('+62.0%')).toBeNull();
  });

  it('指数 name/template_pass/close null 时降级为 — (code 兜底)', () => {
    const data = mkTrading();
    (data.environment as { indices: unknown[] }).indices = [
      { code: '999999', name: null, template_pass: null, criteria: [], close: null },
    ];
    renderTrading({ data });
    expect(screen.getByRole('list', { name: '999999 趋势模板 8 条件' })).toBeInTheDocument();
    // 该夹具下 name 兜底为 code、pass/close 降级: 页面仅此两处 —
    expect(screen.getAllByText('—')).toHaveLength(2);
  });

  it('RS 基准缺失显示事实性降级提示', () => {
    const data = mkTrading();
    (data.environment as { source_status: Record<string, string> }).source_status = {
      indices: 'ok', rs_benchmark: 'missing',
    };
    renderTrading({ data });
    expect(screen.getByText(/RS 基准（中证全指 000985）当日数据缺失/)).toBeInTheDocument();
  });

  it('loading 显示骨架', () => {
    renderTrading({ isLoading: true, data: undefined });
    expect(screen.queryByText('进攻')).toBeNull();
    expect(screen.getByLabelText('加载中')).toBeInTheDocument();
  });

  it('error 与 environment 缺失显示占位', () => {
    renderTrading({ error: new Error('x'), data: undefined });
    expect(screen.getByText('暂无交易环境数据')).toBeInTheDocument();
  });

  it('data 存在但 environment 为 null 显示占位', () => {
    renderTrading({ data: mkTrading({ environment: null }) });
    expect(screen.getByText('暂无交易环境数据')).toBeInTheDocument();
  });
});

// ── 信号 Tab ─────────────────────────────────────────────────────────

describe('TradingPage 信号 Tab', () => {
  it('候选表按综合分降序渲染, 含状态文案与涨停一字标记', () => {
    renderTrading();
    clickTab('信号');
    const rows = screen.getAllByRole('row');
    expect(rows[1]?.textContent).toContain('300750'); // 8.1 分在前
    expect(rows[2]?.textContent).toContain('600519');
    expect(rows[3]?.textContent).toContain('000001'); // 同为 7.2 分, 稳定排序保持原序
    expect(rows[4]?.textContent).toContain('688981'); // null 分垫底
    expect(screen.getByText('已进入买区')).toBeInTheDocument();
    expect(screen.getByText('接近买点')).toBeInTheDocument();
    expect(screen.getByText('底部观察')).toBeInTheDocument();
    expect(screen.getByText('涨停一字')).toBeInTheDocument();
    expect(screen.getAllByText('3次/22.5%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('1710.0~1795.5').length).toBeGreaterThan(0);
  });

  it('null 字段渲染 — (综合分/VCP/买区/状态)', () => {
    renderTrading();
    clickTab('信号');
    const rows = screen.getAllByRole('row');
    expect(rows[4]?.textContent).not.toContain('次/'); // vcp null (688981)
    expect(rows[4]?.textContent).not.toContain('~'); // 买区 null
    expect(rows[4]?.textContent).not.toContain('S2'); // stage null → '—'
    expect(rows[3]?.textContent).not.toContain('底部观察'); // state null → '—' (000001)
    expect(rows[3]?.textContent).toContain('—');
  });

  it('defense 档显示事实性冻结提示条', () => {
    const data = mkTrading();
    (data.environment as Record<string, unknown>).regime = 'defense';
    renderTrading({ data });
    clickTab('信号');
    expect(screen.getByText(/防守档不输出买区相关状态/)).toBeInTheDocument();
  });

  it('候选池为空显示空态', () => {
    renderTrading({ data: mkTrading({ candidates: [] }) });
    clickTab('信号');
    expect(screen.getByText('今日候选池为空')).toBeInTheDocument();
  });

  it('loading 骨架与 error 占位', () => {
    renderTrading({ isLoading: true, data: undefined });
    clickTab('信号');
    expect(screen.queryByText('贵州茅台')).toBeNull();
    cleanup();
    renderTrading({ error: new Error('x'), data: undefined });
    clickTab('信号');
    expect(screen.getByText('暂无交易信号数据')).toBeInTheDocument();
  });
});

// ── 持仓 / 复盘占位 Tab ──────────────────────────────────────────────

describe('TradingPage 持仓/复盘占位', () => {
  it('member 态点持仓/复盘显示接线占位', () => {
    renderTrading();
    clickTab('持仓');
    expect(screen.getByText(/持仓管理建设中/)).toBeInTheDocument();
    clickTab('复盘');
    expect(screen.getByText(/交易复盘建设中/)).toBeInTheDocument();
  });
});

// ── 仓位计算器 ───────────────────────────────────────────────────────

describe('calcPosition 纯函数', () => {
  it('风险预算口径约束时取风险股数', () => {
    const r = calcPosition({ equity: 100000, entry: 17.1, stop: 15.73, riskPct: 0.75, maxPositionPct: 20 });
    expect(r).not.toBeNull();
    expect(r!.riskAmount).toBeCloseTo(750, 6);
    expect(r!.perShareRisk).toBeCloseTo(1.37, 6);
    expect(r!.sharesByRisk).toBe(547);
    expect(r!.sharesByCap).toBe(1169);
    expect(r!.shares).toBe(547);
    expect(r!.binding).toBe('risk');
    expect(r!.positionPct).toBeCloseTo((547 * 17.1 / 100000) * 100, 6);
  });

  it('市值上限口径约束时取上限股数', () => {
    const r = calcPosition({ equity: 100000, entry: 500, stop: 495, riskPct: 0.75, maxPositionPct: 20 });
    expect(r!.sharesByRisk).toBe(150);
    expect(r!.sharesByCap).toBe(40);
    expect(r!.shares).toBe(40);
    expect(r!.binding).toBe('cap');
  });

  it('非正输入与入场≤止损返回 null', () => {
    expect(calcPosition({ equity: 0, entry: 10, stop: 9, riskPct: 0.75, maxPositionPct: 20 })).toBeNull();
    expect(calcPosition({ equity: 100000, entry: 9, stop: 10, riskPct: 0.75, maxPositionPct: 20 })).toBeNull();
    expect(calcPosition({ equity: 100000, entry: 10, stop: 10, riskPct: 0.75, maxPositionPct: 20 })).toBeNull();
    expect(calcPosition({ equity: 100000, entry: 10, stop: 9, riskPct: 0, maxPositionPct: 20 })).toBeNull();
  });
});

describe('PositionCalculator UI (信号 Tab 内)', () => {
  const fillInputs = () => {
    fireEvent.change(screen.getByPlaceholderText('100000'), { target: { value: '100000' } });
    fireEvent.change(screen.getByPlaceholderText('17.10'), { target: { value: '17.1' } });
    fireEvent.change(screen.getByPlaceholderText('15.73'), { target: { value: '15.73' } });
  };

  it('初始态提示输入', () => {
    renderTrading();
    clickTab('信号');
    expect(screen.getByText(/输入权益、入场价、止损价后显示计算结果/)).toBeInTheDocument();
    expect(screen.getByText(/当前环境档位为进攻/)).toBeInTheDocument();
  });

  it('输入三值输出风险预算股数与口径对照', () => {
    renderTrading();
    clickTab('信号');
    fillInputs();
    expect(screen.getByText('547 股')).toBeInTheDocument();
    expect(screen.getByText(/受风险预算约束/)).toBeInTheDocument();
    expect(screen.getByText(/风险预算 547 股/)).toBeInTheDocument();
    expect(screen.getByText(/市值上限 1169 股/)).toBeInTheDocument();
  });

  it('入场价低于止损价显示方向无效提示', () => {
    renderTrading();
    clickTab('信号');
    fireEvent.change(screen.getByPlaceholderText('100000'), { target: { value: '100000' } });
    fireEvent.change(screen.getByPlaceholderText('17.10'), { target: { value: '15' } });
    fireEvent.change(screen.getByPlaceholderText('15.73'), { target: { value: '17' } });
    expect(screen.getByText(/入场价不高于止损价/)).toBeInTheDocument();
  });

  it('部分非法输入显示有效性提示', () => {
    renderTrading();
    clickTab('信号');
    fireEvent.change(screen.getByPlaceholderText('100000'), { target: { value: 'abc' } });
    expect(screen.getByText(/请输入有效的正数/)).toBeInTheDocument();
  });

  it('regime 缺失时计算器提示数据缺失口径', () => {
    const data = mkTrading();
    (data.environment as Record<string, unknown>).regime = null;
    renderTrading({ data });
    clickTab('信号');
    expect(screen.getByText(/环境档位数据缺失/)).toBeInTheDocument();
  });

  it('参数可改: 市值上限收紧触发 cap 约束, 风险参数放大风险股数', () => {
    renderTrading();
    clickTab('信号');
    fillInputs();
    expect(screen.getByText('547 股')).toBeInTheDocument(); // 默认 risk 口径
    // 市值上限 20% → 1%: cap = floor(1000/17.1) = 58 股
    fireEvent.change(screen.getByDisplayValue('20'), { target: { value: '1' } });
    expect(screen.getByText(/受市值上限约束/)).toBeInTheDocument();
    expect(screen.getByText('58 股')).toBeInTheDocument();
    // 单笔风险 0.75% → 1.5%: 风险股数 1094, 仍受 cap 58 约束
    fireEvent.change(screen.getByDisplayValue('0.75'), { target: { value: '1.5' } });
    expect(screen.getByText(/风险预算 1094 股/)).toBeInTheDocument();
    expect(screen.getByText('58 股')).toBeInTheDocument();
  });

  it('neutral 档附减半口径对照, defense 档提示无操作含义', () => {
    const neutral = mkTrading();
    (neutral.environment as Record<string, unknown>).regime = 'neutral';
    renderTrading({ data: neutral });
    clickTab('信号');
    fillInputs();
    expect(screen.getByText(/中性档减半口径（单笔风险 ×0.5）：273 股/)).toBeInTheDocument();

    cleanup();
    const defense = mkTrading();
    (defense.environment as Record<string, unknown>).regime = 'defense';
    renderTrading({ data: defense });
    clickTab('信号');
    expect(screen.getByText(/以下仅为算术计算展示/)).toBeInTheDocument();
  });
});

// ── useTrading 真实 fetcher (hook 文件覆盖) ──────────────────────────

describe('useTrading fetcher', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  const renderProbe = async () => {
    const actual = await vi.importActual<typeof import('@/hooks/useTrading')>('@/hooks/useTrading');
    const Probe = () => {
      const { data, error } = actual.useTrading();
      return <div>{data ? (data.environment?.regime ?? 'no-env') : error ? 'err' : 'loading'}</div>;
    };
    render(<MemoryRouter><Probe /></MemoryRouter>);
  };

  it('404 时进入 error 状态', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await renderProbe();
    await waitFor(() => expect(screen.getByText('err')).toBeInTheDocument());
  });

  it('200 时 parse 并返回数据', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => mkTrading() }));
    await renderProbe();
    await waitFor(() => expect(screen.getByText('offense')).toBeInTheDocument());
  });
});
