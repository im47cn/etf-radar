import type { EtfMetric } from '@/lib/portfolio/types';

export const etfsMock: EtfMetric[] = [
  {
    code: '512480',
    name: '半导体ETF国联安',
    tracking_index: '中证全指半导体',
    price: 2.481,
    strength: { short: 95, mid: 99, long: 99, composite: 98 },
  },
  {
    code: '999999',
    name: '弱势ETF',
    price: 1.0,
    strength: { short: 10, mid: 10, long: 10, composite: 10 },
  },
];
