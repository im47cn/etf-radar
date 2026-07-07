// 免费版持仓数量上限；会员不限。
// 值来自集中配置 appConfig（读环境变量 VITE_FREE_HOLDINGS_LIMIT，缺省回落 5）。
// 须与后端 005_holdings_free_limit.sql 触发器阈值保持一致。
import { appConfig } from '@/lib/config/appConfig';

export const FREE_HOLDINGS_LIMIT = appConfig.freeHoldingsLimit;
