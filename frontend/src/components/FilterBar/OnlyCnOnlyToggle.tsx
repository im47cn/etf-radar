import { useUIState } from '@/providers/uiStateContext';

export const OnlyCnOnlyToggle = () => {
  const { state, dispatch } = useUIState();
  return (
    <label className="inline-flex items-center gap-1 text-sm text-slate-600">
      <input
        type="checkbox"
        checked={state.onlyCnOnly}
        onChange={(e) =>
          dispatch({ type: 'SET_ONLY_CN_ONLY', v: e.target.checked })
        }
      />
      仅看 A 股专属
    </label>
  );
};
