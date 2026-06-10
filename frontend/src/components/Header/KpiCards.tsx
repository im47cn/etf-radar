import { useDataContext } from '@/providers/DataProvider';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface KpiCardProps {
  label: string;
  value: string;
  badge: string;
  badgeColor?: string;
}

const KpiCard = ({ label, value, badge, badgeColor = 'bg-blue-600' }: KpiCardProps) => (
  <Card className="p-3 flex-1 min-w-[110px]">
    <div className="flex items-center gap-1">
      <Badge className={badgeColor + ' text-white'}>{badge}</Badge>
      <span className="text-xs text-gray-500">{label}</span>
    </div>
    <div className="text-xl font-semibold mt-1">{value}</div>
  </Card>
);

export const KpiCards = () => {
  const { signals } = useDataContext();
  const s = signals?.summary;
  if (!s) return <div className="text-sm text-gray-400">读取中...</div>;
  return (
    <div className="flex gap-2 flex-wrap">
      <KpiCard label="美股主题" value={`${s.themes_total} 个`} badge="US" />
      <KpiCard label="A股ETF" value={`${s.etfs_total} 只`} badge="CN" />
      <KpiCard label="共振" value={`${s.resonance_count} 组`} badge="CO" />
      <KpiCard
        label="传导"
        value={`${s.transmission_count} 组`}
        badge="!"
        badgeColor="bg-red-600"
      />
      <KpiCard
        label="背离"
        value={`${s.divergence_count} 组`}
        badge="!"
        badgeColor="bg-yellow-500"
      />
      {s.top_theme && (
        <KpiCard
          label="当前最强"
          value={`${s.top_theme.name} · ${s.top_theme.primary_us}`}
          badge="TOP"
        />
      )}
    </div>
  );
};
