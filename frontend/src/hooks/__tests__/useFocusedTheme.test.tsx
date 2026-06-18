import { renderHook, act } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useFocusedTheme } from '../useFocusedTheme';

describe('useFocusedTheme', () => {
  it('defaults to null', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai']) }));
    expect(result.current.focusedId).toBeNull();
  });

  it('setFocused updates id', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai']) }));
    act(() => result.current.setFocused('ai'));
    expect(result.current.focusedId).toBe('ai');
  });

  it('toggle sets id when null, clears when same', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai']) }));
    act(() => result.current.toggle('ai'));
    expect(result.current.focusedId).toBe('ai');
    act(() => result.current.toggle('ai'));
    expect(result.current.focusedId).toBeNull();
  });

  it('toggle swaps to different id', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai', 'semi']) }));
    act(() => result.current.toggle('ai'));
    act(() => result.current.toggle('semi'));
    expect(result.current.focusedId).toBe('semi');
  });

  it('ESC clears focus', () => {
    const { result } = renderHook(() => useFocusedTheme({ validThemeIds: new Set(['ai']) }));
    act(() => result.current.setFocused('ai'));
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(result.current.focusedId).toBeNull();
  });

  it('auto-clears when focusedId no longer in validThemeIds', () => {
    const { result, rerender } = renderHook(
      ({ ids }: { ids: Set<string> }) => useFocusedTheme({ validThemeIds: ids }),
      { initialProps: { ids: new Set(['ai']) } },
    );
    act(() => result.current.setFocused('ai'));
    rerender({ ids: new Set(['semi']) });
    expect(result.current.focusedId).toBeNull();
  });

  it('outside click clears focus when containerRef provided', () => {
    const inside = document.createElement('div');
    const outside = document.createElement('div');
    document.body.append(inside, outside);
    const containerRef = { current: inside };
    const { result } = renderHook(() =>
      useFocusedTheme({ validThemeIds: new Set(['ai']), containerRef }),
    );
    act(() => result.current.setFocused('ai'));
    act(() => {
      outside.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    expect(result.current.focusedId).toBeNull();
    inside.remove();
    outside.remove();
  });

  it('inside click keeps focus when containerRef provided', () => {
    const inside = document.createElement('div');
    document.body.append(inside);
    const containerRef = { current: inside };
    const { result } = renderHook(() =>
      useFocusedTheme({ validThemeIds: new Set(['ai']), containerRef }),
    );
    act(() => result.current.setFocused('ai'));
    act(() => {
      inside.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    expect(result.current.focusedId).toBe('ai');
    inside.remove();
  });
});
