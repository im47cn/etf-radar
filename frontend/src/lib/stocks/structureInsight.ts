import type { AggregatedStock } from '@/types/holdings';

export type ThemeStructure =
  | 'head_led'
  | 'broad_strength'
  | 'divergent'
  | 'weak'
  | 'no_data';

export interface StructureDiagnosis {
  type: ThemeStructure;
  text: string;
  validCount: number;
  meanStrength: number | null;
}

/**
 * 主题结构诊断（基于 strength_60d 分布）。
 *
 * 规则优先级（先匹配优先）：
 *   no_data: 全部 strength 为 null
 *   broad_strength: ≥ 6 只 strength ≥ 70
 *   head_led: 1-2 只 strength ≥ 80 且其他 < 60
 *   weak: 均值 < 50
 *   divergent: 其他情况（强弱分化）
 */
export function diagnoseStructure(stocks: AggregatedStock[]): StructureDiagnosis {
  const strengths = stocks
    .map(s => s.indicators?.strength_60d)
    .filter((v): v is number => v !== null && v !== undefined);

  if (strengths.length === 0) {
    return { type: 'no_data', text: '本主题暂无指标数据', validCount: 0, meanStrength: null };
  }

  const mean = strengths.reduce((a, b) => a + b, 0) / strengths.length;
  const strong = strengths.filter(v => v >= 70).length;
  const veryStrong = strengths.filter(v => v >= 80).length;
  const weak = strengths.filter(v => v < 60).length;

  if (strong >= 6) {
    return {
      type: 'broad_strength',
      text: `本主题 ${strong} 只股票强度 ≥ 70，全面走强`,
      validCount: strengths.length,
      meanStrength: Math.round(mean),
    };
  }
  if (veryStrong >= 1 && veryStrong <= 2 && weak >= strengths.length - veryStrong - 1) {
    return {
      type: 'head_led',
      text: `本主题由 ${veryStrong} 只龙头带动，其他成分股偏中性`,
      validCount: strengths.length,
      meanStrength: Math.round(mean),
    };
  }
  if (mean < 50) {
    return {
      type: 'weak',
      text: `本主题整体偏弱（均值 ${Math.round(mean)}），建议观望`,
      validCount: strengths.length,
      meanStrength: Math.round(mean),
    };
  }
  return {
    type: 'divergent',
    text: `本主题强度分化（均值 ${Math.round(mean)}，强者 ${veryStrong} 弱者 ${weak}），结构不健康`,
    validCount: strengths.length,
    meanStrength: Math.round(mean),
  };
}
