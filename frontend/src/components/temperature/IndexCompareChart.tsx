import { useMemo, useState } from 'react';
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
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

// 默认仅显示宽度(始终) + 上证指数 + 创业板指 (大盘代表 + 成长代表, 风格不重叠);
// 深成/沪深300/科创50/科创100 默认隐藏, 用户点图例按需展开.
const DEFAULT_HIDDEN = new Set<string>(['399001', '000300', '000688', '000698']);

interface LegendPayloadItem {
  dataKey?: string | number;
  value?: string | number;
  color?: string;
}

interface CustomLegendProps {
  hidden: Set<string>;
  onToggle: (key: string) => void;
  payload?: LegendPayloadItem[];
}

const CustomLegend = ({ hidden, onToggle, payload }: CustomLegendProps) => (
  <div className="mt-2 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px]">
    {(payload ?? []).map((entry, i) => {
      const key = String(entry.dataKey ?? '');
      const isRate = key === RATE_KEY;
      const isHidden = !isRate && hidden.has(key);
      return (
        <button
          key={key || i}
          type="button"
          onClick={() => onToggle(key)}
          disabled={isRate}
          className={`flex items-center gap-1 transition-opacity ${
            isHidden ? 'opacity-30' : 'opacity-100 hover:text-gray-900'
          } ${isRate ? 'cursor-default' : 'cursor-pointer'}`}
        >
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span>{entry.value}</span>
        </button>
      );
    })}
  </div>
);

/** 温度页对比图: 左轴宽度站上率% + 右轴 A 股主要指数点位, 双 Y 轴看背离. */
export const IndexCompareChart = ({ market, indices }: Props) => {
  const [hidden, setHidden] = useState<Set<string>>(DEFAULT_HIDDEN);

  const data = useMemo(() => {
    const rows: Array<Record<string, number | string | null>> = [];
    for (let i = 0; i < market.length; i++) {
      const row: Record<string, number | string | null> = {
        date: market[i]?.date ?? '',
        [RATE_KEY]: market[i]?.rate ?? null,
      };
      for (const idx of indices) {
        row[idx.code] = idx.series[i] ?? null;
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
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">宽度 vs A 股主要指数</h2>
        <span className="text-[10px] text-gray-400">左轴: 站上率% · 右轴: 指数点位(对数) · 点击图例切换</span>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 10 }} />
          <YAxis yAxisId="breadth" domain={[0, 100]} unit="%" tick={{ fontSize: 10 }} width={40} />
          {/* 右轴对数: 6 只指数点位量级跨度大 (科创~1800 → 深成~14000), log 铺开后各线趋势均可辨.
              domain 取 1000 的整数倍下取/上取整, 保证正域且留余量. */}
          <YAxis
            yAxisId="price"
            orientation="right"
            scale="log"
            domain={[
              (dataMin: number) => Math.floor(dataMin / 1000) * 1000,
              (dataMax: number) => Math.ceil(dataMax / 1000) * 1000,
            ]}
            allowDataOverflow
            tick={{ fontSize: 10 }}
            width={52}
          />
          <Tooltip />
          <Legend content={<CustomLegend hidden={hidden} onToggle={toggle} />} />
          <Line
            yAxisId="breadth"
            dataKey={RATE_KEY}
            name={RATE_LABEL}
            stroke="#1e293b"
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
    </div>
  );
};
