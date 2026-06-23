import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import { useSnapshotsTimeline } from '@/hooks/useSnapshotsTimeline';
import { usePortfolioScores } from '@/hooks/usePortfolioScores';
import { RotationTrailsOverlay } from '@/components/rotation/RotationTrailsOverlay';
import { QuadrantLegend } from '@/components/rotation/QuadrantLegend';
import { RotationHealthBar } from '@/components/rotation/RotationHealthBar';
import { computeRotationHealth } from '@/lib/rotationHealth';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { MarketViewSelector } from '@/components/FilterBar/MarketViewSelector';

export const RotationPage = () => {
  const { themes, isLoading, error } = useDataContext();
  const { snapshotsFrames, index, prefetch } = useSnapshotsTimeline();
  const { ownedThemeIds } = usePortfolioScores();

  // availableDates: 给 slider 决定上限用; 与 snapshotsFrames (cache 子集) 解耦.
  // 让 slider 能覆盖 MAX_TRAIL_DAYS (30) 而不被 PREFETCH_RECENT (10) 卡住.
  const availableDates = useMemo(
    () => index?.snapshots.map(s => s.date) ?? [],
    [index],
  );

  // Health 必须在所有 hooks 调用完成后计算 (即便提前 return). 用 useMemo 缓存,
  // themes.themes 变化时自动重算 (滑动时间轴 / 数据刷新).
  // 注: 当前 RotationPage 无时间轴 slider, 数据源为 dataContext (=最新快照).
  // 未来加 slider 时改用 useSnapshotsTimeline().frame?.themes 即可.
  // 提取到局部变量是为了让 react-hooks/preserve-manual-memoization 推断的依赖
  // 与手写依赖一致 (否则 optional chaining 会被推断为更宽的 `themes`).
  const themesArr = themes?.themes;
  const health = useMemo(
    () => (themesArr ? computeRotationHealth(themesArr) : null),
    [themesArr],
  );

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
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-bold">主题轮动象限图</h2>
          <MarketViewSelector />
        </div>
        <p className="text-xs text-gray-600 mb-4">
          X 轴为长期强度 (60d), Y 轴为短期强度 (1d), 中线 50 切四象限。气泡大小反映综合排名。
        </p>
        {health && <RotationHealthBar health={health} />}
        <RotationTrailsOverlay
          themes={themes.themes}
          snapshots={snapshotsFrames}
          availableDates={availableDates}
          onPrefetch={prefetch}
          ownedThemeIds={ownedThemeIds}
        />
        <QuadrantLegend />
      </div>
    </main>
  );
};
