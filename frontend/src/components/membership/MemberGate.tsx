import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useSubscription } from '@/lib/subscription/useSubscription';

// 会员门控组件（仿 AuthGate）：非会员显示升级引导，会员渲染 children。
// 注意：这是 UX 软门控；真正的写权限由 add_watchlist RPC 服务端强制。
export const MemberGate = ({ children }: { children: ReactNode }) => {
  const { state } = useSubscription();

  if (state === 'loading') {
    return <div className="p-8 text-center text-gray-500">加载中...</div>;
  }

  if (state === 'member') return <>{children}</>;

  // non-member
  return (
    <div className="max-w-md mx-auto mt-12 p-6 border rounded bg-white shadow-sm text-center">
      <div className="text-lg font-semibold mb-2">会员专属</div>
      <p className="text-sm text-gray-600 mb-4">
        自选盯盘为会员功能。开通后可把关注的主题 / A股 ETF 加入自选，集中查看它们的当前状态。
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
