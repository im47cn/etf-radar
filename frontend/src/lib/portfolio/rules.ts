import type { HoldingScore, Strength, StrengthTag, MomentumTag, Quadrant } from './types';

export function strengthTag(composite: number): StrengthTag {
  if (composite >= 75) return '偏强';
  if (composite >= 50) return '中性偏强';
  if (composite >= 25) return '中性偏弱';
  return '偏弱';
}

export function momentumTag(short: number, mid: number): MomentumTag | null {
  if (short >= 70 && mid >= 60) return '动量向上';
  if (short <= 30 && mid <= 40) return '动量向下';
  return null;
}

export function computeQuadrant(s: Strength): Quadrant {
  const longHigh  = s.long  >= 50;
  const shortHigh = s.short >= 50;
  if (longHigh  && shortHigh) return 'leading';
  if (longHigh  && !shortHigh) return 'weakening';
  if (!longHigh && shortHigh) return 'following';
  return 'weak';
}

export function quadrantLabel(q: Quadrant): string {
  switch (q) {
    case 'leading':   return '领涨象限';
    case 'weakening': return '转弱象限';
    case 'following': return '跟随象限';
    case 'weak':      return '弱势象限';
  }
}

export function buildNarrative(score: HoldingScore): string {
  if (score.status !== 'covered' || !score.quadrant || !score.selfStrength) {
    return '';
  }
  const parts: string[] = [];
  parts.push(`位于${quadrantLabel(score.quadrant)}`);
  parts.push(`综合强度 ${score.selfStrength.composite} 分位`);

  const mid = score.selfStrength.mid;
  if (mid >= 75) parts.push('中周期强劲');
  else if (mid <= 25) parts.push('中周期走弱');

  if (score.themeSignal === 'resonance')    parts.push('美股 A 股共振');
  if (score.themeSignal === 'transmission') parts.push('美股领先 A 股待跟随');
  if (score.themeSignal === 'divergence')   parts.push('美股 A 股背离');

  return parts.join('，');
}
