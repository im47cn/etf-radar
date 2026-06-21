import { createContext } from 'react';
import type { User } from '@supabase/supabase-js';

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'unconfigured';

export interface AuthContextValue {
  status: AuthStatus;
  user:   User | null;
  signInWithMagicLink: (email: string) => Promise<{ error: string | null }>;
  signInWithGoogle:    () => Promise<{ error: string | null }>;
  signOut:             () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
