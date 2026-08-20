/* eslint-disable react-refresh/only-export-components -- GATE_COPY 是 FeatureGate 的配套文案常量, 非独立模块 */
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useSubscription } from '@/lib/subscription/useSubscription';
import type { GatedPage } from '@/lib/gateCopy';

/**
 * 门控页文案预设（登录态 + 会员态共用 hero）。
 * 新增门控页：在 gateCopy.ts 的 GATED_PAGES 加 key，再在此补一项。
 */
export const GATE_COPY: Record<GatedPage, {
  icon: string;
  title: string;
  subtitle: string;
  features: string[];
  unconfiguredHint: string;
  footer: { heading: string; lines: string[] };
}> = {
  portfolio: {
    icon: '📊',
    title: '持仓信号监控',
    subtitle: '把您的持仓接入跨市场主题强弱与轮动信号引擎',
    features: [
      '美股主题 ETF 强弱自动映射到 A 股 ETF',
      '持仓与主题强度叠加，一眼看清偏离与共振',
      '关键信号（共振 / 传导 / 背离）自动预警',
    ],
    unconfiguredHint: '持仓监控功能',
    footer: {
      heading: '🔒 数据隐私',
      lines: ['持仓数据仅用于本站信号叠加', '不与任何第三方共享', '不构成投资建议'],
    },
  },
  watchlist: {
    icon: '⭐',
    title: '自选盯盘',
    subtitle: '把关注的主题与 A股 ETF 集中到一个视图',
    features: [
      '自定义自选池，跨市场集中盯盘',
      '主题 / A股 ETF 状态实时聚合',
      '会员专属：高级信号叠加与持续刷新',
    ],
    unconfiguredHint: '自选盯盘功能',
    footer: {
      heading: '🔒 数据隐私',
      lines: ['自选数据仅用于本站展示', '不与任何第三方共享', '不构成投资建议'],
    },
  },
  evidence: {
    icon: '📊',
    title: '信号证据',
    subtitle: 'strength 主题信号的统计有效性证据',
    features: [
      '5 年样本外 IC（横截面预测力）',
      'ARCH 波动聚集检验（McLeod-Li）',
      '月度预计算，跨牛熊周期验证',
    ],
    unconfiguredHint: '信号证据功能',
    // 证据为公开统计数据，无用户隐私 → 用免责声明语境
    footer: {
      heading: '⚠ 免责声明',
      lines: ['本页为 5 年样本外统计，非实时交易信号', '不构成投资建议'],
    },
  },
  grid: {
    icon: '📐',
    title: '网格选标',
    subtitle: '按波动率 + 均值回归 + ARCH 持续性优选适合网格的主题 ETF',
    features: [
      '复合分跨主题排序，绿色主题适合网格',
      'Hurst 均值回归检验，避开趋势陷阱',
      '波动率 + ARCH 双维度，兼顾利润空间与持续性',
    ],
    unconfiguredHint: '网格选标功能',
    footer: {
      heading: '⚠ 免责声明',
      lines: ['统计信号非保证盈利，需结合价位/流动性/趋势实判', '不构成投资建议'],
    },
  },
  membership: {
    icon: '💳',
    title: '会员订阅',
    subtitle: '解锁全部高级功能与持续信号服务',
    features: [
      '自选盯盘 + 信号证据全开放',
      '主题变化摘要定时推送',
      '优先支持与新功能优先体验',
    ],
    unconfiguredHint: '会员订阅功能',
    footer: {
      heading: '🔒 数据隐私',
      lines: ['订阅数据仅用于会员服务', '不与任何第三方共享', '不构成投资建议'],
    },
  },
  'trading-signals': {
    icon: '📡',
    title: '交易信号跟踪',
    subtitle: 'SEPA 趋势模板 + VCP 形态的 A 股候选池每日快照',
    features: [
      '全市场漏斗筛选：趋势模板 → Stage 2 → VCP → 综合分 Top 50',
      '买区 / 止损位 / 距买区距离的事实性状态展示',
      '风险预算法仓位计算器（纯算术，无指令）',
    ],
    unconfiguredHint: '交易信号跟踪功能',
    footer: {
      heading: '⚠ 免责声明',
      lines: ['全部内容为事实性数据展示，非买卖指令', '不构成投资建议'],
    },
  },
  'trading-positions': {
    icon: '📌',
    title: '持仓管理',
    subtitle: '您的持仓每日信号事件跟踪（止损位 / 均线 / 阶段变化）',
    features: [
      '持仓每日 EOD 信号事件：事实性状态变化记录',
      '止损位跟踪（只上移规则的计算展示）',
      '云端存储（Supabase），仅本人可见',
    ],
    unconfiguredHint: '持仓管理功能',
    footer: {
      heading: '🔒 数据隐私',
      lines: ['持仓数据仅用于本人信号叠加', '不与任何第三方共享', '不构成投资建议'],
    },
  },
  'trading-review': {
    icon: '🧾',
    title: '交易复盘',
    subtitle: '按纪律分与结果分（R 倍数）回顾交易记录',
    features: [
      '纪律分 0-100：入场 / 止损执行 / 退出响应 / 仓位合规',
      '结果分：R 倍数、持仓天数、MAE',
      '按环境档位切片的胜率与期望统计',
    ],
    unconfiguredHint: '交易复盘功能',
    footer: {
      heading: '⚠ 免责声明',
      lines: ['复盘统计为历史记录描述', '不构成投资建议'],
    },
  },
};

