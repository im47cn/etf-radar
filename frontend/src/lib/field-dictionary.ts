/**
 * REQ-018: 问号 tooltip 字段定义来源。
 * 键为字段名/概念名, 值为简短说明文字。
 */
export const FIELD_DICTIONARY: Record<string, string> = {
  strength: '0-100 评分, 多周期动量加权后映射, ≥60 为走强。',
  mapping_score:
    'A 股 ETF 与美股主题的相关度评分 (60 日滚动 Pearson 相关性 × 100), 越高映射越可靠。',
  confidence: '映射可靠性档位: 精确匹配=90, 宽主题替代=60。',
  resonance: '共振: 两边在多个周期同向走强或走弱, 适合优先观察。',
  transmission: '传导: 美股已先动, A 股尚未跟上, 适合观察隔夜补涨/补跌。',
  divergence: '背离: 美股与 A 股走势不同步, 需二次确认。',
};
