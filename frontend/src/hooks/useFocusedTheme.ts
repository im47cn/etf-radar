import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

export interface UseFocusedThemeOptions {
  validThemeIds: Set<string>;
  /**
   * 容器引用; 当用户点击该容器之外时, 自动退焦.
   * 容器内部的"非聚焦目标"区域 (例如 ScatterChart 网格空白处) 由组件自身决定是否阻止冒泡.
   */
  containerRef?: React.RefObject<HTMLElement | null>;
}

export interface UseFocusedThemeReturn {
  focusedId: string | null;
  setFocused: (id: string | null) => void;
  toggle: (id: string) => void;
}

export function useFocusedTheme(opts: UseFocusedThemeOptions): UseFocusedThemeReturn {
  const [storedId, setStoredId] = useState<string | null>(null);
  const focusedIdRef = useRef<string | null>(null);

  const focusedId = useMemo(
    () => (storedId !== null && opts.validThemeIds.has(storedId) ? storedId : null),
    [storedId, opts.validThemeIds],
  );

  useEffect(() => {
    focusedIdRef.current = focusedId;
  }, [focusedId]);

  const setFocused = useCallback((id: string | null) => setStoredId(id), []);
  const toggle = useCallback(
    (id: string) => setStoredId(prev => (prev === id ? null : id)),
    [],
  );

  // ESC 退焦
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setStoredId(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // 外部点击退焦: 仅当 containerRef 提供时启用
  useEffect(() => {
    const containerRef = opts.containerRef;
    if (!containerRef) return;
    const onDown = (e: MouseEvent) => {
      if (focusedIdRef.current === null) return;
      const el = containerRef.current;
      if (!el) return;
      if (!(e.target instanceof Node)) return;
      if (!el.contains(e.target)) setStoredId(null);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [opts.containerRef]);

  return { focusedId, setFocused, toggle };
}
