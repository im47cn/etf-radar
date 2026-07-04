import { useEffect, useState } from 'react';
import { getSupabase } from '@/lib/supabase';
import { useSubscription } from '@/lib/subscription/useSubscription';
import { Disclaimer } from './Disclaimer';

// 爱发电订阅链接。默认指向创作者页（列出全部方案，用户自选月/年）；
// env 若配置则优先（可将年费指向独立方案链接）。用 || 兼容未配置(undefined)与空串。
// 注意：默认值不能是 '#'——在 HashRouter 下点 '#' 会跳到默认页(市场温度)。
const AFDIAN_HOME = 'https://www.afdian.com/a/im47cn';
const AFDIAN_MONTHLY_URL = import.meta.env.VITE_AFDIAN_MONTHLY_URL || AFDIAN_HOME;
const AFDIAN_YEARLY_URL  = import.meta.env.VITE_AFDIAN_YEARLY_URL || AFDIAN_HOME;

const PLAN_LABEL: Record<string, string> = { monthly: '月度会员', yearly: '年度会员' };

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('zh-CN');
}

// 定价卡：只描述权益与价格，不含任何操作动词。
const PriceCard = ({
  title, price, unit, note, href,
}: { title: string; price: string; unit: string; note?: string; href: string }) => (
  <a
    href={href}
    target="_blank"
    rel="noreferrer"
    className="flex-1 block p-5 border rounded-lg hover:border-blue-500 hover:shadow-sm transition"
  >
    <div className="text-sm text-gray-600">{title}</div>
    <div className="mt-1">
      <span className="text-3xl font-bold">¥{price}</span>
      <span className="text-gray-500 text-sm"> / {unit}</span>
    </div>
    {note && <div className="mt-1 text-xs text-green-600">{note}</div>}
    <div className="mt-3 text-sm text-blue-600">前往爱发电订阅 →</div>
  </a>
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
      <h1 className="text-2xl font-bold mb-1">会员中心</h1>
      <p className="text-sm text-gray-600 mb-4">
        会员可使用自选盯盘：把关注的主题 / A股 ETF 加入自选，集中查看它们的当前状态。
      </p>

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
