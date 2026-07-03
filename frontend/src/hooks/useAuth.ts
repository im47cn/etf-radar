import { useContext } from 'react';
import { AuthContext } from '@/providers/authContext';

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within <AuthProvider>');
  }
  return ctx;
}

// 可选变体：AuthProvider 缺失时返回 null 而非抛错。
// 供可能渲染在 provider 外的通用组件使用（如嵌入各页的自选按钮）。
export function useAuthOptional() {
  return useContext(AuthContext);
}
