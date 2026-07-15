import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import { useSnapshotsTimeline } from '@/hooks/useSnapshotsTimeline';
import { usePortfolioScores } from '@/hooks/usePortfolioScores';
import { RotationTrailsOverlay } from '@/components/rotation/RotationTrailsOverlay';
import { QuadrantLegend } from '@/components/rotation/QuadrantLegend';
import { RotationHealthBar } from '@/components/rotation/RotationHealthBar';
import { MarketThermometer } from '@/components/rotation/MarketThermometer';
import { computeRotationHealth } from '@/lib/rotationHealth';
import { computeMarketBreadth } from '@/lib/marketBreadth';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { MarketViewSelector } from '@/components/FilterBar/MarketViewSelector';
import { useUIState } from '@/providers/uiStateContext';
import { marketViewToRotationMode } from '@/lib/marketView';
import { AddWatchButton } from '@/components/membership/AddWatchButton';

export const RotationPage = () => {
  const { themes, etfs, isLoading, error } = useDataContext();
  const { snapshotsFrames, index, prefetch } = useSnapshotsTimeline();
  const { ownedThemeIds } = usePortfolioScores();
  const { state: uiState } = useUIState();
  const rotationMode = marketViewToRotationMode(uiState.marketView);

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
    () => (themesArr ? computeRotationHealth(themesArr, rotationMode) : null),
    [themesArr, rotationMode],
  );

  // 市场温度计: 与象限图 (RRG 相对图) 正交, 补全市场普涨/普跌盲区.
  // CN 模式用 41 只主题 ETF 的 r_1d; US 模式用有 us_strength 的主题美股锚点 r_1d.
  const etfsArr = etfs?.etfs;
  const breadth = useMemo(() => {
    const values =
      rotationMode === 'cn'
        ? (etfsArr ?? []).map((e) => e.returns.r_1d)
        : (themesArr ?? [])
            .filter((t) => t.us_strength !== null)
            .map((t) => t.returns.r_1d);
    return computeMarketBreadth(values);
  }, [rotationMode, etfsArr, themesArr]);

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
      <div className="bg-white border rounded p-4 animate-fade-rise" style={{ animationDelay: '0ms' }}>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-bold">主题轮动象限图</h2>
          <MarketViewSelector />
        </div>
        <p className="text-xs text-gray-600 mb-4">
          X 轴为长期强度 (60d), Y 轴为短期强度 (1d), 中线 50 切四象限。气泡大小反映综合排名。
        </p>
        <MarketThermometer breadth={breadth} />
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

      {/* 会员自选快捷添加：把关注的主题加入自选，去「我的自选」集中查看当前状态 */}
      <div className="bg-white border rounded p-4 animate-fade-rise" style={{ animationDelay: '60ms' }}>
        <h3 className="text-sm font-semibold mb-2">加入自选（会员）</h3>
        <div className="flex flex-wrap gap-2">
          {themes.themes.map((t, i) => (
            <span key={t.id} className="inline-flex items-center gap-1 text-xs border rounded px-2 py-1 animate-fade-rise" style={{ animationDelay: `${60 + Math.min(i, 6) * 40}ms` }}>
              {t.name}
              <AddWatchButton itemType="theme" itemKey={t.id} />
            </span>
          ))}
        </div>
      </div>
    </main>
  );
};
