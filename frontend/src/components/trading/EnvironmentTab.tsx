import { useTrading } from '@/hooks/useTrading';
import type { TradingEnvironment, TradingIndex, TradingRegime } from '@/types/trading';
import { Skeleton } from '@/components/ui/skeleton';
import { formatPct } from '@/lib/format';

/** 趋势模板 8 条件短名 (spec §2.1), 与 criteria 布尔数组按下标对应. */
const TEMPLATE_CRITERIA = [
  '收盘 > 50/150/200MA',
  '150MA > 200MA',
  '200MA 至少 1 个月上行',
  '50MA > 150/200MA',
  '现价 ≥ 52周低点 × 1.30',
  '现价 ≥ 52周高点 × 0.75',
  'RS 分位 ≥ 70',
  '50/200MA 非缠绕（距离 ≥1%）',
] as const;

const REGIME_LABEL: Record<TradingRegime, string> = {
  offense: '进攻',
  neutral: '中性',
  defense: '防守',
};

const regimeBadge = (regime: TradingRegime): string => {
  if (regime === 'offense') return 'bg-green-100 text-green-700 border-green-200';
  if (regime === 'defense') return 'bg-red-100 text-red-700 border-red-200';
  return 'bg-gray-100 text-gray-700 border-gray-200';
};

/** 宽度百分数 (breadth 值为小数占比). */
const fmtBreadth = (v: number | null): string => formatPct(v);

/** 指数卡: 名称 + 收盘 + x/8 + 8 条件点阵 (title 提示条件名). */
const IndexCard = ({ idx }: { idx: TradingIndex }) => {
  const pass = idx.template_pass;
  // 派生标签提 const: JSX 内 ?? 与三元是 coverage 盲区 (CONVENTIONS)
  const name = idx.name ?? idx.code;
  const passLabel = pass != null ? `${pass}/8` : '—';
  const closeLabel = idx.close != null ? idx.close.toFixed(2) : '—';
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="flex items-baseline justify-between">
        <span className="font-medium text-gray-800">{name}</span>
        <span className="text-xs text-gray-400">{idx.code}</span>
      </div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="text-2xl font-semibold text-gray-900">{passLabel}</span>
        <span className="text-xs text-gray-500">趋势模板通过</span>
        <span className="ml-auto text-sm text-gray-600">{closeLabel}</span>
      </div>
      <div className="mt-3 grid grid-cols-8 gap-1" role="list" aria-label={`${name} 趋势模板 8 条件`}>
        {TEMPLATE_CRITERIA.map((label, i) => {
          const ok = idx.criteria[i] === true;
          return (
            <span
              key={label}
              role="listitem"
              title={`${i + 1}. ${label}：${ok ? '通过' : '未通过'}`}
              className={ok ? 'h-2.5 rounded bg-green-500' : 'h-2.5 rounded bg-gray-200'}
            />
          );
        })}
      </div>
    </div>
  );
};

/** 宽度佐证卡: ma20/60/120 站上率 (market_temperature.json, 不进档位公式). */
const BreadthCard = ({ env }: { env: TradingEnvironment }) => {
  const b = env.breadth;
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-800">宽度佐证</div>
      <div className="mt-1 text-xs text-gray-500">全市场个股 MA 站上率（不参与档位计算）</div>
      <div className="mt-3 flex gap-6">
        <div>
          <div className="text-lg font-semibold text-gray-900">{b != null ? fmtBreadth(b.ma20_pct) : '—'}</div>
          <div className="text-xs text-gray-500">MA20</div>
        </div>
        <div>
          <div className="text-lg font-semibold text-gray-900">{b != null ? fmtBreadth(b.ma60_pct) : '—'}</div>
          <div className="text-xs text-gray-500">MA60</div>
        </div>
        <div>
          <div className="text-lg font-semibold text-gray-900">{b != null ? fmtBreadth(b.ma120_pct) : '—'}</div>
          <div className="text-xs text-gray-500">MA120</div>
        </div>
      </div>
    </div>
  );
};

/** 市场环境 Tab: 档位徽标 + 三指数模板仪表 + 宽度佐证. 免费内容. */
export const EnvironmentTab = () => {
  const { data, error, isLoading } = useTrading();

  if (isLoading)
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="加载中">
        <Skeleton className="h-24" />
        <Skeleton className="h-32" />
      </div>
    );
  if (error || !data || !data.environment)
    return <div className="p-8 text-center text-gray-400">暂无交易环境数据</div>;

  const env = data.environment;
  const regime = env.regime;
  const rsMissing = env.source_status['rs_benchmark'] === 'missing';

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-gray-600">环境档位</span>
        <span
          className={`rounded-full border px-3 py-1 text-sm font-semibold ${regime != null ? regimeBadge(regime) : 'bg-gray-100 text-gray-500 border-gray-200'}`}
        >
          {regime != null ? REGIME_LABEL[regime] : '数据缺失'}
        </span>
        <span className="text-xs text-gray-400">
          规则：≥2 只指数模板通过 ≥6/8 为进攻；≥2 只 ≤3/8 为防守；其余为中性
        </span>
      </div>

      {rsMissing && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700" role="status">
          ⚠ RS 基准（中证全指 000985）当日数据缺失，综合分暂不含 RS 项（口径降级）。
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {env.indices.map((idx) => (
          <IndexCard key={idx.code} idx={idx} />
        ))}
      </div>

      <BreadthCard env={env} />
    </div>
  );
};
