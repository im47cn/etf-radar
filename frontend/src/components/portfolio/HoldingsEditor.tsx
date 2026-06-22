import { useState } from 'react';
import { useHoldings } from '@/hooks/useHoldings';
import type { Holding } from '@/lib/portfolio/types';
import { EtfCodeAutocomplete } from './EtfCodeAutocomplete';

interface Props {
  open:    boolean;
  onClose: () => void;
  // 传入 = 编辑模式 (覆盖语义); 不传 = 新增模式 (合并语义)
  editing?: Holding | null;
}

// 外层只控制开关 + remount; 内层用 useState 初始化器纯派生 props, 无 effect.
// key 变化触发 remount, 切换"新增 ↔ 编辑" 或 切换不同 editing 行都会得到干净 state.
export const HoldingsEditor = ({ open, onClose, editing }: Props) => {
  if (!open) return null;
  return (
    <EditorForm
      key={editing ? `edit:${editing.id}` : 'new'}
      onClose={onClose}
      editing={editing ?? null}
    />
  );
};

interface FormProps {
  onClose: () => void;
  editing: Holding | null;
}

const EditorForm = ({ onClose, editing }: FormProps) => {
  const { upsert, update } = useHoldings();
  const isEdit = !!editing;
  const [code, setCode]       = useState(() => editing?.etf_code ?? '');
  const [isCovered, setCovered] = useState(false);
  const [shares, setShares]   = useState(() => editing ? String(editing.shares) : '');
  const [cost, setCost]       = useState(() => editing?.cost_price != null ? String(editing.cost_price) : '');
  const [note, setNote]       = useState(() => editing?.note ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg]         = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isEdit && !/^\d{6}$/.test(code)) {
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
    const costNum  = cost ? parseFloat(cost) : null;
    const costFinal = costNum && costNum > 0 ? costNum : null;

    if (isEdit && editing) {
      const { error } = await update(editing.etf_code, {
        shares:     sharesNum,
        cost_price: costFinal,
        note:       note || null,
      });
      setSubmitting(false);
      if (error) { setMsg(`保存失败：${error}`); return; }
      setMsg('✓ 已更新');
      setTimeout(() => { onClose(); }, 1000);
      return;
    }

    const { error, merged } = await upsert({
      etf_code:   code,
      shares:     sharesNum,
      cost_price: costFinal,
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
    setTimeout(() => { onClose(); }, 1200);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full">
        <div className="flex justify-between items-center p-4 border-b">
          <h3 className="text-lg font-semibold">{isEdit ? '编辑持仓' : '添加持仓'}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">✕</button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">ETF 代码或名称</label>
            {isEdit ? (
              <input
                type="text" value={code} readOnly
                className="w-full px-3 py-2 border rounded bg-gray-50 text-gray-700 cursor-not-allowed"
                aria-label="ETF 代码 (不可修改)"
              />
            ) : (
              <EtfCodeAutocomplete value={code} onChange={(c, covered) => { setCode(c); setCovered(covered); }} />
            )}
            {isEdit && (
              <p className="mt-1 text-xs text-gray-500">如需更改代码，请先删除后重新添加</p>
            )}
          </div>
          <div>
            <label htmlFor="shares" className="block text-sm font-medium mb-1">持有份额 *</label>
            <input
              id="shares" type="number" step="any" min="0.0001"
              value={shares} onChange={e => setShares(e.target.value)}
              className="w-full px-3 py-2 border rounded" required
            />
            {isEdit && (
              <p className="mt-1 text-xs text-gray-500">编辑模式将直接覆盖现有份额（非加仓合并）</p>
            )}
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
            <button type="button" onClick={onClose} className="px-4 py-2 border rounded">取消</button>
            <button type="submit" disabled={submitting} className="px-4 py-2 bg-blue-600 text-white rounded disabled:bg-gray-300">
              {submitting ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
