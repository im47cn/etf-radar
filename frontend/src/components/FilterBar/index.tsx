import { DimensionTabs } from './DimensionTabs';
import { SignalTabs } from './SignalTabs';
import { SearchInput } from './SearchInput';
import { Legend } from './Legend';
import { MarketViewSelector } from './MarketViewSelector';
import { PageHelp, type HelpSection } from '@/components/help/PageHelp';

/** 主题雷达帮助文案: 强度双轨制 + 信号三态 + 读法 + 常见误读. */
const RADAR_HELP: HelpSection[] = [
  {
    title: '理论基础',
    children: [
      <p key="strength">
        <strong>强度评分（0–100，双轨制）</strong>：每个维度 = 0.5 × 百分位排名 P + 0.5 × sigmoid 动量 M，
        硬上限 99。<strong>≥60 视为走强</strong>。综合（composite）= 短/中/长三周期加权汇总。
        短期用 r_1d/r_5d，中期用 r_20d/r_60d，长期用 r_120d/r_ytd。
      </p>,
      <p key="signal">
        <strong>信号三态</strong>（跨市美股↔A股映射）：
        <strong>共振</strong> = 多周期同向走强/走弱，跨市映射顺畅（有方向，取美股动量）；
        <strong>传导</strong> = 一方明显领先、另一方尚未跟上（已降级，无方向）；
        <strong>背离</strong> = 跨市方向相反，需二次确认。
      </p>,
    ],
  },
  {
    title: '使用方法',
    children: [
      <p key="r1">① <strong>维度 Tab</strong>（短期/中期/长期/综合）：切换列表排序与详情区展示的强度维度。</p>,
      <p key="r2">② <strong>信号 Tab</strong>（全部/共振/传导/背离）：按信号类型筛选主题。</p>,
      <p key="r3">③ <strong>美股 / A 股</strong>视角：切换双轨强度池——美股视角用 us_strength，A 股视角用 cn_strength。</p>,
      <p key="r4">④ 列表：<strong>★</strong> = 已持仓主题，<strong>🇨🇳</strong> = A 股本土赛道（无美股映射）。点行联动详情与候选池。</p>,
      <p key="r5">⑤ 详情区：美股映射与置信度、各周期收益、四维强度、信号说明；底部 A 股 ETF 候选池按映射分排序。</p>,
    ],
  },
  {
    title: '常见误读',
    children: [
      <p key="m1"><strong>共振"有方向"是薄 alpha</strong>：5 年回测次日 A 股同向约 56%，扣交易成本后期望有限，仅作方向倾向参考。</p>,
      <p key="m2"><strong>传导 ≈ 随机</strong>：回测次日跟随率约 49%，已不再具备方向预测力，仅作状态观察。</p>,
      <p key="m3"><strong>强度是"当前状态"非买卖点</strong>：高分代表近期强，不直接等价于买入信号。</p>,
    ],
  },
];

export const FilterBar = () => (
  <div className="bg-white border-b p-3 flex flex-wrap items-center gap-4">
    <DimensionTabs />
    <SignalTabs />
    <MarketViewSelector />
    <Legend />
    <div className="ml-auto flex items-center gap-2">
      <SearchInput />
      <PageHelp title="主题雷达" sections={RADAR_HELP} />
    </div>
  </div>
);
