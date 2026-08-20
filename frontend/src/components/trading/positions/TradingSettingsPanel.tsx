import { useEffect, useState } from 'react';
import { useTrades } from '@/hooks/useTrades';

const inputClass =
  'w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none';

/**
 * 权益与风控参数（写 trading_settings 单行）。默认值 0.75% 单笔风险 / 5 只 /
 * 20% 单票市值 / 4% 组合总风险（规格 §1.7），供仓位计算与复盘「仓位合规」维度使用。
 */
export const TradingSettingsPanel = () => {
  const { settings, updateSettings } = useTrades();
  const [equity, setEquity] = useState('');
  const [riskPct, setRiskPct] = useState('');
  const [maxPositions, setMaxPositions] = useState('');
  const [maxPosPct, setMaxPosPct] = useState('');
  const [maxPortfolioRisk, setMaxPortfolioRisk] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // settings 异步回填（登录后 refresh / 保存成功后 refresh）→ 同步到输入框草稿。
  // Provider 中 settings 是 useState 值，引用稳定，不会因本组件重渲触发；
  // DB 值 → 本地草稿的单层回填，无级联渲染，豁免 set-state-in-effect。
  /* eslint-disable react-hooks/set-state-in-effect -- DB 异步值回填本地草稿, 单层无级联 */
  useEffect(() => {
    setEquity(settings.equity_cny != null ? String(settings.equity_cny) : '');
    setRiskPct(String(settings.risk_per_trade_pct));
    setMaxPositions(String(settings.max_positions));
    setMaxPosPct(String(settings.max_position_pct));
    setMaxPortfolioRisk(String(settings.max_portfolio_risk_pct));
  }, [settings]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const onSave = async () => {
    setSaved(false);

    const errs: string[] = [];
    const eq = equity.trim() === '' ? null : Number(equity);
    if (eq != null && !(eq > 0)) errs.push('账户权益须为正数（可留空）');
    const rp = Number(riskPct);
    if (!(rp > 0)) errs.push('单笔风险须为正数');
    const mp = Number(maxPositions);
    if (!Number.isInteger(mp) || mp <= 0) errs.push('最多持仓数须为正整数');
    const mpp = Number(maxPosPct);
    if (!(mpp > 0)) errs.push('单票市值上限须为正数');
    const mpr = Number(maxPortfolioRisk);
    if (!(mpr > 0)) errs.push('组合总风险上限须为正数');
    setErrors(errs);
    if (errs.length > 0) return;

    setSubmitting(true);
    const r = await updateSettings({
      equity_cny: eq,
      risk_per_trade_pct: rp,
      max_positions: mp,
      max_position_pct: mpp,
      max_portfolio_risk_pct: mpr,
    });
    setSubmitting(false);
    if (r.error) {
      setErrors([r.error]);
      return;
    }
    setErrors([]);
    setSaved(true);
  };

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-800">权益与风控参数</div>
      <div className="mt-1 text-xs text-gray-500">
        供仓位计算口径与复盘「仓位合规」维度使用；留空权益则仅按比例口径计算。
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-5">
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          账户权益（元）
          <input
            className={inputClass}
            value={equity}
            onChange={(e) => setEquity(e.target.value)}
            placeholder="100000"
            inputMode="decimal"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          单笔风险 %
          <input
            className={inputClass}
            value={riskPct}
            onChange={(e) => setRiskPct(e.target.value)}
            placeholder="0.75"
            inputMode="decimal"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          最多持仓数
          <input
            className={inputClass}
            value={maxPositions}
            onChange={(e) => setMaxPositions(e.target.value)}
            placeholder="5"
            inputMode="numeric"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          单票市值上限 %
          <input
            className={inputClass}
            value={maxPosPct}
            onChange={(e) => setMaxPosPct(e.target.value)}
            placeholder="20"
            inputMode="decimal"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          组合总风险上限 %
          <input
            className={inputClass}
            value={maxPortfolioRisk}
            onChange={(e) => setMaxPortfolioRisk(e.target.value)}
            placeholder="4"
            inputMode="decimal"
          />
        </label>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          disabled={submitting}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:bg-gray-300"
        >
          {submitting ? '保存中...' : '保存参数'}
        </button>
        {errors.length > 0 && (
          <div role="alert" className="text-xs text-red-600">
            {errors.join('；')}
          </div>
        )}
        {saved && <div className="text-xs text-green-600">✓ 已保存</div>}
      </div>
    </div>
  );
};
