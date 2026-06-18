import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';
import { useSearchParams } from 'react-router-dom';
import { DimNameSchema, type DimName } from '@/types/themes';
import { SignalTypeSchema, type SignalType } from '@/types/signals';

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

const DEFAULT_DIM: DimName = 'short';
const DEFAULT_SIG: SignalFilter = 'all';

// 容错解析: 非法值统一回退默认, 避免外部输入污染 state.
function parseDim(s: string | null): DimName {
  const r = DimNameSchema.safeParse(s);
  return r.success ? r.data : DEFAULT_DIM;
}

function parseSig(s: string | null): SignalFilter {
  if (s === 'all') return 'all';
  const r = SignalTypeSchema.safeParse(s);
  return r.success ? r.data : DEFAULT_SIG;
}

const UIContext = createContext<{
  state: UIState;
  dispatch: React.Dispatch<Action>;
} | null>(null);

/**
 * URL 作为 selectedTheme / dim / sig 的单一事实来源,
 * 通过 react-router 的 useSearchParams 读写 (在 HashRouter 下作用于
 * `#/<path>?<query>` 的 query 段, 与路由 path 分离 -- 避免与 HashRouter
 * 抢占 `window.location.hash`).
 *
 * searchQuery 仅内存态: 输入高频且属个人查询, 不进 URL 历史.
 *
 * 默认值 (`dim=short`, `sig=all`) 不写入 URL, 保持 URL 简洁.
 * 写入一律用 `{ replace: true }`, 避免点击 bubble / 切 tab 污染浏览器历史.
 */
export const UIStateProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [params, setParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState('');

  // 关键: useSearchParams 每次 render 都返回新的 URLSearchParams 引用.
  // 直接以 params 作为 useMemo deps 等同于每 render 重算, memo 完全失效.
  // 因此先抽出 primitive string, 再以 string deps 触发 memo.
  const themeParam = params.get('theme');
  const dimParam = params.get('dim');
  const sigParam = params.get('sig');

  const state = useMemo<UIState>(
    () => ({
      selectedThemeId: themeParam || null,
      dimension: parseDim(dimParam),
      signalFilter: parseSig(sigParam),
      searchQuery,
    }),
    [themeParam, dimParam, sigParam, searchQuery],
  );

  const dispatch = useCallback<React.Dispatch<Action>>(
    (a) => {
      if (a.type === 'SET_SEARCH') {
        setSearchQuery(a.q);
        return;
      }
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          switch (a.type) {
            case 'SELECT_THEME':
              if (a.id) next.set('theme', a.id);
              else next.delete('theme');
              break;
            case 'SET_DIM':
              if (a.dim === DEFAULT_DIM) next.delete('dim');
              else next.set('dim', a.dim);
              break;
            case 'SET_SIGNAL_FILTER':
              if (a.v === DEFAULT_SIG) next.delete('sig');
              else next.set('sig', a.v);
              break;
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  // 内联对象字面量会让所有 useUIState 消费者在 provider 任意 render 时全量重渲;
  // memo 后只在 state / dispatch 引用变化时才推下游.
  const contextValue = useMemo(() => ({ state, dispatch }), [state, dispatch]);

  return (
    <UIContext.Provider value={contextValue}>{children}</UIContext.Provider>
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
