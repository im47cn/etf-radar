import { useUIState } from '@/providers/uiStateContext';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { DimName } from '@/types/themes';

const DIMS: Array<{ key: DimName; label: string }> = [
  { key: 'short', label: '短期' },
  { key: 'mid', label: '中期' },
  { key: 'long', label: '长期' },
  { key: 'composite', label: '综合' },
];

export const DimensionTabs = () => {
  const { state, dispatch } = useUIState();
  return (
    <Tabs
      value={state.dimension}
      onValueChange={(v) => dispatch({ type: 'SET_DIM', dim: v as DimName })}
    >
      <TabsList>
        {DIMS.map((d) => (
          <TabsTrigger key={d.key} value={d.key}>
            {d.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
};
