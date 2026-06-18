import { useUIState } from '@/providers/uiStateContext';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';

export const SearchInput = () => {
  const { state, dispatch } = useUIState();
  return (
    <div className="relative max-w-sm">
      <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
      <Input
        value={state.searchQuery}
        onChange={(e) => dispatch({ type: 'SET_SEARCH', q: e.target.value })}
        placeholder="搜索主题、代码或ETF名称"
        className="pl-8"
      />
    </div>
  );
};
