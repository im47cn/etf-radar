/* eslint-disable react-refresh/only-export-components -- MEMBER_COPY 是 MemberGate 的配套文案常量, 非独立模块 */
import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useSubscription } from '@/lib/subscription/useSubscription';
import type { GatedPage } from '@/lib/gateCopy';

/** MemberGate 可用的文案 key（会员功能页子集） */
export type MemberCopyKey = Extract<GatedPage, 'watchlist' | 'evidence'>;

/**
 * 各会员门控页的非会员升级卡文案预设。新增会员功能页只需在此加一项，调用处传 `copy` key。
 * key 为 {@link GatedPage} 子集（仅会员专属功能页）。
 */
export const MEMBER_COPY: Record<MemberCopyKey, {
  feature: string;
  description: string;
}> = {
  watchlist: {
    feature: '自选盯盘',
    description: '开通后可把关注的主题 / A股 ETF 加入自选，集中查看它们的当前状态。',
  },
  evidence: {
    feature: '信号证据',
    description: '开通后可查看 strength 主题信号 5 年样本外统计有效性的可视化证据。',
  },
};

interface MemberGateProps {
  children: ReactNode;
  /** 文案预设 key，默认 watchlist */
  copy?: MemberCopyKey;
}

// 会员门控组件（仿 AuthGate）：非会员显示升级引导，会员渲染 children。
// 注意：这是 UX 软门控；真正的写权限由 add_watchlist RPC 服务端强制。
export const MemberGate = ({ children, copy = 'watchlist' }: MemberGateProps) => {
  const { state } = useSubscription();

  if (state === 'loading') {
    return <div className="p-8 text-center text-gray-500">加载中...</div>;
  }

  if (state === 'member') return <>{children}</>;

  const { feature, description } = MEMBER_COPY[copy];

  // non-member
  return (
    <div className="max-w-md mx-auto mt-12 p-6 border rounded bg-white shadow-sm text-center">
      <div className="text-lg font-semibold mb-2">会员专属</div>
      <p className="text-sm text-gray-600 mb-4">
        {feature}为会员功能。{description}
      </p>
      <Link
        to="/membership"
        className="inline-block px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        前往开通
      </Link>
    </div>
  );
};
