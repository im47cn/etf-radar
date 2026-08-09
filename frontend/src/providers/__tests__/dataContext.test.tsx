import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { DataContext, useDataContext, type DataContextValue } from '../dataContext';

describe('useDataContext', () => {
  it('在 Provider 内返回 context 值', () => {
    const value: DataContextValue = {
      isLoading: false,
      error: null,
    };
    const { result } = renderHook(() => useDataContext(), {
      wrapper: ({ children }) => (
        <DataContext.Provider value={value}>{children}</DataContext.Provider>
      ),
    });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('在 Provider 外抛错（throw 分支）', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => renderHook(() => useDataContext())).toThrow(
      'useDataContext must be inside DataProvider',
    );
    spy.mockRestore();
  });
});
