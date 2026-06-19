import { useDataContext } from '@/providers/dataContext';
import { Alert, AlertDescription } from '@/components/ui/alert';

export const StaleBanner = () => {
  const { meta } = useDataContext();
  if (!meta) return null;

  const stale = meta.stale_minutes > 60;
  const degraded = meta.failed_symbols.length > 0;
  const fallbackCount = Object.keys(meta.fallback_symbols ?? {}).length;
  const fallback = fallbackCount > 0;

  if (!stale && !degraded && !fallback) return null;

  let variant: 'default' | 'warning' | 'destructive';
  let message: string;
  if (stale) {
    variant = 'destructive';
    message = `数据获取异常 — 已过期 ${meta.stale_minutes} 分钟`;
  } else if (degraded) {
    variant = 'destructive';
    message = `Provider 降级: ${meta.failed_symbols.join(', ')}`;
  } else {
    variant = 'warning';
    message = `${fallbackCount} ETF 使用备用数据源`;
  }

  return (
    <Alert variant={variant} className="mt-2">
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
};
