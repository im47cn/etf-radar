import { useDataContext } from '@/providers/DataProvider';
import { Alert, AlertDescription } from '@/components/ui/alert';

export const StaleBanner = () => {
  const { meta } = useDataContext();
  if (!meta) return null;
  const degraded =
    meta.providers.us.status !== 'ok' || meta.providers.cn.status !== 'ok';
  const stale = meta.stale_minutes > 60;
  if (!degraded && !stale) return null;
  return (
    <Alert variant={stale ? 'destructive' : 'default'} className="mt-2">
      <AlertDescription>
        {stale
          ? `数据获取异常 — 已过期 ${meta.stale_minutes} 分钟`
          : `Provider 降级: ${meta.failed_symbols.join(', ')}`}
      </AlertDescription>
    </Alert>
  );
};
