import { useState, type ReactNode } from 'react';
import { useAuth } from '@/hooks/useAuth';

export const AuthGate = ({ children }: { children: ReactNode }) => {
  const { status, signInWithMagicLink, signInWithGoogle } = useAuth();
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
          持仓监控功能需要 Supabase 凭据。请联系管理员或参考
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
      <h2 className="text-xl font-bold text-center mb-1">📊 持仓信号监控</h2>
      <p className="text-sm text-gray-600 text-center mb-6">
        把您的持仓接入跨市场强弱与轮动信号引擎
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
        className="w-full px-4 py-2 border rounded hover:bg-gray-50"
      >
        使用 Google 登录
      </button>

      {msg && (
        <div className={`mt-3 text-sm ${msg.startsWith('✓') ? 'text-green-600' : 'text-red-600'}`}>
          {msg}
        </div>
      )}

      <div className="mt-6 pt-4 border-t text-xs text-gray-500 space-y-1">
        <div>🔒 数据隐私</div>
        <div>• 持仓数据仅用于本站信号叠加</div>
        <div>• 不与任何第三方共享</div>
        <div>• 不构成投资建议</div>
      </div>
    </div>
  );
};
