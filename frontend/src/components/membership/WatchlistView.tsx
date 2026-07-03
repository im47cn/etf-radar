import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import { useWatchlist } from '@/lib/watchlist/useWatchlist';
import { strengthTag } from '@/lib/portfolio/rules';
import { Disclaimer } from './Disclaimer';

// 自选项解析为「名称 + 客观强度状态」。文案只描述状态，无操作动词。
interface ResolvedRow {
  id:        string;
  kind:      'theme' | 'etf';
  key:       string;
  name:      string;
  composite: number | null;
}

const StrengthBadge = ({ composite }: { composite: number | null }) => {
  if (composite === null) {
    return <span className="text-xs text-gray-400">暂无数据</span>;
  }
  const tag = strengthTag(composite);
  const color =
    tag === '偏强'       ? 'bg-red-100 text-red-700'
    : tag === '中性偏强' ? 'bg-orange-100 text-orange-700'
    : tag === '中性偏弱' ? 'bg-blue-100 text-blue-700'
    : 'bg-green-100 text-green-700';
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${color}`}>
      {tag}（{composite}）
    </span>
  );
};

export const WatchlistView = () => {
  const { themes, etfs } = useDataContext();
  const { items, loading, remove } = useWatchlist();

  const rows = useMemo<ResolvedRow[]>(() => {
    const themeMap = new Map(themes?.themes.map(t => [t.id, t]) ?? []);
    const etfMap   = new Map(etfs?.etfs.map(e => [e.code, e]) ?? []);
    return items.map(it => {
      if (it.item_type === 'theme') {
        const t = themeMap.get(it.item_key);
        return {
          id: it.id, kind: 'theme', key: it.item_key,
          name: t?.name ?? it.item_key,
          composite: t?.strength.composite ?? null,
        };
      }
      const e = etfMap.get(it.item_key);
      return {
        id: it.id, kind: 'etf', key: it.item_key,
        name: e?.name ?? it.item_key,
        composite: e?.strength.composite ?? null,
      };
    });
  }, [items, themes, etfs]);

  return (
    <div className="max-w-2xl mx-auto p-6 bg-white border rounded-lg shadow-sm">
      <h1 className="text-2xl font-bold mb-1">我的自选</h1>
      <p className="text-sm text-gray-600 mb-4">
        以下为您自选的主题 / ETF 及其当前客观强度状态。
      </p>

      {loading && <div className="text-gray-500">加载中...</div>}

      {!loading && rows.length === 0 && (
        <div className="text-gray-500 text-sm">
          还没有自选项。在主题轮动或跨市雷达页把关注的项加入自选。
        </div>
      )}

      <ul className="divide-y">
        {rows.map(r => (
          <li key={r.id} className="flex items-center justify-between py-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">{r.kind === 'theme' ? '主题' : 'ETF'}</span>
              <span className="font-medium">{r.name}</span>
              <span className="text-xs text-gray-400">{r.key}</span>
            </div>
            <div className="flex items-center gap-3">
              <StrengthBadge composite={r.composite} />
              <button
                onClick={() => remove(r.id)}
                className="text-xs text-gray-400 hover:text-red-600"
              >
                移除
              </button>
            </div>
          </li>
        ))}
      </ul>

      <Disclaimer />
    </div>
  );
};
