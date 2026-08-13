import { useDataContext } from '@/providers/dataContext';
import { AddWatchButton } from '@/components/membership/AddWatchButton';
import { FeatureGate } from '@/components/gate/FeatureGate';
import { WatchlistView } from '@/components/membership/WatchlistView';
import { PageHelp, type HelpSection } from '@/components/help/PageHelp';

/** 我的自选帮助文案: 自选范围 + 四档强度标签 + 常见误读. 放 gate 外, 未登录亦可见. */
const WATCHLIST_HELP: HelpSection[] = [
  {
    title: '核心概念',
    children: [
      <p key="def">把关注的<strong>主题</strong>或 <strong>ETF</strong> 加入自选，集中查看它们当前的客观强度状态。</p>,
      <p key="tag">
        强度按 composite 分四档：<strong>偏强</strong> / <strong>中性偏强</strong> /
        <strong> 中性偏弱</strong> / <strong>偏弱</strong>，对应不同颜色标签。
      </p>,
    ],
  },
  {
    title: '使用方法',
    children: [
      <p key="r1">① 在<strong>主题雷达</strong>页点星标按钮，或在本页下方"添加主题"区把项加入自选。</p>,
      <p key="r2">② 本页列出全部自选项的当前强度档位，点"移除"取消关注。</p>,
      <p key="r3">③ 强度为空（暂无数据）的项显示灰色占位，通常是数据未覆盖。</p>,
    ],
  },
  {
    title: '常见误读',
    children: [
      <p key="m1"><strong>自选为会员功能</strong>：免费用户无法添加自选。</p>,
      <p key="m2"><strong>强度是"当前状态"非买卖点</strong>：偏强仅代表近期相对强，不直接等价于买入信号。</p>,
    ],
  },
];

export const WatchlistPage = () => {
  const { themes } = useDataContext();
  return (
    <div className="max-w-6xl mx-auto p-4">
      {/* 标题与"使用说明"在 gate 外渲染：未登录/非会员也能看到自选概念说明 */}
      <div className="max-w-2xl mx-auto mb-4 flex items-start justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold mb-1">我的自选</h1>
          <p className="text-sm text-gray-600">以下为您自选的主题 / ETF 及其当前客观强度状态。</p>
        </div>
        <PageHelp title="我的自选" sections={WATCHLIST_HELP} />
      </div>
      <FeatureGate copy="watchlist" required="member">
        <WatchlistView />
        {/* 添加主题到自选: 列出全部主题, 每项一个 AddWatchButton (会员功能, 在 gate 内) */}
        {themes && themes.themes.length > 0 && (
          <div className="bg-white border rounded p-4 mt-4 animate-fade-rise">
            <h3 className="text-sm font-semibold mb-2">添加主题到自选</h3>
            <div className="flex flex-wrap gap-2">
              {themes.themes.map((t) => (
                <span
                  key={t.id}
                  className="inline-flex items-center gap-1 text-xs border rounded px-2 py-1"
                >
                  {t.name}
                  <AddWatchButton itemType="theme" itemKey={t.id} />
                </span>
              ))}
            </div>
          </div>
        )}
      </FeatureGate>
    </div>
  );
};
