import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useHoldings } from '@/hooks/useHoldings';
import { useSubscription } from '@/lib/subscription/useSubscription';
import { FREE_HOLDINGS_LIMIT } from '@/lib/portfolio/limits';
import { usePortfolioScores } from '@/hooks/usePortfolioScores';
import { useDataContext } from '@/providers/dataContext';
import { useUserEvents } from '@/hooks/useUserEvents';
import { usePortfolioEventDetection } from '@/hooks/usePortfolioEventDetection';
import { useSnapshotsTimeline } from '@/hooks/useSnapshotsTimeline';
import { HoldingScoreCard } from './HoldingScoreCard';
import { HoldingsEditor } from './HoldingsEditor';
import { PortfolioSummary } from './PortfolioSummary';
import { OpportunityScanner } from './OpportunityScanner';
import { EventTimeline } from './EventTimeline';

export const HoldingsList = () => {
  const { remove, holdings } = useHoldings();
  const { scores, loading, ownedThemeIds, themes } = usePortfolioScores();
  // 免费版持仓上限：非会员满 5 支时禁止新增（服务端触发器兜底强制）。
  const { state } = useSubscription();
  const isMember = state === 'member';
  const atLimit = !isMember && holdings.length >= FREE_HOLDINGS_LIMIT;
  // null = 不开; '' = 新增模式; etfCode = 编辑模式
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const editing = editingCode ? holdings.find(h => h.etf_code === editingCode) ?? null : null;
  const editorOpen = editingCode !== null;

  // 快照索引：取最新两日日期，供事件检测使用
  const { index } = useSnapshotsTimeline();
  const snapsLen = index?.snapshots.length ?? 0;
  const todayDate     = snapsLen >= 1 ? index!.snapshots[snapsLen - 1].date : undefined;
  const yesterdayDate = snapsLen >= 2 ? index!.snapshots[snapsLen - 2].date : undefined;

  // themeNames map：themeId → name，供 EventTimeline 展示
  const data = useDataContext();
  const themeNames = new Map<string, string>(
    data.themes?.themes.map(t => [t.id, t.name]) ?? []
  );

  // 仅取 covered（有 themeId）持仓用于信号差异检测
  const holdingsForDiff = scores
    .filter(s => s.status === 'covered' && s.themeId)
    .map(s => ({ themeId: s.themeId!, etfCode: s.etfCode }));

  // 触发事件检测（同日节流，内部有 localStorage guard）
  usePortfolioEventDetection({ todayDate, yesterdayDate, holdings: holdingsForDiff });

  // 事件流数据（useUserEvents 消费 EventsContext）
  const { events, unreadCount, markAllRead } = useUserEvents();

  // 当前持仓 ETF 代码集合 —— 透传给 EventTimeline 计算"事件影响你持仓的 SOXX"
  // useMemo 避免每次 render 重建 Set 触发下游不必要 re-render
  const currentHoldings = useMemo(
    () => new Set(holdings.map(h => h.etf_code)),
    [holdings],
  );

  if (loading) {
    return <div className="p-8 text-center text-gray-500">加载持仓...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-baseline gap-2">
          <h2 className="text-lg font-semibold">我的持仓（{scores.length} 只）</h2>
          {!isMember && (
            <span className="text-xs text-gray-500">免费版 {holdings.length}/{FREE_HOLDINGS_LIMIT}</span>
          )}
        </div>
        {atLimit ? (
          <Link
            to="/membership"
            className="px-3 py-1.5 bg-amber-500 text-white rounded text-sm hover:bg-amber-600"
            title={`免费版最多 ${FREE_HOLDINGS_LIMIT} 支，升级会员解锁不限`}
          >升级解锁更多</Link>
        ) : (
          <button
            onClick={() => setEditingCode('')}
            className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm"
          >+ 添加持仓</button>
        )}
      </div>

      {scores.length === 0 ? (
        <div className="border rounded p-8 text-center bg-gray-50">
          <div className="text-gray-600 mb-2">还没有录入持仓</div>
          <div className="text-sm text-gray-500 mb-4">
            把您的 A 股 ETF 接入信号引擎，看看它们当下状态
          </div>
          <button
            onClick={() => setEditingCode('')}
            className="px-4 py-2 bg-blue-600 text-white rounded"
          >+ 添加第一只</button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {scores.map(s => (
              <HoldingScoreCard
                key={s.etfCode} score={s}
                onDelete={remove}
                onEdit={setEditingCode}
              />
            ))}
          </div>
          <PortfolioSummary scores={scores} />
          <EventTimeline
            events={events}
            themeNames={themeNames}
            unreadCount={unreadCount}
            markAllRead={markAllRead}
            currentHoldings={currentHoldings}
          />
          <OpportunityScanner themes={themes} ownedThemeIds={ownedThemeIds} />
        </>
      )}

      <HoldingsEditor
        open={editorOpen}
        onClose={() => setEditingCode(null)}
        editing={editing}
      />
    </div>
  );
};
