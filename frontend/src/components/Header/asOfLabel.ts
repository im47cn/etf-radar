/** BJT 今日 (YYYY-MM-DD)。 */
export const todayBjt = (): string =>
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
