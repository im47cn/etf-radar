import { Link } from 'react-router-dom';
import { useMetals } from '@/hooks/useMetals';
import { useDataContext } from '@/providers/dataContext';
import { MacroCards } from '@/components/metals/MacroCards';
import { MetalsThemeCards } from '@/components/metals/MetalsThemeCards';
import { PageHelp, type HelpSection } from '@/components/help/PageHelp';
import { Skeleton } from '@/components/ui/skeleton';
import { formatPct } from '@/lib/format';

// 免责文案与回测结论对齐: gsr_timing_backtest (2026-08-19) 预注册判定"无 alpha",
// 金银比分位是描述性指标 — 与 leader 规则同款对冲, 勿删.
const METALS_HELP: HelpSection[] = [
  {
    title: '贵金属宏观指标',
    children: [
      <p key="gsr">
        <strong>金银比</strong> = GLD/SLV 收盘价比，5 年滚动分位。分位高 = 金贵银贱，分位低 = 银强于金。
        仅描述相对估值位置：<strong>60 日前瞻检验未达显著（p=0.17，方向对但欠功率），无择时含义</strong>。
      </p>,
      <p key="rr">
        <strong>实际利率代理</strong>：TIP（iShares TIPS ETF）价格，与实际利率反向。传统上实际利率是金价第一性驱动，
        20 日滚动相关塌陷可视作关系失效的预警。Yahoo 已下线 DFII10，故用 ETF 价格代理。
      </p>,
      <p key="ml">
        <strong>金矿杠杆比</strong> = GDX/GLD。矿股是带经营杠杆的金价放大器，比价 1 年分位极高通常对应情绪过热。
        <strong>美元指数</strong>为金价第二驱动。
      </p>,
    ],
  },
  {
    title: '⚠ 风险与边界',
    children: [
      <p key="lof">
        A 股白银端为 <strong>161226 白银 LOF</strong>（非 ETF），场内价格含溢价波动、流动性受限，
        与美股 SLV 的收益差异可能远大于 ETF 映射主题的常规偏差。
      </p>,
      <p key="notdir">
        本页全部指标为<strong>描述性仪表盘</strong>，不含择时信号，不构成投资建议。
      </p>,
    ],
  },
];

const MetalsContent = () => {
  const { data, error, isLoading } = useMetals();
  const { themes } = useDataContext();

  if (isLoading)
    return (
      <div className="flex flex-col gap-4 p-4" aria-busy="true" aria-label="加载中">
        <Skeleton className="h-20" />
        <Skeleton className="h-40" />
      </div>
    );
  if (error || !data) return <div className="p-8 text-center text-gray-400">暂无贵金属数据</div>;

  const cn = data.cn_side;
  const rows = [
    { label: '黄金 ETF', etf: cn.gold_etf },
    { label: '白银 LOF', etf: cn.silver_lof },
  ].filter((r) => r.etf != null);

  return (
    <main className="flex flex-col gap-4 animate-crossfade">
      <div className="flex items-start justify-between gap-2 animate-fade-rise" style={{ animationDelay: '0ms' }}>
        <div>
          <h1 className="text-lg font-semibold text-gray-800">贵金属</h1>
          <p className="mt-0.5 text-xs text-gray-500">
            金/银宏观仪表盘 · 描述性指标（非择时信号） · 截至 {data.as_of ?? '—'}
          </p>
        </div>
        <PageHelp title="贵金属" sections={METALS_HELP} />
      </div>

      <div className="animate-fade-rise" style={{ animationDelay: '60ms' }}>
        <MacroCards data={data} />
      </div>

      {themes && (
        <div className="animate-fade-rise" style={{ animationDelay: '120ms' }}>
          <h2 className="text-sm font-medium text-gray-600 mb-2">主题强度（美股锚 → A 股映射）</h2>
          <MetalsThemeCards themes={themes.themes} />
        </div>
      )}

      {rows.length > 0 && (
        <div className="animate-fade-rise" style={{ animationDelay: '180ms' }}>
          <h2 className="text-sm font-medium text-gray-600 mb-2">A 股端行情</h2>
          <div className="rounded-lg border bg-white p-3 text-xs divide-y">
            {rows.map(({ label, etf }) => (
              <div key={etf!.code} className="flex items-center justify-between py-2">
                <span className="text-gray-700">
                  {label} · {etf!.name ?? etf!.code}
                  <span className="text-gray-400 ml-2">{etf!.code}</span>
                </span>
                <span className="flex items-center gap-4 tabular-nums">
                  <span className="text-gray-600">{etf!.price?.toFixed(3) ?? '—'}</span>
                  <span className={(etf!.r_1d ?? 0) >= 0 ? 'text-blue-600' : 'text-red-600'}>
                    {formatPct(etf!.r_1d)}
                  </span>
                  <span className="text-gray-400">{etf!.amount_yi?.toFixed(1) ?? '—'} 亿</span>
                </span>
              </div>
            ))}
          </div>
          <p className="mt-1.5 text-xs text-gray-400">
            LOF 场内价格含溢价，可能偏离净值；溢价数据源未接入（premium 预留）。
          </p>
        </div>
      )}

      <p className="animate-fade-rise text-xs text-gray-400" style={{ animationDelay: '240ms' }}>
        金银是网格策略热门标的 → <Link to="/grid" className="text-blue-600 hover:underline">网格选标（会员）</Link>
        。口径：金银比/分位与后端预注册回测一致；指标不含择时信号。
      </p>
    </main>
  );
};

export const MetalsPage = () => (
  <div className="max-w-6xl mx-auto p-4">
    <MetalsContent />
  </div>
);
