import { describe, it, expect } from 'vitest';
import { derivePositions } from '../derivePositions';
import type { Trade } from '../types';

// 构造 Trade 行（推导只依赖 code/name/side/trade_date/price/shares/stop_after/created_at）
let seq = 0;
function trade(over: Partial<Trade> & Pick<Trade, 'code' | 'side' | 'price' | 'shares'>): Trade {
  seq += 1;
  const d = over.trade_date ?? '2026-08-01';
  return {
    id:         `00000000-0000-4000-8000-${String(seq).padStart(12, '0')}`,
    user_id:    '00000000-0000-4000-8000-000000000001',
    name:       over.name ?? '测试股',
    trade_date: d,
    stop_after: over.stop_after !== undefined ? over.stop_after : null,
    reason:     null,
    created_at: over.created_at ?? `${d}T10:${String(seq % 60).padStart(2, '0')}:00Z`,
    updated_at: '',
    ...over,
  } as Trade;
}

describe('derivePositions', () => {
  it('空流水 → 空持仓', () => {
    expect(derivePositions([])).toEqual([]);
  });

  it('open 建仓：avg_cost=price，stop_after 即止损位', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open', price: 1700, shares: 100, stop_after: 1560 }),
    ]);
    expect(pos).toEqual([
      { code: '600519', name: '测试股', shares: 100, avg_cost: 1700, stop_current: 1560 },
    ]);
  });

  it('open 未带止损 → stop_current=null', () => {
    const pos = derivePositions([trade({ code: '600519', side: 'open', price: 10, shares: 100 })]);
    expect(pos[0].stop_current).toBeNull();
  });

  it('add 加权平均成本并累加份额', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open', price: 100, shares: 100 }),
      trade({ code: '600519', side: 'add',  price: 110, shares: 100 }),
    ]);
    expect(pos[0].shares).toBe(200);
    expect(pos[0].avg_cost).toBe(105); // (100*100+110*100)/200
  });

  it('add 携带 stop_after → 更新止损位', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open', price: 100, shares: 100, stop_after: 90 }),
      trade({ code: '600519', side: 'add',  price: 110, shares: 100, stop_after: 100 }),
    ]);
    expect(pos[0].stop_current).toBe(100);
  });

  it('add 未带 stop_after → 保留原止损位', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open', price: 100, shares: 100, stop_after: 90 }),
      trade({ code: '600519', side: 'add',  price: 110, shares: 100 }),
    ]);
    expect(pos[0].stop_current).toBe(90);
  });

  it('reduce 扣减份额、成本口径不变', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open',   price: 100, shares: 200 }),
      trade({ code: '600519', side: 'reduce', price: 120, shares: 100 }),
    ]);
    expect(pos[0]).toMatchObject({ shares: 100, avg_cost: 100 });
  });

  it('reduce 后清零 → 持仓移除', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open',   price: 100, shares: 100 }),
      trade({ code: '600519', side: 'reduce', price: 120, shares: 100 }),
    ]);
    expect(pos).toEqual([]);
  });

  it('超额 reduce（脏数据）→ 视同清仓不产生负份额', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open',   price: 100, shares: 100 }),
      trade({ code: '600519', side: 'reduce', price: 120, shares: 999 }),
    ]);
    expect(pos).toEqual([]);
  });

  it('close 清仓移除', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open',  price: 100, shares: 100 }),
      trade({ code: '600519', side: 'close', price: 120, shares: 100 }),
    ]);
    expect(pos).toEqual([]);
  });

  it('清仓后重新 open → 新建仓（新成本，旧止损不残留）', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open',  price: 100, shares: 100, stop_after: 90 }),
      trade({ code: '600519', side: 'close', price: 120, shares: 100 }),
      trade({ code: '600519', side: 'open',  price: 150, shares: 50 }),
    ]);
    expect(pos).toEqual([
      { code: '600519', name: '测试股', shares: 50, avg_cost: 150, stop_current: null },
    ]);
  });

  it('容错：无持仓的 add 视作 open、reduce/close 忽略', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'reduce', price: 100, shares: 100 }),
      trade({ code: '000001', side: 'close',  price: 10,  shares: 100 }),
      trade({ code: '000001', side: 'add',    price: 12,  shares: 200 }),
    ]);
    expect(pos).toEqual([
      { code: '000001', name: '测试股', shares: 200, avg_cost: 12, stop_current: null },
    ]);
  });

  it('按 trade_date 升序回放（乱序输入同一结果）', () => {
    const ordered = derivePositions([
      trade({ code: '600519', side: 'open',   price: 100, shares: 100, trade_date: '2026-08-01' }),
      trade({ code: '600519', side: 'add',    price: 110, shares: 100, trade_date: '2026-08-05' }),
      trade({ code: '600519', side: 'reduce', price: 120, shares: 50,  trade_date: '2026-08-10' }),
    ]);
    const shuffled = derivePositions([
      trade({ code: '600519', side: 'reduce', price: 120, shares: 50,  trade_date: '2026-08-10' }),
      trade({ code: '600519', side: 'open',   price: 100, shares: 100, trade_date: '2026-08-01' }),
      trade({ code: '600519', side: 'add',    price: 110, shares: 100, trade_date: '2026-08-05' }),
    ]);
    expect(shuffled).toEqual(ordered);
    // open 100@100 + add 110@100 → avg 105；reduce 50 股成本口径不变
    expect(ordered[0]).toMatchObject({ shares: 150, avg_cost: 105 });
  });

  it('同日多笔按 created_at 升序（先开后加）', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'add',  price: 110, shares: 100, trade_date: '2026-08-01', created_at: '2026-08-01T09:35:00Z' }),
      trade({ code: '600519', side: 'open', price: 100, shares: 100, trade_date: '2026-08-01', created_at: '2026-08-01T09:30:00Z' }),
    ]);
    expect(pos[0]).toMatchObject({ shares: 200, avg_cost: 105 });
  });

  it('多标的并行持仓互不干扰', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open', price: 100, shares: 100 }),
      trade({ code: '000001', side: 'open', price: 10,  shares: 1000 }),
      trade({ code: '600519', side: 'reduce', price: 110, shares: 50 }),
    ]);
    expect(pos.map(p => p.code).sort()).toEqual(['000001', '600519']);
    expect(pos.find(p => p.code === '600519')).toMatchObject({ shares: 50, avg_cost: 100 });
    expect(pos.find(p => p.code === '000001')).toMatchObject({ shares: 1000, avg_cost: 10 });
  });

  it('加权平均成本四舍五入到 4 位小数（避免浮点尾差）', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open', price: 10.01, shares: 3 }),
      trade({ code: '600519', side: 'add',  price: 10.03, shares: 3 }),
    ]);
    // (10.01*3 + 10.03*3)/6 = 10.02 精确；构造非整除: 3+2 股
    const pos2 = derivePositions([
      trade({ code: '000001', side: 'open', price: 9.99, shares: 3 }),
      trade({ code: '000001', side: 'add',  price: 10.00, shares: 2 }),
    ]);
    expect(pos[0].avg_cost).toBe(10.02);
    // (9.99*3 + 10*2)/5 = 9.994
    expect(pos2[0].avg_cost).toBe(9.994);
  });

  it('加仓更新 name 为最新一笔的名称', () => {
    const pos = derivePositions([
      trade({ code: '600519', side: 'open', price: 100, shares: 100, name: '贵州茅台' }),
      trade({ code: '600519', side: 'add',  price: 110, shares: 100, name: '贵州茅台SH' }),
    ]);
    expect(pos[0].name).toBe('贵州茅台SH');
  });
});
