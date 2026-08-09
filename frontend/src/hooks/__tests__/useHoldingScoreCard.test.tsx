import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useHoldingScoreCard } from '../useHoldingScoreCard';

describe('useHoldingScoreCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('初始 menuOpen 为 false', () => {
    const { result } = renderHook(() =>
      useHoldingScoreCard({ etfCode: '159870', onDelete: vi.fn() }),
    );
    expect(result.current.menuOpen).toBe(false);
  });

  it('setMenuOpen(true) 打开菜单', () => {
    const { result } = renderHook(() =>
      useHoldingScoreCard({ etfCode: '159870', onDelete: vi.fn() }),
    );
    act(() => result.current.setMenuOpen(true));
    expect(result.current.menuOpen).toBe(true);
  });

  it('handleEdit 无 onEdit 时不报错（?. 分支）', () => {
    const { result } = renderHook(() =>
      useHoldingScoreCard({ etfCode: '159870', onDelete: vi.fn() }),
    );
    act(() => result.current.setMenuOpen(true));
    act(() => result.current.handleEdit());
    expect(result.current.menuOpen).toBe(false);
  });

  it('handleEdit 有 onEdit 时调用 onEdit(code) 并关闭菜单', () => {
    const onEdit = vi.fn();
    const { result } = renderHook(() =>
      useHoldingScoreCard({ etfCode: '159870', onDelete: vi.fn(), onEdit }),
    );
    act(() => result.current.setMenuOpen(true));
    act(() => result.current.handleEdit());
    expect(onEdit).toHaveBeenCalledWith('159870');
    expect(result.current.menuOpen).toBe(false);
  });

  it('handleDelete confirm=true 时调用 onDelete', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const onDelete = vi.fn();
    const { result } = renderHook(() =>
      useHoldingScoreCard({ etfCode: '159870', onDelete }),
    );
    act(() => result.current.setMenuOpen(true));
    act(() => result.current.handleDelete());
    expect(onDelete).toHaveBeenCalledWith('159870');
    expect(result.current.menuOpen).toBe(false);
  });

  it('handleDelete confirm=false 时不调用 onDelete', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const onDelete = vi.fn();
    const { result } = renderHook(() =>
      useHoldingScoreCard({ etfCode: '159870', onDelete }),
    );
    act(() => result.current.setMenuOpen(true));
    act(() => result.current.handleDelete());
    expect(onDelete).not.toHaveBeenCalled();
    expect(result.current.menuOpen).toBe(false);
  });

  it('菜单打开时按 Escape 关闭', async () => {
    const { result } = renderHook(() =>
      useHoldingScoreCard({ etfCode: '159870', onDelete: vi.fn() }),
    );
    act(() => result.current.setMenuOpen(true));
    expect(result.current.menuOpen).toBe(true);

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    await waitFor(() => expect(result.current.menuOpen).toBe(false));
  });

  it('菜单打开时点击外部关闭（menuRef 有 DOM 时）', async () => {
    // menuRef.current 在 renderHook 中为 null，需要 mock contains 返回 false 模拟外部点击
    const fakeNode = { contains: () => false } as unknown as Node;
    const { result } = renderHook(() =>
      useHoldingScoreCard({ etfCode: '159870', onDelete: vi.fn() }),
    );
    act(() => result.current.setMenuOpen(true));
    // 手动注入 fake DOM 节点到 menuRef
    act(() => {
      (result.current.menuRef as React.MutableRefObject<Node | null>).current = fakeNode;
    });
    act(() => {
      document.dispatchEvent(new MouseEvent('mousedown'));
    });
    await waitFor(() => expect(result.current.menuOpen).toBe(false));
  });

  it('菜单打开时点击内部不关闭（contains=true 分支）', async () => {
    const fakeNode = { contains: () => true } as unknown as Node;
    const { result } = renderHook(() =>
      useHoldingScoreCard({ etfCode: '159870', onDelete: vi.fn() }),
    );
    act(() => result.current.setMenuOpen(true));
    act(() => {
      (result.current.menuRef as React.MutableRefObject<Node | null>).current = fakeNode;
    });
    act(() => {
      document.dispatchEvent(new MouseEvent('mousedown'));
    });
    // contains=true → 内部点击，菜单保持打开
    expect(result.current.menuOpen).toBe(true);
  });
});
