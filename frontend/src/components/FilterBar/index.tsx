import { DimensionTabs } from './DimensionTabs';
import { SignalTabs } from './SignalTabs';
import { SearchInput } from './SearchInput';
import { Legend } from './Legend';
import { OnlyCnOnlyToggle } from './OnlyCnOnlyToggle';

export const FilterBar = () => (
  <div className="bg-white border-b p-3 flex flex-wrap items-center gap-4">
    <DimensionTabs />
    <SignalTabs />
    <OnlyCnOnlyToggle />
    <Legend />
    <div className="ml-auto">
      <SearchInput />
    </div>
  </div>
);
