import type { Theme } from '@/types/themes';

export const MappingPanel = ({
  theme,
  confidence,
}: {
  theme: Theme;
  confidence: number | null;
}) => {
  if (theme.primary_us === null) {
    return (
      <div className="rounded border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
        本主题为 A 股本土赛道，无对应美股主题，故不展示映射相关字段。
      </div>
    );
  }
  return (
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
};
