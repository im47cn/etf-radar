import { useEffect, useState } from 'react';
import { getSupabase } from '@/lib/supabase';
import { useSubscription } from '@/lib/subscription/useSubscription';
import { Disclaimer } from './Disclaimer';

// 爱发电订阅链接来自构建时环境变量（生产在 deploy-frontend.yml 由
// vars.AFDIAN_MONTHLY_URL/YEARLY_URL 注入；本地在 .env.local）。
// 未配置时按钮禁用并提示——绝不硬编码 URL，也绝不用 '#'（HashRouter 下会跳默认页）。
const AFDIAN_MONTHLY_URL = import.meta.env.VITE_AFDIAN_MONTHLY_URL || '';
const AFDIAN_YEARLY_URL  = import.meta.env.VITE_AFDIAN_YEARLY_URL || '';

const PLAN_LABEL: Record<string, string> = { monthly: '月度会员', yearly: '年度会员' };

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('zh-CN');
}

// 定价卡：只描述权益与价格，不含任何操作动词。
// href 为空（未配置订阅链接）时渲染为禁用态，避免无效跳转。
const PriceCard = ({
  title, price, unit, note, href,
}: { title: string; price: string; unit: string; note?: string; href: string }) => {
  const body = (
    <>
      <div className="text-sm text-gray-600">{title}</div>
      <div className="mt-1">
        <span className="text-3xl font-bold">¥{price}</span>
        <span className="text-gray-500 text-sm"> / {unit}</span>
      </div>
      {note && <div className="mt-1 text-xs text-green-600">{note}</div>}
      <div className={`mt-3 text-sm ${href ? 'text-blue-600' : 'text-gray-400'}`}>
        {href ? '前往爱发电订阅 →' : '订阅入口配置中'}
      </div>
    </>
  );
  if (!href) {
    return (
      <div className="flex-1 block p-5 border rounded-lg opacity-60 cursor-not-allowed" aria-disabled>
        {body}
      </div>
    );
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="flex-1 block p-5 border rounded-lg hover:border-blue-500 hover:shadow-sm transition"
    >
      {body}
    </a>
  );
};

// 权益对比表：直观呈现免费用户与会员的功能差异。
// '✓' 已支持，'—' 不支持，字符串为特殊状态（如即将推出）。
const FEATURE_ROWS: { name: string; desc?: string; free: string; member: string; highlight?: boolean }[] = [
  { name: '市场温度 / 宽度', free: '✓', member: '✓' },
  { name: '板块轮动雷达',   free: '✓', member: '✓' },
  { name: 'ETF 雷达榜单',   free: '✓', member: '✓' },
  { name: '持仓管理',       free: '✓', member: '✓' },
  { name: '自选盯盘', desc: '把关注的主题 / A股 ETF 加入自选，集中查看当前状态', free: '—', member: '✓', highlight: true },
  { name: '每日变化摘要邮件', free: '—', member: '即将推出', highlight: true },
];

const cellClass = (v: string): string =>
  v === '✓' ? 'text-green-600 font-medium'
  : v === '—' ? 'text-gray-300'
  : 'text-blue-600 text-xs';

const FeatureComparison = () => (
  <div className="mb-6 overflow-x-auto">
    <table className="w-full text-sm border-collapse min-w-[20rem]">
      <thead>
        <tr className="border-b">
          <th className="py-2 px-2 text-left font-medium text-gray-600">功能</th>
          <th className="py-2 px-2 text-center font-medium text-gray-500 w-24">免费用户</th>
          <th className="py-2 px-2 text-center font-medium text-blue-700 w-24">会员</th>
        </tr>
      </thead>
      <tbody>
        {FEATURE_ROWS.map((row) => (
          <tr key={row.name} className={`border-b ${row.highlight ? 'bg-blue-50/50' : ''}`}>
            <td className={`py-2 px-2 ${row.highlight ? 'font-medium' : 'text-gray-700'}`}>
              {row.name}
              {row.desc && <div className="text-xs font-normal text-gray-500 mt-0.5">{row.desc}</div>}
            </td>
            <td className={`py-2 px-2 text-center ${cellClass(row.free)}`}>{row.free}</td>
            <td className={`py-2 px-2 text-center ${cellClass(row.member)}`}>{row.member}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

// 绑定码块：调 issue_bind_code RPC 取码，引导用户下单时填入订单留言。
const BindCodeBlock = () => {
  const [code, setCode]   = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { data, error } = await getSupabase().rpc('issue_bind_code');
      if (cancelled) return;
      if (error) setError(error.message);
      else setCode(data as string);
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded">
      <div className="text-sm font-medium mb-2">下单时请在爱发电订单留言中填写此绑定码</div>
      {loading && <div className="text-sm text-gray-500">生成中...</div>}
      {error && <div className="text-sm text-red-600">生成失败：{error}</div>}
      {code && (
        <div className="text-2xl font-mono tracking-widest bg-white inline-block px-3 py-1 rounded border">
          {code}
        </div>
      )}
      <div className="mt-2 text-xs text-gray-500">
        绑定码用于把您的爱发电订单与本站账号关联。系统收到订单后自动开通会员，通常几分钟内生效。
      </div>
    </div>
  );
};

export const MembershipPanel = () => {
  const { state, plan, periodEnd } = useSubscription();

  return (
    <div className="max-w-2xl mx-auto p-6 bg-white border rounded-lg shadow-sm">
      <h1 className="text-2xl font-bold mb-4">会员中心</h1>

      {/* 当前订阅状态 */}
      <div className="mb-6 p-4 bg-gray-50 rounded">
        {state === 'loading' && <span className="text-gray-500">加载订阅状态...</span>}
        {state === 'member' && (
          <span className="text-green-700">
            会员生效中（{PLAN_LABEL[plan ?? '']}），到期日 {fmtDate(periodEnd)}
          </span>
        )}
        {state === 'non-member' && <span className="text-gray-700">当前未订阅</span>}
      </div>

      {state !== 'member' && (
        <>
          <FeatureComparison />
          <div className="flex flex-col sm:flex-row gap-3">
            <PriceCard title="月度会员" price="6"  unit="月" href={AFDIAN_MONTHLY_URL} />
            <PriceCard title="年度会员" price="58" unit="年" note="约 8 折" href={AFDIAN_YEARLY_URL} />
          </div>
          <BindCodeBlock />
        </>
      )}

      <Disclaimer />
    </div>
  );
};
