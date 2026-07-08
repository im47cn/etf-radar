import { useDataContext } from '@/providers/dataContext';

/** BJT 今日 (YYYY-MM-DD)。 */
const todayBjt = (): string =>
  new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date());

/**
 * 数据非今日时返回 "数据截至 MM-DD", 今日/缺失返回 null。
 * 纯函数, 便于测试。补足 StaleBanner 未覆盖的"正常但非今日"(周末/滞后) 提示。
 */
export const asOfLabel = (
  cnDataDate: string | null | undefined,
  today: string,
): string | null => {
  if (!cnDataDate || cnDataDate === today) return null;
  return `数据截至 ${cnDataDate.slice(5)}`;
};

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
