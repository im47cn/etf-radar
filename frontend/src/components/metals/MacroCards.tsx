import type React from 'react';
import type { Metals } from '@/types/metals';
import { useSubscription } from '@/lib/subscription/useSubscription';
import { formatPct } from '@/lib/format';
import { cn } from '@/lib/utils';
import { Sparkline } from './Sparkline';

interface Props {
  data: Metals;
}

const Card: React.FC<{ title: string; status: string; children: React.ReactNode; className?: string }> = ({
  title, status, children, className,
}) => (
  <div className={cn('rounded-lg border bg-white p-3', status !== 'ok' && 'opacity-60', className)}>
    <div className="flex items-center justify-between">
      <span className="text-xs font-medium text-gray-500">{title}</span>
      {status !== 'ok' && <span className="text-xs text-gray-400">数据源不可用</span>}
    </div>
    {children}
  </div>
);

const pctColor = (p: number): string => (p >= 0.8 ? 'bg-red-500' : p >= 0.5 ? 'bg-amber-400' : 'bg-blue-500');

const kv = (label: string, value: React.ReactNode): React.ReactNode => (
  <div className="flex justify-between text-xs">
    <span className="text-gray-500">{label}</span>
    <span className="tabular-nums text-gray-700">{value}</span>
  </div>
);

/** 金银比 5 年分位进度条; 分位与金价相关系数为会员内容 (设计定死的门控点). */
const PercentileBar: React.FC<{ percentile: number | null; isMember: boolean }> = ({ percentile, isMember }) => {
  if (percentile == null) return <span className="text-xs text-gray-400">—</span>;
  if (!isMember)
    return (
      <span className="text-xs text-gray-400" title="会员可见">
        🔒 分位
      </span>
    );
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 rounded bg-gray-100 overflow-hidden">
        <div className={cn('h-full', pctColor(percentile))} style={{ width: `${Math.round(percentile * 100)}%` }} />
      </div>
      <span className="text-xs tabular-nums text-gray-600 w-9 text-right">
        {Math.round(percentile * 100)}%
      </span>
    </div>
  );
};

const LockedValue: React.FC<{ value: string; isMember: boolean; title?: string }> = ({
  value, isMember, title = '会员可见',
}) => (isMember ? <>{value}</> : <span className="text-gray-400" title={title}>🔒</span>);

export const MacroCards = ({ data }: Props) => {
  const { state: subState } = useSubscription();
  const isMember = subState === 'member';
  const g = data.gold_silver_ratio;
  const rr = data.real_rate;
  const dxy = data.dxy;
  const ml = data.miner_leverage;
  const st = data.source_status;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Card title="金银比 (GLD/SLV)" status={st.gold_silver} className="col-span-2">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="text-2xl font-semibold tabular-nums text-gray-800">
              {g.value?.toFixed(2) ?? '—'}
            </div>
            <p className="text-xs text-gray-500 mt-0.5">5 年分位</p>
            <div className="w-40 mt-1">
              <PercentileBar percentile={g.percentile_5y} isMember={isMember} />
            </div>
          </div>
          <Sparkline points={g.series.slice(-120)} width={220} />
        </div>
      </Card>
      <Card title="实际利率代理 (TIP)" status={st.real_rate}>
        <div className="text-2xl font-semibold tabular-nums text-gray-800">
          {rr.tip_price?.toFixed(2) ?? '—'}
        </div>
        <div className="mt-1 space-y-0.5">
          {kv('60 日变动', rr.change_60d == null ? '—' : `${rr.change_60d >= 0 ? '+' : ''}${rr.change_60d.toFixed(2)}`)}
          {kv('金价 20 日相关', <LockedValue isMember={isMember} value={rr.corr_gold_20d?.toFixed(2) ?? '—'} />)}
        </div>
      </Card>
      <Card title="美元指数 (DXY)" status={st.dxy}>
        <div className="text-2xl font-semibold tabular-nums text-gray-800">
          {dxy.value?.toFixed(1) ?? '—'}
        </div>
        <div className="mt-1 space-y-0.5">
          {kv('20 日', formatPct(dxy.r_20d))}
          {kv('60 日', formatPct(dxy.r_60d))}
        </div>
      </Card>
      <Card title="金矿杠杆比 (GDX/GLD)" status={st.miner_leverage} className="col-span-2 lg:col-span-1">
        <div className="text-2xl font-semibold tabular-nums text-gray-800">
          {ml.ratio?.toFixed(3) ?? '—'}
        </div>
        <div className="mt-1">
          {kv('1 年分位', ml.percentile_1y == null ? '—' : `${Math.round(ml.percentile_1y * 100)}%`)}
        </div>
      </Card>
    </div>
  );
};