interface FeatureGateProps {
  /** 文案预设 key */
  copy: GatedPage;
  /** 页面访问要求：auth=登录即可，member=需付费会员 */
  required: 'auth' | 'member';
  children: ReactNode;
}

/**
 * 统一门控：按「页面要求 × 用户状态」驱动内容。
 * - loading / unconfigured → 骨架 / 配置缺失卡
 * - anonymous → Hero（功能介绍 + 登录表单）
 * - authenticated + required=auth → 直接渲染 children
 * - authenticated + required=member → 交 MemberCheck（member 渲染 children，否则 Hero 升级卡）
 */
export const FeatureGate = ({ copy, required, children }: FeatureGateProps) => {
  const { status } = useAuth();
  const c = GATE_COPY[copy];

  if (status === 'loading') {
    return <div className="p-8 text-center text-gray-500">加载中...</div>;
  }

  if (status === 'unconfigured') {
    return (
      <div className="max-w-md mx-auto mt-12 p-6 border rounded bg-yellow-50">
        <div className="text-lg font-semibold mb-2">⚠ 未配置 Supabase</div>
        <div className="text-sm text-gray-700">
          {c.unconfiguredHint}需要 Supabase 凭据。请联系管理员或参考
          <code className="mx-1 px-1 bg-gray-100">frontend/.env.local.example</code>
          自行配置。
        </div>
      </div>
    );
  }

  if (status === 'anonymous') {
    return <HeroLogin copy={copy} />;
  }

  // status === 'authenticated'
  if (required === 'auth') return <>{children}</>;
  return (
    <MemberCheck copy={copy}>{children}</MemberCheck>
  );
};

/** 会员门检查：仅在 required=member 且已登录时挂载，避免无谓订阅查询。 */
const MemberCheck = ({ copy, children }: { copy: GatedPage; children: ReactNode }) => {
  const { state } = useSubscription();

  if (state === 'loading') {
    return <div className="p-8 text-center text-gray-500">加载中...</div>;
  }
  if (state === 'member') return <>{children}</>;
  return <HeroUpgrade copy={copy} />;
};

/** Hero 共享布局：icon + 价值主张 + 特性网格 + CTA + footer。 */
const Hero = ({ copy, cta }: { copy: GatedPage; cta: ReactNode }) => {
  const c = GATE_COPY[copy];
  return (
    <div className="max-w-2xl mx-auto mt-8 p-8 bg-white rounded-lg border shadow-sm">
      <div className="text-center mb-6">
        <div className="text-4xl mb-2">{c.icon}</div>
        <h1 className="text-2xl font-bold text-gray-800">{c.title}</h1>
        <p className="mt-1 text-sm text-gray-600">{c.subtitle}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        {c.features.map(f => (
          <div
            key={f}
            className="p-3 bg-gray-50 rounded text-xs text-gray-700 flex items-start gap-1.5"
          >
            <span className="text-green-600 shrink-0">✓</span>
            <span>{f}</span>
          </div>
        ))}
      </div>

      <div className="border-t pt-4">{cta}</div>

      <div className="mt-6 pt-4 border-t text-xs text-gray-500 space-y-1">
        <div>{c.footer.heading}</div>
        {c.footer.lines.map(line => (
          <div key={line}>• {line}</div>
        ))}
      </div>
    </div>
  );
};

/** 未登录 CTA：magic link + OAuth 登录表单。 */
const HeroLogin = ({ copy }: { copy: GatedPage }) => {
  const { signInWithMagicLink, signInWithGoogle, signInWithGithub } = useAuth();
  const [email, setEmail] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleMagicLink = async () => {
    if (!email) return;
    setSubmitting(true);
    setMsg(null);
    const { error } = await signInWithMagicLink(email);
    setSubmitting(false);
    setMsg(error ? `失败：${error}` : '✓ 登录链接已发送，请检查邮箱（含垃圾邮件）');
  };

  return (
    <Hero
      copy={copy}
      cta={
        <>
          <label htmlFor="email" className="block text-sm font-medium mb-1">邮箱登录</label>
          <div className="flex gap-2 mb-3">
            <input
              id="email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="your@email.com"
              className="flex-1 px-3 py-2 border rounded text-sm"
            />
            <button
              onClick={handleMagicLink}
              disabled={!email || submitting}
              className="px-4 py-2 bg-blue-600 text-white rounded text-sm disabled:bg-gray-300 shrink-0"
            >
              {submitting ? '发送中...' : '发送登录链接'}
            </button>
          </div>
          <div className="text-center text-gray-400 my-2 text-xs">— 或 —</div>
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              onClick={signInWithGoogle}
              className="flex-1 px-4 py-2 border rounded text-sm hover:bg-gray-50"
            >
              使用 Google 登录
            </button>
            <button
              onClick={signInWithGithub}
              className="flex-1 px-4 py-2 border rounded text-sm hover:bg-gray-50"
            >
              使用 GitHub 登录
            </button>
          </div>
          {msg && (
            <div className={`mt-3 text-sm ${msg.startsWith('✓') ? 'text-green-600' : 'text-red-600'}`}>
              {msg}
            </div>
          )}
        </>
      }
    />
  );
};

/** 非会员 CTA：开通会员引导。 */
const HeroUpgrade = ({ copy }: { copy: GatedPage }) => (
  <Hero
    copy={copy}
    cta={
      <div className="text-center">
        <Link
          to="/membership"
          className="inline-block px-6 py-2.5 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm font-medium"
        >
          立即开通会员
        </Link>
        <div className="mt-2 text-xs text-gray-400">已是会员？刷新页面查看</div>
      </div>
    }
  />
);
