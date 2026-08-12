import { FeatureGate } from '@/components/gate/FeatureGate';
import { HoldingsList } from '@/components/portfolio/HoldingsList';
import { PageHelp, type HelpSection } from '@/components/help/PageHelp';
import { usePortfolioScores } from '@/hooks/usePortfolioScores';

/** 我的持仓帮助文案: covered/uncovered + 各模块读法 + 常见误读. 放 gate 外, 未登录亦可见. */
const PORTFOLIO_HELP: HelpSection[] = [
  {
    title: '核心概念',
    children: [
      <p key="covered">
        <strong>covered / uncovered</strong>：持仓 ETF 若命中 14 个追踪主题之一为 covered（归属主题，
        展示双轨强度与信号）；否则为 uncovered（灰底，仅记录持仓信息、无信号）。
      </p>,
      <p key="strength">
        <strong>双轨强度</strong>：covered 持仓同时显示美股（us_strength）与 A 股（cn_strength）池内的相对强度，
        以及该 ETF 自身的综合百分位。
      </p>,
      <p key="tags">每只持仓带 L2 行业与动量标签，便于横向归类。</p>,
    ],
  },
  {
    title: '使用方法',
    children: [
      <p key="r1">① <strong>持仓卡片</strong>：股数 / 成本价 / 现价 / 市值 / 盈亏 + 归属信号文案。</p>,
      <p key="r2">② <strong>汇总</strong>：总市值、总盈亏（金额 + 百分比）、覆盖率、强弱分布四档计数。</p>,
      <p key="r3">③ <strong>事件流</strong>（默认折叠）：持仓主题的信号变化，可"全部标为已读"。</p>,
      <p key="r4">④ <strong>信号扫描</strong>（默认折叠）：综合强度≥阈值且短周期≥阈值、排除已持仓的候选主题。</p>,
      <p key="r5">⑤ 免费版最多 5 支，满限后点"升级解锁更多"。</p>,
    ],
  },
  {
    title: '常见误读',
    children: [
      <p key="m1"><strong>uncovered 持仓无信号</strong>：超出追踪主题范围的 ETF 只记录持仓信息，不参与信号引擎。</p>,
      <p key="m2"><strong>盈亏需手填成本价</strong>：系统不抓券商成本，未填成本价则无法计算盈亏。</p>,
    ],
  },
];

export const PortfolioPage = () => {
  // 计数来自 usePortfolioScores（纯 context 读，无 IO 副作用；与 HoldingsList 内部调用同源）。
  // gate 外渲染：未登录时 scores 为空 → 标题不带计数。
  const { scores } = usePortfolioScores();
  return (
  <div className="max-w-6xl mx-auto p-4">
    {/* 标题与"使用说明"在 gate 外渲染：未登录也能看到持仓概念说明 */}
    <div className="mb-4 flex items-center justify-between">
      <h1 className="text-lg font-semibold text-gray-800">
        我的持仓{scores.length > 0 ? `（${scores.length} 只）` : ''}
      </h1>
      <PageHelp title="我的持仓" sections={PORTFOLIO_HELP} />
    </div>
    <FeatureGate copy="portfolio" required="auth">
      <HoldingsList />
    </FeatureGate>
  </div>
  );
};
