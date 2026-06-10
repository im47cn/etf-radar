import { useUIState } from '@/providers/UIStateProvider';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type { SignalType } from '@/types/signals';

type SignalFilter = 'all' | SignalType;

const OPTS: Array<{ key: SignalFilter; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'resonance', label: '共振' },
  { key: 'transmission', label: '传导' },
  { key: 'divergence', label: '背离' },
];

export const SignalTabs = () => {
  const { state, dispatch } = useUIState();
  return (
    <Tabs
      value={state.signalFilter}
      onValueChange={(v) => dispatch({ type: 'SET_SIGNAL_FILTER', v: v as SignalFilter })}
    >
      <TabsList>
        {OPTS.map((o) => (
          <TabsTrigger key={o.key} value={o.key}>
            {o.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
};
