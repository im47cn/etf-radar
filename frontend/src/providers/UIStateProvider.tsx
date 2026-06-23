import React, { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DimNameSchema, type DimName } from '@/types/themes';
import { SignalTypeSchema } from '@/types/signals';
import type { MarketView } from '@/lib/marketView';
import {
  UIContext,
  type SignalFilter,
  type UIState,
  type UIStateAction,
} from './uiStateContext';

const DEFAULT_DIM: DimName = 'short';
const DEFAULT_SIG: SignalFilter = 'all';
const DEFAULT_MV: MarketView = 'cn-all';

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

function parseMv(s: string | null): MarketView {
  if (s === 'cn-all' || s === 'us') return s;
  return DEFAULT_MV;
}

/**
 * URL 作为 selectedTheme / dim / sig / mv 的单一事实来源,
 * 通过 react-router 的 useSearchParams 读写 (在 HashRouter 下作用于
 * `#/<path>?<query>` 的 query 段, 与路由 path 分离 -- 避免与 HashRouter
 * 抢占 `window.location.hash`).
 *
 * searchQuery 仅内存态: 输入高频且属个人查询, 不进 URL 历史.
 *
 * 默认值 (`dim=short`, `sig=all`, `mv=cn-all`) 不写入 URL, 保持 URL 简洁.
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
  const mvParam = params.get('mv');

  const state = useMemo<UIState>(
    () => ({
      selectedThemeId: themeParam || null,
      dimension: parseDim(dimParam),
      signalFilter: parseSig(sigParam),
      searchQuery,
      marketView: parseMv(mvParam),
    }),
    [themeParam, dimParam, sigParam, mvParam, searchQuery],
  );

  const dispatch = useCallback<React.Dispatch<UIStateAction>>(
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
            case 'SET_MARKET_VIEW':
              if (a.v === DEFAULT_MV) next.delete('mv');
              else next.set('mv', a.v);
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
