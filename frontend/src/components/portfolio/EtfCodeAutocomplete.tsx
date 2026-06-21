import { useState, useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';

interface Props {
  value:    string;
  onChange: (code: string, isCovered: boolean) => void;
}

export const EtfCodeAutocomplete = ({ value, onChange }: Props) => {
  const data = useDataContext();
  const [query, setQuery] = useState(value);

  const allOptions = useMemo(() => {
    return (data?.etfs?.etfs ?? []).map((e) => ({
      code: e.code,
      name: e.name,
      covered: true,
    }));
  }, [data]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allOptions.slice(0, 8);
    return allOptions
      .filter(o => o.code.includes(q) || o.name.toLowerCase().includes(q))
      .slice(0, 8);
  }, [query, allOptions]);

  const handlePick = (code: string, isCovered: boolean) => {
    setQuery(code);
    onChange(code, isCovered);
  };

  const handleManualInput = (raw: string) => {
    setQuery(raw);
    // 任意 6 位代码都允许提交
    if (/^\d{6}$/.test(raw)) {
      const isCovered = allOptions.some(o => o.code === raw);
      onChange(raw, isCovered);
    }
  };

  return (
    <div className="relative">
      <input
        type="text"
        value={query}
        onChange={e => handleManualInput(e.target.value)}
        placeholder="ETF 代码或名称（如 512480、半导体）"
        className="w-full px-3 py-2 border rounded"
      />
      {filtered.length > 0 && query !== value && (
        <div className="absolute z-10 w-full mt-1 bg-white border rounded shadow-lg max-h-60 overflow-y-auto">
          {filtered.map(o => (
            <button
              key={o.code}
              type="button"
              onClick={() => handlePick(o.code, o.covered)}
              className="w-full text-left px-3 py-2 hover:bg-gray-100 flex justify-between items-center"
            >
              <span>{o.code} {o.name}</span>
              {o.covered && (
                <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">信号覆盖</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
