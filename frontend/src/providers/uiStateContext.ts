import { createContext, useContext } from 'react';
import type { DimName } from '@/types/themes';
import type { SignalType } from '@/types/signals';

export type SignalFilter = 'all' | SignalType;

export interface UIState {
  selectedThemeId: string | null;
  dimension: DimName;
  signalFilter: SignalFilter;
  searchQuery: string;
}

export type UIStateAction =
  | { type: 'SELECT_THEME'; id: string | null }
  | { type: 'SET_DIM'; dim: DimName }
  | { type: 'SET_SIGNAL_FILTER'; v: SignalFilter }
  | { type: 'SET_SEARCH'; q: string };

export const UIContext = createContext<{
  state: UIState;
  dispatch: React.Dispatch<UIStateAction>;
} | null>(null);

export const useUIState = (): {
  state: UIState;
  dispatch: React.Dispatch<UIStateAction>;
} => {
  const c = useContext(UIContext);
  if (!c) throw new Error('useUIState must be inside UIStateProvider');
  return c;
};
