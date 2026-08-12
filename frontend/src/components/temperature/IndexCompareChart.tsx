import { useMemo, useState } from 'react';
import { ChartCard } from '@/components/ChartCard';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { MarketPoint } from '@/types/marketTemperature';
import type { IndexSeriesEntry } from '@/types/indexSeries';

interface Props {
  market: MarketPoint[];
  indices: IndexSeriesEntry[];
}

const INDEX_COLORS: Record<string, string> = {
  '000001': '#dc2626', // 上证指数
  '399001': '#7c3aed', // 深证成指
  '399006': '#059669', // 创业板指
  '000300': '#d97706', // 沪深300
  '000688': '#0891b2', // 科创50
  '000698': '#db2777', // 科创100
};

const RATE_KEY = 'rate';
const RATE_LABEL = '宽度站上率';
const RATE_COLOR = '#1e293b';

// 默认仅显示宽度(始终) + 上证指数 + 创业板指 (大盘代表 + 成长代表, 风格不重叠);
// 深成/沪深300/科创50/科创100 默认隐藏, 用户点图例按需展开.
const DEFAULT_HIDDEN = new Set<string>(['399001', '000300', '000688', '000698']);

interface CustomLegendProps {
  indices: IndexSeriesEntry[];
  hidden: Set<string>;
  onToggle: (key: string) => void;
}

// 自渲染图例: 不依赖 recharts 注入 payload, 保证 hide 项始终可见可点 (根治 payload 不确定性).
const CustomLegend = ({ indices, hidden, onToggle }: CustomLegendProps) => (
  <div className="mt-2 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px]">
    {/* 宽度项: 始终显示, 不可切换 */}
    <button type="button" disabled className="flex cursor-default items-center gap-1 opacity-100">
      <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: RATE_COLOR }} />
      <span>{RATE_LABEL}</span>
    </button>
    {indices.map((idx) => {
      const isHidden = hidden.has(idx.code);
      return (
        <button
          key={idx.code}
          type="button"
          onClick={() => onToggle(idx.code)}
          className={`flex cursor-pointer items-center gap-1 transition-opacity ${
            isHidden ? 'opacity-30' : 'opacity-100 hover:text-gray-900'
          }`}
        >
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: INDEX_COLORS[idx.code] ?? '#64748b' }}
          />
          <span>{idx.name}</span>
        </button>
      );
    })}
  </div>
);

/** 温度页对比图: 左轴宽度站上率% + 右轴指数涨跌幅%(相对窗口起点), 双 Y 轴看广度-价格背离. */
export const IndexCompareChart = ({ market, indices }: Props) => {
  const [hidden, setHidden] = useState<Set<string>>(DEFAULT_HIDDEN);

  const data = useMemo(() => {
    // 各指数转"相对窗口起点的涨跌幅%": 消除绝对点位量级差 (上证~3800 vs 深成~14000),
    // 多线同尺度可比, 也能与左轴宽度站上率同框对照"广度 vs 价格变化".
    const base: Record<string, number> = {};
    for (const idx of indices) {
      for (const v of idx.series) {
        if (v != null) {
          base[idx.code] = v;
          break;
        }
      }
    }
    const rows: Array<Record<string, number | string | null>> = [];
    for (let i = 0; i < market.length; i++) {
      const row: Record<string, number | string | null> = {
        date: market[i]?.date ?? '',
        [RATE_KEY]: market[i]?.rate ?? null,
      };
      for (const idx of indices) {
        const v = idx.series[i];
        const b = base[idx.code];
        row[idx.code] = v != null && b ? +((v / b - 1) * 100).toFixed(2) : null;
      }
      rows.push(row);
    }
    return rows;
  }, [market, indices]);

  const toggle = (key: string) => {
    if (key === RATE_KEY) return; // 宽度始终显示
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (!market.length || !indices.length) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-400">
        暂无指数对比数据
      </div>
    );
  }

  return (
    <ChartCard
      title="宽度 vs A 股主要指数"
      subtitle="左轴站上率% · 右轴指数涨跌幅% · 点图例切换"
      helpTitle="宽度 vs 指数 · 读法"
      help={
        <>
          <p><strong>左轴</strong>：宽度站上率%（全市场站上 MA 占比）；<strong>右轴</strong>：指数相对窗口起点的涨跌幅%（归一化消除绝对点位量级差）。</p>
          <p><strong>看背离</strong>：宽度升 + 指数跌 = 底部扩张（涨面先于点位）；宽度降 + 指数涨 = 顶部收缩（涨面萎缩）。</p>
          <p>点图例切换指数显示；<strong>误读</strong>：指数已归一化（相对起点），非绝对点位。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 10 }} />
          <YAxis yAxisId="breadth" domain={[0, 100]} unit="%" tick={{ fontSize: 10 }} width={40} />
          {/* 右轴: 指数相对窗口起点的涨跌幅% (线性, 已归一化消除量级差) */}
          <YAxis yAxisId="price" orientation="right" unit="%" tick={{ fontSize: 10 }} width={48} />
          <Tooltip
            formatter={(value, name) => {
              const label = typeof name === 'string' ? name : String(name);
              if (label === RATE_LABEL) return [`${Number(value).toFixed(1)}%`, label];
              return [`${Number(value).toFixed(2)}%`, label];
            }}
          />
          <Line
            yAxisId="breadth"
            dataKey={RATE_KEY}
            name={RATE_LABEL}
            stroke={RATE_COLOR}
            strokeWidth={1.5}
            dot={false}
            type="monotone"
            connectNulls
          />
          {indices.map((idx) => (
            <Line
              key={idx.code}
              yAxisId="price"
              dataKey={idx.code}
              name={idx.name}
              stroke={INDEX_COLORS[idx.code] ?? '#64748b'}
              strokeWidth={1.25}
              dot={false}
              type="monotone"
              connectNulls
              hide={hidden.has(idx.code)}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      <CustomLegend indices={indices} hidden={hidden} onToggle={toggle} />
    </ChartCard>
  );
};
