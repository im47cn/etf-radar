import { useEffect, useRef, useState } from 'react';
import type { HoldingScore } from '@/lib/portfolio/types';

interface Props {
  score:    HoldingScore;
  onDelete: (etfCode: string) => void;
  onEdit?:  (etfCode: string) => void;
}

const tagColor = (tag?: string) => {
  switch (tag) {
    case '偏强':       return 'bg-green-100 text-green-700';
    case '中性偏强':   return 'bg-green-50 text-green-600';
    case '中性偏弱':   return 'bg-orange-50 text-orange-600';
    case '偏弱':       return 'bg-red-100 text-red-700';
    case '动量向上':   return 'bg-blue-100 text-blue-700';
    case '动量向下':   return 'bg-amber-100 text-amber-700';
    default:           return 'bg-gray-100 text-gray-600';
  }
};

const fmtPct = (n: number | null) => n === null ? '—' : `${(n * 100).toFixed(1)}%`;
const fmtMoney = (n: number | null) => n === null ? '—' : `¥${n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;

export const HoldingScoreCard = ({ score, onDelete, onEdit }: Props) => {
  const isUncovered = score.status === 'uncovered';
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Outside click / Esc 关闭菜单 — 订阅 DOM, 合法 effect 用法
  useEffect(() => {
    if (!menuOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false); };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  const handleDelete = () => {
    setMenuOpen(false);
    if (window.confirm(`确定删除 ${score.etfCode} 的持仓记录吗？此操作不可恢复。`)) {
      onDelete(score.etfCode);
    }
  };

  const handleEdit = () => {
    setMenuOpen(false);
    onEdit?.(score.etfCode);
  };

  return (
    <div className={`border rounded-lg p-4 ${isUncovered ? 'bg-gray-50 opacity-90' : 'bg-white'}`}>
      {/* Header */}
      <div className="flex justify-between items-start mb-2">
        <div>
          <div className="font-semibold">{score.etfCode}</div>
          {score.name && <div className="text-sm text-gray-600">{score.name}</div>}
        </div>
        <div className="flex flex-wrap gap-1 items-start">
          {isUncovered ? (
            <span className="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-600">无信号</span>
          ) : (
            <>
              {score.l2Tag && <span className={`text-xs px-2 py-0.5 rounded ${tagColor(score.l2Tag)}`}>{score.l2Tag}</span>}
              {score.momentumTag && <span className={`text-xs px-2 py-0.5 rounded ${tagColor(score.momentumTag)}`}>{score.momentumTag}</span>}
            </>
          )}
          {/* kebab 菜单 — 触发器始终显示, 编辑/删除收纳其中 */}
          <div className="relative ml-1" ref={menuRef}>
            <button
              type="button"
              onClick={() => setMenuOpen(o => !o)}
              title="操作" aria-label="操作菜单"
              aria-haspopup="menu" aria-expanded={menuOpen}
              className="text-gray-400 hover:text-gray-700 text-sm px-1 leading-none"
            >
              ⋯
            </button>
            {menuOpen && (
              <div
                role="menu"
                className="absolute right-0 mt-1 w-28 bg-white border border-gray-200 rounded shadow-lg z-10 py-1 text-sm"
              >
                {onEdit && (
                  <button
                    type="button" role="menuitem"
                    onClick={handleEdit}
                    className="block w-full text-left px-3 py-1.5 hover:bg-gray-50"
                  >
                    ✏️ 编辑
                  </button>
                )}
                <button
                  type="button" role="menuitem"
                  onClick={handleDelete}
                  className="block w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-600"
                >
                  🗑 删除
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 持仓 */}
      <div className="text-sm space-y-1 border-t pt-2">
        <div>持仓 {score.shares} 份 {score.costPrice !== null && `· 成本 ${fmtMoney(score.costPrice)}`}</div>
        {score.currentPrice !== null && (
          <div>现价 {fmtMoney(score.currentPrice)} · 市值 {fmtMoney(score.marketValue)}</div>
        )}
        {score.pnlAbs !== null && score.pnlPct !== null && (
          <div className={score.pnlAbs >= 0 ? 'text-green-600' : 'text-red-600'}>
            盈亏 {score.pnlAbs >= 0 ? '+' : ''}{fmtMoney(score.pnlAbs)} ({score.pnlAbs >= 0 ? '+' : ''}{fmtPct(score.pnlPct)})
          </div>
        )}
      </div>

      {/* uncovered 提示 */}
      {isUncovered && (
        <div className="mt-3 pt-2 border-t text-xs text-gray-500">
          ⓘ 该 ETF 不在信号覆盖范围（14 主题外），仅记录持仓信息
        </div>
      )}

      {/* covered: 信号区 — 三段独立渲染, 缺主题归属时仍展示自身百分位与 narrative */}
      {!isUncovered && (
        <div className="mt-3 pt-2 border-t text-sm space-y-2">
          {score.themeName ? (
            <div className="text-gray-600">归属主题：<span className="font-medium text-gray-900">{score.themeName}</span></div>
          ) : (
            <div className="text-xs text-gray-400">ⓘ 未归入主题分组（暂无双轨信号）</div>
          )}

          {score.selfStrength && (
            <div className={`grid ${score.themeUsStrength ? 'grid-cols-2' : 'grid-cols-1'} gap-2 text-xs`}>
              {score.themeUsStrength && (
                <div className="border rounded p-2">
                  <div className="text-gray-500 mb-1">双轨强度（美/A）</div>
                  <div>美 短{score.themeUsStrength.short} 中{score.themeUsStrength.mid} 长{score.themeUsStrength.long}</div>
                  {score.themeCnStrength && (
                    <div>A 短{score.themeCnStrength.short} 中{score.themeCnStrength.mid} 长{score.themeCnStrength.long}</div>
                  )}
                </div>
              )}
              <div className="border rounded p-2">
                <div className="text-gray-500 mb-1">ETF 自身百分位</div>
                <div>短 {score.selfStrength.short}</div>
                <div>中 {score.selfStrength.mid}</div>
                <div>长 {score.selfStrength.long}</div>
                <div>综合 {score.selfStrength.composite}</div>
              </div>
            </div>
          )}

          {score.narrative && (
            <div className="text-gray-700 text-xs leading-relaxed bg-gray-50 p-2 rounded">
              {score.narrative}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
