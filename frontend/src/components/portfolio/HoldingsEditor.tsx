import { useState } from 'react';
import { useHoldings } from '@/hooks/useHoldings';
import { EtfCodeAutocomplete } from './EtfCodeAutocomplete';

interface Props {
  open:    boolean;
  onClose: () => void;
}

export const HoldingsEditor = ({ open, onClose }: Props) => {
  const { upsert } = useHoldings();
  const [code, setCode]       = useState('');
  const [isCovered, setCovered] = useState(false);
  const [shares, setShares]   = useState('');
  const [cost, setCost]       = useState('');
  const [note, setNote]       = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg]         = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      setMsg('请输入 6 位 ETF 代码');
      return;
    }
    const sharesNum = parseFloat(shares);
    if (!sharesNum || sharesNum <= 0) {
      setMsg('请输入有效份额');
      return;
    }
    setSubmitting(true);
    setMsg(null);
    const costNum = cost ? parseFloat(cost) : null;
    const { error, merged } = await upsert({
      etf_code:   code,
      shares:     sharesNum,
      cost_price: costNum && costNum > 0 ? costNum : null,
      note:       note || null,
    });
    setSubmitting(false);
    if (error) {
      setMsg(`保存失败：${error}`);
      return;
    }
    if (!isCovered) {
      setMsg('✓ 已保存（该 ETF 不在 14 主题覆盖范围内，仅记录持仓）');
    } else if (merged) {
      setMsg('✓ 已合并到现有持仓');
    } else {
      setMsg('✓ 已保存');
    }
    // 短暂展示后关闭
    setTimeout(() => { resetAndClose(); }, 1200);
  };

  const resetAndClose = () => {
    setCode(''); setCovered(false); setShares(''); setCost(''); setNote(''); setMsg(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
        <div className="flex justify-between items-center p-4 border-b">
          <h3 className="text-lg font-semibold">添加持仓</h3>
          <button onClick={resetAndClose} className="text-gray-400 hover:text-gray-700">✕</button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">ETF 代码或名称</label>
            <EtfCodeAutocomplete value={code} onChange={(c, covered) => { setCode(c); setCovered(covered); }} />
          </div>
          <div>
            <label htmlFor="shares" className="block text-sm font-medium mb-1">持有份额 *</label>
            <input
              id="shares" type="number" step="any" min="0.0001"
              value={shares} onChange={e => setShares(e.target.value)}
              className="w-full px-3 py-2 border rounded" required
            />
          </div>
          <div>
            <label htmlFor="cost" className="block text-sm font-medium mb-1">平均成本（可选）</label>
            <input
              id="cost" type="number" step="any" min="0"
              value={cost} onChange={e => setCost(e.target.value)}
              className="w-full px-3 py-2 border rounded"
            />
          </div>
          <div>
            <label htmlFor="note" className="block text-sm font-medium mb-1">备注（可选）</label>
            <textarea
              id="note" rows={2}
              value={note} onChange={e => setNote(e.target.value)}
              className="w-full px-3 py-2 border rounded"
            />
          </div>
          {msg && (
            <div className={`text-sm ${msg.startsWith('✓') ? 'text-green-600' : 'text-red-600'}`}>
              {msg}
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={resetAndClose} className="px-4 py-2 border rounded">取消</button>
            <button type="submit" disabled={submitting} className="px-4 py-2 bg-blue-600 text-white rounded disabled:bg-gray-300">
              {submitting ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
