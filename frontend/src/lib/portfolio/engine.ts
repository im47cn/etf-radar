import type {
  Holding, HoldingScore, ScoreInputs,
  ThemeMetric, EtfMetric, ThemeSignalEntry,
} from './types';
import { strengthTag, momentumTag, computeQuadrant, buildNarrative } from './rules';

export function scorePortfolio(inputs: ScoreInputs): HoldingScore[] {
  const etfByCode = new Map<string, EtfMetric>(inputs.etfs.map(e => [e.code, e]));
  const themeById = new Map<string, ThemeMetric>(
    inputs.themes.map(t => [t.id, t]),
  );
  const signalByTheme = new Map<string, ThemeSignalEntry>(
    inputs.themeSignals.map(s => [s.theme_id, s]),
  );

  return inputs.holdings.map(h => buildScore(h, etfByCode, themeById, signalByTheme));
}

function buildScore(
  h: Holding,
  etfByCode: Map<string, EtfMetric>,
  themeById: Map<string, ThemeMetric>,
  signalByTheme: Map<string, ThemeSignalEntry>,
): HoldingScore {
  const etf = etfByCode.get(h.etf_code);

  if (!etf) {
    // uncovered
    return {
      etfCode:      h.etf_code,
      status:       'uncovered',
      shares:       h.shares,
      costPrice:    h.cost_price,
      currentPrice: null,
      marketValue:  null,
      pnlPct:       null,
      pnlAbs:       null,
    };
  }

  // covered: 按 etf.theme_id 反查主题（缺失/未知则 theme=undefined, UI 兜底渲染）
  const theme = etf.theme_id ? themeById.get(etf.theme_id) : undefined;
  const signal = theme ? signalByTheme.get(theme.id) : undefined;
  const quadrant = computeQuadrant(etf.strength);
  const l2Tag = strengthTag(etf.strength.composite);
  const mTag  = momentumTag(etf.strength.short, etf.strength.mid);

  const marketValue = h.shares * etf.price;
  const pnlAbs = h.cost_price !== null
    ? (etf.price - h.cost_price) * h.shares
    : null;
  const pnlPct = h.cost_price !== null && h.cost_price > 0
    ? (etf.price - h.cost_price) / h.cost_price
    : null;

  const score: HoldingScore = {
    etfCode:      h.etf_code,
    status:       'covered',
    name:         etf.name,
    shares:       h.shares,
    costPrice:    h.cost_price,
    currentPrice: etf.price,
    marketValue,
    pnlAbs,
    pnlPct,
    selfStrength: etf.strength,
    themeId:      theme?.id,
    themeName:    theme?.name,
    themeUsStrength: theme?.us_strength,
    themeCnStrength: theme?.cn_strength,
    themeSignal:  signal?.signal,
    quadrant,
    l2Tag,
    momentumTag:  mTag,
  };
  score.narrative = buildNarrative(score);
  return score;
}
