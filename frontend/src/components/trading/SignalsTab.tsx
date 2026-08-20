import { useMemo } from 'react';
import { useTrading } from '@/hooks/useTrading';
import type { TradingCandidate, TradingCandidateState, TradingRegime } from '@/types/trading';
import { Skeleton } from '@/components/ui/skeleton';
import { PositionCalculator } from '@/components/trading/PositionCalculator';

/**
 * 状态文案 (合规立场 §0: 全部事实性表述, 禁"可建仓/建议买入"等指令词汇).
 * in_buy_zone = 收盘价落在买区 [pivot, pivot×1.05];
 * near_buy_zone = 距买区下沿 ≤3%; watch = 其余.
 */
const STATE_LABEL: Record<TradingCandidateState, string> = {
  in_buy_zone: '已进入买区',
  near_buy_zone: '接近买点',
  watch: '底部观察',
};

const stateClass = (state: TradingCandidateState | null): string => {
  if (state === 'in_buy_zone') return 'bg-blue-900/60 text-blue-300';
  if (state === 'near_buy_zone') return 'bg-amber-900/50 text-amber-300';
  return 'bg-gray-800 text-gray-400';
};

/** 数值格式化 (null → '—'), 统一走纯函数避免 JSX 内三元/?? 的 coverage 盲区. */
const fmtNum = (v: number | null, digits = 2): string => (v != null ? v.toFixed(digits) : '—');
const fmtInt = (v: number | null): string => (v != null ? String(Math.round(v)) : '—');
const fmtSignedPct = (v: number | null): string =>
  v != null ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '—';

const chgClass = (v: number | null): string => {
  if (v == null) return 'text-gray-500';
  return v > 0 ? 'text-red-400' : v < 0 ? 'text-green-400' : 'text-gray-400';
};

const vcpLabel = (c: TradingCandidate): string => {
  if (c.vcp == null) return '—';
  const times = c.vcp.contractions != null ? `${Math.round(c.vcp.contractions)}次` : '—';
  const depth = c.vcp.depth_pct != null ? `${c.vcp.depth_pct.toFixed(1)}%` : '—';
  return `${times}/${depth}`;
};

const buyZoneLabel = (c: TradingCandidate): string => {
  if (c.buy_zone_low == null || c.buy_zone_high == null) return '—';
  return `${c.buy_zone_low.toFixed(1)}~${c.buy_zone_high.toFixed(1)}`;
};

/** 综合分降序, null 分排末尾 (契约已保证降序, 前端兜底防后端未排). */
const sortByScore = (candidates: TradingCandidate[]): TradingCandidate[] => {
  const rows = [...candidates];
  rows.sort((a, b) => {
    if (a.composite_score == null) return 1;
    if (b.composite_score == null) return -1;
    return b.composite_score - a.composite_score;
  });
  return rows;
};

/** 筛选漏斗: 全市场 → 可交易 → Stage2 → VCP → TopN. */
const FunnelRow = ({
  items,
}: {
  items: { label: string; value: number | null }[];
}) => (
  <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
    {items.map((it, i) => (
      <span key={it.label} className="flex items-center gap-2">
        {i > 0 && <span className="text-gray-300">→</span>}
        <span className="rounded bg-gray-100 px-2 py-1">
          {it.label} <strong className="text-gray-800">{fmtInt(it.value)}</strong>
        </span>
      </span>
    ))}
  </div>
);

