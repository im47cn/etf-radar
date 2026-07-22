import type { RefObject } from 'react';

interface Props {
  menuOpen: boolean;
  menuRef: RefObject<HTMLDivElement | null>;
  onToggle: () => void;
  onEditClick?: () => void;
  onDeleteClick: () => void;
}

// kebab 菜单触发器 + 下拉（编辑/删除），编辑项仅在 onEditClick 存在时渲染
export const HoldingScoreCardActions = ({ menuOpen, menuRef, onToggle, onEditClick, onDeleteClick }: Props) => (
  <div className="relative ml-1" ref={menuRef}>
    <button
      type="button"
      onClick={onToggle}
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
        {onEditClick && (
          <button
            type="button" role="menuitem"
            onClick={onEditClick}
            className="block w-full text-left px-3 py-1.5 hover:bg-gray-50"
          >
            ✏️ 编辑
          </button>
        )}
        <button
          type="button" role="menuitem"
          onClick={onDeleteClick}
          className="block w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-600"
        >
          🗑 删除
        </button>
      </div>
    )}
  </div>
);
