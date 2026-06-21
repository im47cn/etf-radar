import { createClient, SupabaseClient } from '@supabase/supabase-js';

const url     = import.meta.env.VITE_SUPABASE_URL ?? '';
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY ?? '';

let client: SupabaseClient | null = null;

export function isSupabaseConfigured(): boolean {
  return Boolean(url && anonKey);
}

export function getSupabase(): SupabaseClient {
  if (!isSupabaseConfigured()) {
    throw new Error(
      'SUPABASE_NOT_CONFIGURED: VITE_SUPABASE_URL 或 VITE_SUPABASE_ANON_KEY 未配置。' +
      '请在 frontend/.env.local 中填入凭据后重启 dev server。'
    );
  }
  if (!client) {
    client = createClient(url, anonKey, {
      auth: {
        persistSession:  true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }
  return client;
}
