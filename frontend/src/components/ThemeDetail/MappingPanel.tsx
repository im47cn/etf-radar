import type { Theme } from '@/types/themes';

export const MappingPanel = ({
  theme,
  confidence,
}: {
  theme: Theme;
  confidence: number | null;
}) => (
  <div className="flex gap-4 text-sm">
    <div>
      <div className="text-xs text-gray-500">美股映射</div>
      <div className="font-medium">{theme.primary_us}</div>
      <div className="text-xs text-gray-500">{theme.us_etfs.join(' / ')}</div>
    </div>
    {confidence !== null && (
      <div>
        <div className="text-xs text-gray-500">置信度</div>
        <div className="text-2xl font-semibold">{confidence}</div>
      </div>
    )}
  </div>
);
