import { useEffect, useState, useCallback, type ReactNode } from 'react';
import type { User } from '@supabase/supabase-js';
import { isSupabaseConfigured, getSupabase } from '@/lib/supabase';
import { AuthContext, type AuthStatus } from './authContext';

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  // 懒初始化: 配置缺失时直接落到 'unconfigured', 避免 effect 内 setState 引起级联渲染
  const [status, setStatus] = useState<AuthStatus>(() =>
    isSupabaseConfigured() ? 'loading' : 'unconfigured',
  );
  const [user, setUser]     = useState<User | null>(null);

  useEffect(() => {
    if (!isSupabaseConfigured()) return;
    const supabase = getSupabase();
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setStatus(session?.user ? 'authenticated' : 'anonymous');
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setUser(session?.user ?? null);
        setStatus(session?.user ? 'authenticated' : 'anonymous');
      }
    );
    return () => subscription.unsubscribe();
  }, []);

  const signInWithMagicLink = useCallback(async (email: string) => {
    if (!isSupabaseConfigured()) return { error: '未配置 Supabase' };
    const { error } = await getSupabase().auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/etf-radar/#/auth/callback` },
    });
    return { error: error?.message ?? null };
  }, []);

  const signInWithGoogle = useCallback(async () => {
    if (!isSupabaseConfigured()) return { error: '未配置 Supabase' };
    const { error } = await getSupabase().auth.signInWithOAuth({
      provider: 'google',
      options:  { redirectTo: `${window.location.origin}/etf-radar/#/auth/callback` },
    });
    return { error: error?.message ?? null };
  }, []);

  const signOut = useCallback(async () => {
    if (!isSupabaseConfigured()) return;
    await getSupabase().auth.signOut();
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, signInWithMagicLink, signInWithGoogle, signOut }}>
      {children}
    </AuthContext.Provider>
  );
};
