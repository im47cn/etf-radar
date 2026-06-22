import type { EtfMetric } from '@/lib/portfolio/types';

export const etfsMock: EtfMetric[] = [
  {
    code: '512480',
    name: '半导体ETF国联安',
    tracking_index: '中证全指半导体',
    theme_id: 'storage_dram',
    price: 2.481,
    strength: { short: 95, mid: 99, long: 99, composite: 98 },
  },
  {
    code: '562500',
    name: '机器人ETF',
    tracking_index: '中证机器人',
    theme_id: 'robotics_theme',
    price: 1.50,
    strength: { short: 75, mid: 70, long: 65, composite: 70 },
  },
  {
    code: '159559',
    name: '机器人ETF景顺',
    tracking_index: '中证机器人产业',
    theme_id: 'robotics_theme',  // 同主题非 primary_cn
    price: 1.44,
    strength: { short: 73, mid: 76, long: 58, composite: 68 },
  },
  {
    code: '999999',
    name: '弱势ETF',
    theme_id: 'weak_theme',
    price: 1.0,
    strength: { short: 10, mid: 10, long: 10, composite: 10 },
  },
  {
    code: '888888',
    name: '孤儿ETF（theme_id 缺失，仿历史快照）',
    price: 2.0,
    strength: { short: 50, mid: 50, long: 50, composite: 50 },
    // 故意不填 theme_id
  },
];
