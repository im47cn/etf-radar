import type { ThemeMetric, ThemeSignalEntry } from '@/lib/portfolio/types';

export const themesMock: ThemeMetric[] = [
  {
    id: 'storage_dram',
    name: '存储芯片',
    primary_cn: '512480',
    strength:    { short: 95, mid: 99, long: 99, composite: 98 },  // 不直接用
    us_strength: { short: 99, mid: 96, long: 99, composite: 98 },
    cn_strength: { short: 96, mid: 99, long: 98, composite: 98 },
  },
  {
    id: 'robotics_theme',
    name: '机器人',
    primary_cn: '562500',
    strength:    { short: 70, mid: 70, long: 70, composite: 70 },
    us_strength: { short: 72, mid: 68, long: 65, composite: 68 },
    cn_strength: { short: 70, mid: 70, long: 70, composite: 70 },
  },
  {
    id: 'weak_theme',
    name: '弱势主题',
    primary_cn: '999999',
    strength:    { short: 10, mid: 10, long: 10, composite: 10 },
    us_strength: { short: 10, mid: 10, long: 10, composite: 10 },
    cn_strength: { short: 12, mid: 8,  long: 11, composite: 10 },
  },
];

export const themeSignalsMock: ThemeSignalEntry[] = [
  { theme_id: 'storage_dram',   signal: 'resonance' },
  { theme_id: 'robotics_theme', signal: 'transmission' },
  { theme_id: 'weak_theme',     signal: 'divergence' },
];