/** 信号跟踪 Tab: 候选池深色数据表格 + 筛选漏斗 + 仓位计算器. 会员门内. */
export const SignalsTab = () => {
  const { data, error, isLoading } = useTrading();

  const rows = useMemo(() => sortByScore(data?.candidates ?? []), [data]);
  const regime: TradingRegime | null = data?.environment?.regime ?? null;
  const defenseFrozen = regime === 'defense' && rows.length > 0;

  if (isLoading)
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="加载中">
        <Skeleton className="h-16" />
        <Skeleton className="h-64" />
      </div>
    );
  if (error || !data)
    return <div className="p-8 text-center text-gray-400">暂无交易信号数据</div>;

  const stats = data.universe_stats;
  // 逐行 push (CONVENTIONS: 多行对象字面量是 v8 coverage 盲区)
  const funnelItems: { label: string; value: number | null }[] = [];
  funnelItems.push({ label: '全市场', value: stats?.total ?? null });
  funnelItems.push({ label: '可交易', value: stats?.tradable ?? null });
  funnelItems.push({ label: 'Stage 2', value: stats?.stage2 ?? null });
  funnelItems.push({ label: 'VCP 成立', value: stats?.vcp ?? null });
  funnelItems.push({ label: '综合分 Top', value: stats?.top ?? null });

  return (
    <div className="flex flex-col gap-4">
      {defenseFrozen && (
        <p
          className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700"
          role="status"
        >
          ⚠ 当前环境档位为防守：下列候选的状态全部为「底部观察」（防守档不输出买区相关状态）。数据照常展示。
        </p>
      )}

      <FunnelRow items={funnelItems} />

      {rows.length === 0 ? (
        <div className="p-8 text-center text-gray-400">今日候选池为空</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="min-w-full bg-gray-900 text-left text-xs text-gray-200">
            <thead>
              <tr className="border-b border-gray-700 bg-gray-800 text-gray-400">
                <th className="px-2 py-2 font-medium">代码</th>
                <th className="px-2 py-2 font-medium">名称</th>
                <th className="px-2 py-2 font-medium">综合分</th>
                <th className="px-2 py-2 font-medium">阶段</th>
                <th className="px-2 py-2 font-medium">RS分位</th>
                <th className="px-2 py-2 font-medium">VCP</th>
                <th className="px-2 py-2 font-medium">买区</th>
                <th className="px-2 py-2 font-medium">止损</th>
                <th className="px-2 py-2 font-medium">状态</th>
                <th className="px-2 py-2 font-medium">涨跌幅</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => {
                const stateLabel = c.state != null ? STATE_LABEL[c.state] : '—';
                // 名称/阶段/模板通过数提 const: JSX 内 ?? 与三元是 coverage 盲区
                const nameLabel = c.name ?? '—';
                const stageLabel = c.stage != null ? `S${c.stage}` : '—';
                const passLabel = c.template_pass != null ? `${c.template_pass}/8` : '';
                return (
                  <tr key={c.code} className="border-b border-gray-800 hover:bg-gray-800/60">
                    <td className="px-2 py-1.5 font-mono text-gray-400">{c.code}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">
                      {nameLabel}
                      {c.limit_up_unexecutable === true && (
                        <span className="ml-1 rounded bg-red-900/50 px-1 text-[10px] text-red-300">涨停一字</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 font-semibold text-gray-100">{fmtNum(c.composite_score, 1)}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap text-gray-300">
                      {stageLabel}
                      <span className="ml-1 text-gray-500">{passLabel}</span>
                    </td>
                    <td className="px-2 py-1.5 text-gray-300">{fmtNum(c.rs_pct, 0)}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap text-gray-300">{vcpLabel(c)}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap text-gray-300">{buyZoneLabel(c)}</td>
                    <td className="px-2 py-1.5 text-gray-300">{fmtNum(c.stop, 1)}</td>
                    <td className="px-2 py-1.5">
                      <span className={`rounded px-1.5 py-0.5 whitespace-nowrap ${stateClass(c.state)}`}>{stateLabel}</span>
                    </td>
                    <td className={`px-2 py-1.5 ${chgClass(c.chg_pct)}`}>{fmtSignedPct(c.chg_pct)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-gray-400">
        口径：综合分 1-10（趋势模板 30% + VCP 40% + RS 20% + 流动性/波动 10%）；买区 = [pivot, pivot×1.05]；
        止损 = max(基部最近低点, pivot×0.92)。涨跌幅为当日收盘涨跌。
        综合分反映结构完整度（趋势模板/VCP/RS 的加权描述），为筛选漏斗排序依据，非未来收益预测。
      </p>

      <PositionCalculator regime={regime} />
    </div>
  );
};
