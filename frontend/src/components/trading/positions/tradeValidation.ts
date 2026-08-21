// frontend/src/components/trading/positions/tradeValidation.ts
// 录入/编辑共用字段校验（TradeEntryForm 与 TradeEditForm 单一口径）

export interface TradeFieldValues {
  code:      string;
  name:      string;
  tradeDate: string;
  price:     string;
  shares:    string;
  stopAfter: string;
}

export const validateTradeFields = (v: TradeFieldValues): string[] => {
  const errs: string[] = [];
  if (!/^\d{6}$/.test(v.code.trim())) errs.push('代码须为 6 位数字');
  if (v.name.trim() === '') errs.push('请填写名称');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v.tradeDate)) errs.push('请填写交易日期');
  const p = Number(v.price);
  if (!(p > 0)) errs.push('价格须为正数');
  const s = Number(v.shares);
  if (!Number.isInteger(s) || s <= 0) errs.push('股数须为正整数');
  const stop = parseStopAfter(v.stopAfter);
  if (stop != null && !(stop > 0)) errs.push('止损位须为正数（可留空）');
  return errs;
};

/** 留空 → null，否则转数值（与 stop_after 可空口径一致）。 */
export const parseStopAfter = (stopAfter: string): number | null =>
  stopAfter.trim() === '' ? null : Number(stopAfter);
