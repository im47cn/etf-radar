export const formatPct = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—';
  const pct = v * 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
};

export const formatYi = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—';
  return `${v.toFixed(1)}亿`;
};

export const formatStrength = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—';
  return Math.round(v).toString();
};

export const formatRelativeTime = (
  iso: string | null | undefined,
  now: Date = new Date(),
): string => {
  if (!iso) return '—';
  const ts = new Date(iso).getTime();
  const diffMin = Math.floor((now.getTime() - ts) / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}小时前`;
  const d = new Date(iso);
  const hh = d.getHours().toString().padStart(2, '0');
  const mm = d.getMinutes().toString().padStart(2, '0');
  return `${d.getMonth() + 1}-${d.getDate()} ${hh}:${mm}`;
};
