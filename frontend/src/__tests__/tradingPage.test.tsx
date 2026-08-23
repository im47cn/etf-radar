import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';

vi.mock('@/hooks/useTrading', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/useTrading')>();
  return { ...actual, useTrading: vi.fn() };
});
vi.mock('@/lib/subscription/useSubscription', () => ({ useSubscription: vi.fn() }));
vi.mock('@/hooks/useTrades', () => ({ useTrades: vi.fn() }));
vi.mock('@/lib/trading/api', () => ({ listReviews: vi.fn(), getReviewAggregates: vi.fn() }));

// 自选/主题持仓 Tab 接线测试的页面 stub（gate 行为由两页面各自既有测试背书）
vi.mock('@/pages/WatchlistPage', () => ({ WatchlistPage: () => <div>watchlist-page-marker</div> }));
vi.mock('@/pages/PortfolioPage', () => ({ PortfolioPage: () => <div>portfolio-page-marker</div> }));

import { useTrading } from '@/hooks/useTrading';
import { useSubscription } from '@/lib/subscription/useSubscription';
import { useTrades } from '@/hooks/useTrades';
import { getReviewAggregates, listReviews } from '@/lib/trading/api';
import { AuthContext } from '@/providers/authContext';
import { TradingPage } from '@/pages/TradingPage';
import { TradingSchema } from '@/types/trading';
import { calcPosition } from '@/components/trading/PositionCalculator';
import { DEFAULT_SETTINGS_VALUES, type TradeReview } from '@/lib/trading/types';

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

const setupMocks = (
  hookOverrides: Record<string, unknown> = {},
  tradesOverrides: Record<string, unknown> = {},
  reviews: TradeReview[] = [],
) => {
  vi.mocked(useSubscription).mockReturnValue({ state: 'member' } as never);
  vi.mocked(useTrading).mockReturnValue({
    data: mkTrading(),
    error: undefined,
    isLoading: false,
    ...hookOverrides,
  } as never);
  vi.mocked(useTrades).mockReturnValue({
    trades: [],
    positions: [],
    settings: { user_id: '', updated_at: '', ...DEFAULT_SETTINGS_VALUES },
    loading: false,
    error: null,
    addTrade: vi.fn(),
    removeTrade: vi.fn(),
    updateSettings: vi.fn(),
    refresh: vi.fn(),
    ...tradesOverrides,
  } as never);
  vi.mocked(listReviews).mockReset().mockResolvedValue(reviews);
  vi.mocked(getReviewAggregates).mockReset().mockResolvedValue(null);
};

const renderTrading = (
  hookOverrides: Record<string, unknown> = {},
  tradesOverrides: Record<string, unknown> = {},
  reviews: TradeReview[] = [],
  initialEntries: string[] = ['/trading'],
) => {
  setupMocks(hookOverrides, tradesOverrides, reviews);
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <AuthContext.Provider value={{ status: 'authenticated', user: { email: 'a@b.com' } } as never}>
        <TradingPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
};

