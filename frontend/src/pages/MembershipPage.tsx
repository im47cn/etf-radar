import { FeatureGate } from '@/components/gate/FeatureGate';
import { MembershipPanel } from '@/components/membership/MembershipPanel';
import { PageHelp, type HelpSection } from '@/components/help/PageHelp';

/** 会员中心帮助文案: 权益差异 + 下单流程 + 常见误读. 放 gate 外, 未登录亦可见. */
const MEMBERSHIP_HELP: HelpSection[] = [
  {
    title: '权益说明',
    children: [
      <p key="free">
        <strong>免费用户</strong>：板块轮动雷达、ETF 雷达榜单、市场温度/宽度均可查看；持仓最多录入 5 支；
        自选盯盘与每日变化摘要邮件为会员功能。
      </p>,
      <p key="member">
        <strong>会员</strong>：持仓不限数量、自选盯盘、每日变化摘要邮件（即将推出）。月度 ¥6 / 年度 ¥58（约 8 折）。
      </p>,
    ],
  },
  {
    title: '开通流程',
    children: [
      <p key="step1">① 选择月度或年度，点击跳转<strong>爱发电</strong>完成支付。</p>,
      <p key="step2">② 下单时把页面显示的<strong>绑定码</strong>填入订单留言，用于将支付与账号关联。</p>,
      <p key="step3">③ 支付成功后回到本页，订阅状态自动刷新生效。</p>,
    ],
  },
  {
    title: '常见误读',
    children: [
      <p key="m1"><strong>前端门控仅为体验</strong>：界面上的会员标识只是 UX 层提示，真实的数据访问边界由后端强制，无法通过改前端绕过。</p>,
      <p key="m2">绑定码请妥善保管，不要泄露给他人。</p>,
    ],
  },
];

export const MembershipPage = () => (
  <div className="max-w-6xl mx-auto p-4">
    {/* 标题与"使用说明"在 gate 外渲染：未登录/非会员也能看到权益说明 */}
    <div className="max-w-2xl mx-auto mb-4 flex items-center justify-between">
      <h1 className="text-2xl font-bold">会员中心</h1>
      <PageHelp title="会员中心" sections={MEMBERSHIP_HELP} />
    </div>
    <FeatureGate copy="membership" required="auth">
      <MembershipPanel />
    </FeatureGate>
  </div>
);
