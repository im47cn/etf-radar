import { useEffect, useRef, useState } from 'react';

interface Params {
  etfCode: string;
  onDelete: (etfCode: string) => void;
  onEdit?: (etfCode: string) => void;
}

// kebab 菜单开关 + outside click/Esc 关闭 + 删除确认/编辑派发，从 HoldingScoreCard 抽出的纯状态逻辑
export const useHoldingScoreCard = ({ etfCode, onDelete, onEdit }: Params) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

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
    if (window.confirm(`确定删除 ${etfCode} 的持仓记录吗？此操作不可恢复。`)) {
      onDelete(etfCode);
    }
  };

  const handleEdit = () => {
    setMenuOpen(false);
    onEdit?.(etfCode);
  };

  return { menuOpen, setMenuOpen, menuRef, handleDelete, handleEdit };
};
