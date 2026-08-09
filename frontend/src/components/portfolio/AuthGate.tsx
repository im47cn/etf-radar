/* eslint-disable react-refresh/only-export-components -- AUTH_COPY 是 AuthGate 的配套文案常量, 非独立模块 */
import { useState, type ReactNode } from 'react';
import { useAuth } from '@/hooks/useAuth';

/**
 * 各门控页的登录卡文案预设。新增门控页只需在此加一项，调用处传 `copy` key。
 */
export const AUTH_COPY = {
  portfolio: {
    title: '📊 持仓信号监控',
    subtitle: '把您的持仓接入跨市场强弱与轮动信号引擎',
    unconfiguredHint: '持仓监控功能',
    privacyNote: '持仓数据仅用于本站信号叠加',
  },
  evidence: {
    title: '📊 信号证据',
    subtitle: '登录后查看 strength 主题信号的统计证据',
    unconfiguredHint: '信号证据功能',
    privacyNote: '数据仅用于本站统计展示',
  },
  membership: {
    title: '💳 会员订阅',
    subtitle: '登录后查看与管理您的会员订阅',
    unconfiguredHint: '会员订阅功能',
    privacyNote: '订阅数据仅用于会员服务',
  },
} as const;

export type AuthCopyKey = keyof typeof AUTH_COPY;

interface AuthGateProps {
  children: ReactNode;
  /** 文案预设 key，默认 portfolio */
  copy?: AuthCopyKey;
}

export const AuthGate = ({ children, copy = 'portfolio' }: AuthGateProps) => {
  const { status, signInWithMagicLink, signInWithGoogle, signInWithGithub } = useAuth();
  const [email, setEmail]   = useState('');
  const [msg, setMsg]       = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === 'loading') {
    return <div className="p-8 text-center text-gray-500">加载中...</div>;
  }

  if (status === 'unconfigured') {
    return (
      <div className="max-w-md mx-auto mt-12 p-6 border rounded bg-yellow-50">
        <div className="text-lg font-semibold mb-2">⚠ 未配置 Supabase</div>
        <div className="text-sm text-gray-700">
          {AUTH_COPY[copy].unconfiguredHint}需要 Supabase 凭据。请联系管理员或参考
          <code className="mx-1 px-1 bg-gray-100">frontend/.env.local.example</code>
          自行配置。
        </div>
      </div>
    );
  }

  if (status === 'authenticated') return <>{children}</>;

  // status === 'anonymous'
  const handleMagicLink = async () => {
    if (!email) return;
    setSubmitting(true);
    setMsg(null);
    const { error } = await signInWithMagicLink(email);
    setSubmitting(false);
    setMsg(error ? `失败：${error}` : '✓ 登录链接已发送，请检查邮箱（含垃圾邮件）');
  };

  return (
    <div className="max-w-md mx-auto mt-12 p-6 border rounded bg-white shadow-sm">
      <h2 className="text-xl font-bold text-center mb-1">{AUTH_COPY[copy].title}</h2>
      <p className="text-sm text-gray-600 text-center mb-6">
        {AUTH_COPY[copy].subtitle}
      </p>

      <label htmlFor="email" className="block text-sm font-medium mb-1">邮箱</label>
      <input
        id="email"
        type="email"
        value={email}
        onChange={e => setEmail(e.target.value)}
        placeholder="your@email.com"
        className="w-full px-3 py-2 border rounded mb-3"
      />
      <button
        onClick={handleMagicLink}
        disabled={!email || submitting}
        className="w-full px-4 py-2 bg-blue-600 text-white rounded disabled:bg-gray-300"
      >
        {submitting ? '发送中...' : '发送登录链接'}
      </button>

      <div className="text-center text-gray-400 my-3 text-xs">— 或 —</div>

      <button
        onClick={signInWithGoogle}
        className="w-full px-4 py-2 border rounded hover:bg-gray-50 mb-2"
      >
        使用 Google 登录
      </button>

      <button
        onClick={signInWithGithub}
        className="w-full px-4 py-2 border rounded hover:bg-gray-50"
      >
        使用 GitHub 登录
      </button>

      {msg && (
        <div className={`mt-3 text-sm ${msg.startsWith('✓') ? 'text-green-600' : 'text-red-600'}`}>
          {msg}
        </div>
      )}

      <div className="mt-6 pt-4 border-t text-xs text-gray-500 space-y-1">
        <div>🔒 数据隐私</div>
        <div>• {AUTH_COPY[copy].privacyNote}</div>
        <div>• 不与任何第三方共享</div>
        <div>• 不构成投资建议</div>
      </div>
    </div>
  );
};
