import { useDataContext } from '@/providers/DataProvider';
import { RotationScatter } from '@/components/rotation/RotationScatter';
import { QuadrantLegend } from '@/components/rotation/QuadrantLegend';
import { Alert, AlertDescription } from '@/components/ui/alert';

export const RotationPage = () => {
  const { themes, isLoading, error } = useDataContext();

  if (isLoading) {
    return <div data-testid="rotation-skeleton" className="h-[500px] animate-pulse bg-gray-100 rounded m-4" />;
  }
  if (error) {
    return (
      <Alert variant="destructive" className="m-4">
        <AlertDescription>数据加载失败, 已显示上次成功快照</AlertDescription>
      </Alert>
    );
  }
  if (!themes || themes.themes.length === 0) {
    return (
      <Alert className="m-4">
        <AlertDescription>暂无主题数据</AlertDescription>
      </Alert>
    );
  }

  return (
    <main className="p-4 space-y-4">
      <div className="bg-white border rounded p-4">
        <h2 className="text-lg font-bold mb-2">主题轮动象限图</h2>
        <p className="text-xs text-gray-600 mb-4">
          X 轴为长期强度 (60d), Y 轴为短期强度 (1d), 中线 50 切四象限。气泡大小反映综合排名。
        </p>
        <RotationScatter themes={themes.themes} />
        <QuadrantLegend />
      </div>
    </main>
  );
};
