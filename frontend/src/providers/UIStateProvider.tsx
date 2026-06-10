import React, { createContext, useContext, useEffect, useReducer } from 'react';
import type { DimName } from '@/types/themes';
import type { SignalType } from '@/types/signals';

type SignalFilter = 'all' | SignalType;

interface UIState {
  selectedThemeId: string | null;
  dimension: DimName;
  signalFilter: SignalFilter;
  searchQuery: string;
}

type Action =
  | { type: 'SELECT_THEME'; id: string | null }
  | { type: 'SET_DIM'; dim: DimName }
  | { type: 'SET_SIGNAL_FILTER'; v: SignalFilter }
  | { type: 'SET_SEARCH'; q: string };

const initial: UIState = {
  selectedThemeId: null,
  dimension: 'short',
  signalFilter: 'all',
  searchQuery: '',
};

function reducer(s: UIState, a: Action): UIState {
  switch (a.type) {
    case 'SELECT_THEME':
      return { ...s, selectedThemeId: a.id };
    case 'SET_DIM':
      return { ...s, dimension: a.dim };
    case 'SET_SIGNAL_FILTER':
      return { ...s, signalFilter: a.v };
    case 'SET_SEARCH':
      return { ...s, searchQuery: a.q };
  }
}

const UIContext = createContext<{
  state: UIState;
  dispatch: React.Dispatch<Action>;
} | null>(null);

function parseHash(): Partial<UIState> {
  if (typeof window === 'undefined') return {};
  const h = new URLSearchParams(window.location.hash.slice(1));
  const theme = h.get('theme');
  const dim = h.get('dim') as DimName | null;
  const sig = h.get('sig') as SignalFilter | null;
  return {
    selectedThemeId: theme,
    dimension: dim ?? 'short',
    signalFilter: sig ?? 'all',
  };
}

export const UIStateProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [state, dispatch] = useReducer(reducer, { ...initial, ...parseHash() });

  useEffect(() => {
    const p = new URLSearchParams();
    if (state.selectedThemeId) p.set('theme', state.selectedThemeId);
    if (state.dimension !== 'short') p.set('dim', state.dimension);
    if (state.signalFilter !== 'all') p.set('sig', state.signalFilter);
    const hash = p.toString();
    if (hash !== window.location.hash.slice(1)) {
      window.history.replaceState(
        null,
        '',
        hash ? `#${hash}` : window.location.pathname,
      );
    }
  }, [state.selectedThemeId, state.dimension, state.signalFilter]);

  return (
    <UIContext.Provider value={{ state, dispatch }}>{children}</UIContext.Provider>
  );
};

export const useUIState = (): {
  state: UIState;
  dispatch: React.Dispatch<Action>;
} => {
  const c = useContext(UIContext);
  if (!c) throw new Error('useUIState must be inside UIStateProvider');
  return c;
};
