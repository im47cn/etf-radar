import { useDataContext } from '@/providers/dataContext';
import { asOfLabel, todayBjt } from './asOfLabel';

export const AsOfBadge = () => {
  const { meta } = useDataContext();
  if (!meta) return null;
  // 与 StaleBanner 去重: 后者已触发(陈旧/降级/备用源)时不再重复展示 as-of。
  // 仅在"正常但非今日"(周末/滞后, StaleBanner 静默)场景补足提示。
  const staleBannerActive =
    meta.stale_minutes > 60 ||
    meta.failed_symbols.length > 0 ||
    Object.keys(meta.fallback_symbols ?? {}).length > 0;
  if (staleBannerActive) return null;
  const label = asOfLabel(meta.cn_data_date, todayBjt());
  if (!label) return null;
  return (
    <div className="text-xs text-amber-600" data-testid="asof-badge">
      {label}
    </div>
  );
};
