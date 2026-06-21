import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('supabase client', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('isSupabaseConfigured returns false when env missing', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', '');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '');
    const mod = await import('../supabase');
    expect(mod.isSupabaseConfigured()).toBe(false);
  });

  it('isSupabaseConfigured returns true when env present', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://test.supabase.co');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'fake-anon-key');
    const mod = await import('../supabase');
    expect(mod.isSupabaseConfigured()).toBe(true);
    expect(mod.getSupabase()).toBeDefined();
  });

  it('getSupabase throws when not configured', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', '');
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '');
    const mod = await import('../supabase');
    expect(() => mod.getSupabase()).toThrow(/SUPABASE/);
  });
});