const clickTab = (label: string) => {
  // 锚定正则: 持仓 与 主题持仓 互为子串, 🔒 span 为 aria-hidden 不计入可访问名
  fireEvent.click(screen.getByRole('tab', { name: new RegExp('^' + label + '$') }));
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
  it('渲染六 Tab 按钮, 免费/开放 tab 无锁、member tab 带锁, 默认环境 Tab 免费展示', () => {
    renderTrading();
    for (const label of ['环境', '信号', '自选', '持仓', '主题持仓', '复盘']) {
      expect(screen.getByRole('tab', { name: new RegExp('^' + label + '$') })).toBeInTheDocument();
    }
    // locked 两分支: 主题持仓为 auth 开放功能不带锁, 其余 member tab 带 🔒
    expect(screen.getByRole('tab', { name: /^环境$/ }).textContent).not.toContain('🔒');
    expect(screen.getByRole('tab', { name: /^主题持仓$/ }).textContent).not.toContain('🔒');
    for (const label of ['信号', '自选', '持仓', '复盘']) {
      expect(screen.getByRole('tab', { name: new RegExp('^' + label + '$') }).textContent).toContain('🔒');
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

// ── 自选/主题持仓 Tab 接线与 URL 参数 ────────────────────────────────

describe('自选/主题持仓 Tab 接线与 URL 参数', () => {
  it('点自选 Tab 渲染 WatchlistPage', () => {
    renderTrading();
    clickTab('自选');
    expect(screen.getByText('watchlist-page-marker')).toBeInTheDocument();
  });

  it('点主题持仓 Tab 渲染 PortfolioPage', () => {
    renderTrading();
    clickTab('主题持仓');
    expect(screen.getByText('portfolio-page-marker')).toBeInTheDocument();
  });

  it('deep-link ?tab=holdings 免点击直达主题持仓', () => {
    renderTrading({}, {}, [], ['/trading?tab=holdings']);
    expect(screen.getByText('portfolio-page-marker')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /^主题持仓$/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('非法 tab 参数回落环境 Tab (isTabKey false 分支)', () => {
    renderTrading({}, {}, [], ['/trading?tab=xyz']);
    expect(screen.getByRole('tab', { name: /^环境$/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('进攻')).toBeInTheDocument();
  });

  it('点自选后 location.search 更新为 ?tab=watchlist', () => {
    const searches: string[] = [];
    const Probe = () => {
      searches.push(useLocation().search);
      return null;
    };
    setupMocks();
    render(
      <MemoryRouter initialEntries={['/trading']}>
        <AuthContext.Provider value={{ status: 'authenticated', user: { email: 'a@b.com' } } as never}>
          <Probe />
          <TradingPage />
        </AuthContext.Provider>
      </MemoryRouter>,
    );
    clickTab('自选');
    expect(searches.at(-1)).toBe('?tab=watchlist');
  });
});

// ── 持仓 / 复盘 Tab (member 门内) ────────────────────────────────────

describe('TradingPage 持仓/复盘 Tab', () => {
  it('member 态点持仓: 空数据渲染四区块与合规脚注', async () => {
    renderTrading();
    clickTab('持仓');
    expect(screen.getByText(/暂无持仓/)).toBeInTheDocument();
    expect(screen.getByText(/暂无交易记录/)).toBeInTheDocument();
    expect(screen.getByText('权益与风控参数')).toBeInTheDocument();
    expect(screen.getByText(/不构成买卖指令或投资建议/)).toBeInTheDocument();
    // 录入表单在空态下直接可见（无需展开）
    expect(screen.getByLabelText('交易记录录入')).toBeInTheDocument();
    clickTab('复盘');
    await waitFor(() =>
      expect(screen.getByText(/复盘评分将在每晚交易数据管线运行后生成/)).toBeInTheDocument(),
    );
  });

  it('持仓 Tab: loading 骨架与数据加载失败提示', () => {
    renderTrading({}, { loading: true });
    clickTab('持仓');
    expect(screen.getByLabelText('加载中')).toBeInTheDocument();
    cleanup();
    renderTrading({}, { loading: false, error: 'connection refused' });
    clickTab('持仓');
    expect(screen.getByRole('alert')).toHaveTextContent('connection refused');
  });

  it('持仓 Tab: 有持仓渲染表格行', () => {
    renderTrading({}, {
      positions: [{
        code: '600519', name: '贵州茅台', shares: 100, avg_cost: 1710.5, stop_current: 1573.2,
      }],
    });
    clickTab('持仓');
    const rows = screen.getAllByRole('row');
    expect(rows[1]?.textContent).toContain('600519');
    expect(rows[1]?.textContent).toContain('1573.200');
    expect(rows[1]?.textContent).toContain('1710.500');
  });

  it('复盘 Tab: Actions 产出后渲染统计卡与逐笔列表', async () => {
    renderTrading({}, {}, [
      {
        id: 'rv1', user_id: 'u', trade_id: 't1', review_date: '2026-08-19',
        discipline_score: 100, result_r: 2, mae_pct: -1,
        events: { pnl: 100, dimensions: {} }, computed_at: '2026-08-19T17:30:00Z',
      },
    ]);
    clickTab('复盘');
    await waitFor(() => expect(screen.getByText('100.0%')).toBeInTheDocument());
    expect(screen.getByText(/1 笔已复盘/)).toBeInTheDocument();
    expect(screen.getByText('逐笔复盘')).toBeInTheDocument();
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

  it('初始参数联动 trading_settings: 已保存时回填, 未保存时回落本地默认', () => {
    // 未保存 (updated_at 空): 权益空, 本地默认 0.75% / 20%
    renderTrading();
    clickTab('信号');
    expect(screen.getByPlaceholderText('100000')).toHaveValue('');
    expect(screen.getByDisplayValue('0.75')).toBeInTheDocument();
    expect(screen.getByDisplayValue('20')).toBeInTheDocument();
    cleanup();
    // 已保存: DB 值作为计算器初始值
    renderTrading({}, {
      settings: {
        user_id: 'u', updated_at: '2026-08-20T09:00:00Z', equity_cny: 200000,
        risk_per_trade_pct: 1, max_positions: 3, max_position_pct: 30, max_portfolio_risk_pct: 5,
      },
    });
    clickTab('信号');
    expect(screen.getByPlaceholderText('100000')).toHaveValue('200000');
    expect(screen.getByDisplayValue('1')).toBeInTheDocument();
    expect(screen.getByDisplayValue('30')).toBeInTheDocument();
    // 联动后本地修改仍生效 (临时改参数参与计算)
    fireEvent.change(screen.getByPlaceholderText('17.10'), { target: { value: '17.1' } });
    fireEvent.change(screen.getByPlaceholderText('15.73'), { target: { value: '15.73' } });
    // 风险 1% × 200000 = 2000, 每股风险 1.37 → 1459 股
    expect(screen.getByText('1459 股')).toBeInTheDocument();
  });

  it('settings 已保存但权益未设置: 参数回填, 权益保留空输入', () => {
    renderTrading({}, {
      settings: {
        user_id: 'u', updated_at: '2026-08-20T09:00:00Z', equity_cny: null,
        risk_per_trade_pct: 0.75, max_positions: 5, max_position_pct: 20, max_portfolio_risk_pct: 4,
      },
    });
    clickTab('信号');
    expect(screen.getByPlaceholderText('100000')).toHaveValue('');
    expect(screen.getByDisplayValue('0.75')).toBeInTheDocument();
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
