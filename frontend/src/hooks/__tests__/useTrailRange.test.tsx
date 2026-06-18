import { renderHook, act } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useTrailRange } from '../useTrailRange';

describe('useTrailRange', () => {
  it('defaults to startOffset=-10, endOffset=0', () => {
    const { result } = renderHook(() => useTrailRange());
    expect(result.current.range).toEqual({ startOffset: -10, endOffset: 0 });
  });

  it('setRange updates state when valid', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -30, endOffset: 0 }));
    expect(result.current.range).toEqual({ startOffset: -30, endOffset: 0 });
  });

  it('clamps startOffset to lower bound -60', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -100, endOffset: 0 }));
    expect(result.current.range.startOffset).toBe(-60);
  });

  it('clamps endOffset to upper bound 0', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -10, endOffset: 5 }));
    expect(result.current.range.endOffset).toBe(0);
  });

  it('rejects invalid range where startOffset >= endOffset (keeps prev)', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: 0, endOffset: 0 }));
    expect(result.current.range).toEqual({ startOffset: -10, endOffset: 0 });
  });

  it('reset returns to default', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -30, endOffset: -5 }));
    act(() => result.current.reset());
    expect(result.current.range).toEqual({ startOffset: -10, endOffset: 0 });
  });

  it('rejects degenerate input at lower bound (endOffset below MIN_START)', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -10, endOffset: -100 }));
    expect(result.current.range).toEqual({ startOffset: -10, endOffset: 0 });
  });

  it('rejects degenerate input where both bounds are below MIN_START', () => {
    const { result } = renderHook(() => useTrailRange());
    act(() => result.current.setRange({ startOffset: -100, endOffset: -100 }));
    expect(result.current.range).toEqual({ startOffset: -10, endOffset: 0 });
  });
});
