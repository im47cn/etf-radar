import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EventItem } from '../EventItem';
import type { UserEvent } from '@/lib/portfolio/eventTypes';

const mk = (overrides: Partial<UserEvent> = {}): UserEvent => ({
  id: 'e1', user_id: 'u1', event_type: 'theme_quadrant_change',
  theme_id: 'cn_tech', event_signature: 'sig',
  payload: { version: 1, from: 'weak', to: 'leading', etf_codes: ['510300'] },
  asof_date: '2026-06-23',
  created_at: '2026-06-23T01:00:00Z', read_at: null,
  ...overrides,
} as UserEvent);

describe('EventItem', () => {
  it('象限切到 leading 显示利好（🟢）', () => {
    render(<EventItem event={mk()} themeName="科技" />);
    expect(screen.getByText(/科技/)).toBeInTheDocument();
    expect(screen.getByText(/领涨|强势/)).toBeInTheDocument();
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'green');
  });

  it('象限切到 weak 显示利空（🔴）', () => {
    render(<EventItem event={mk({
      event_type: 'theme_quadrant_change',
      payload: { version: 1, from: 'leading', to: 'weak', etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'red');
  });

  it('强度上穿显示利好', () => {
    render(<EventItem event={mk({
      event_type: 'theme_strength_cross_up',
      payload: { version: 1, threshold: 75, from: 70, to: 80, etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByText(/上穿|强势区/)).toBeInTheDocument();
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'green');
  });

  it('信号变共振显示利好', () => {
    render(<EventItem event={mk({
      event_type: 'theme_signal_change',
      payload: { version: 1, from: 'divergence', to: 'resonance', etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'green');
  });

  it('已读样式：灰底', () => {
    render(<EventItem event={mk({ read_at: '2026-06-23T02:00:00Z' })} themeName="科技" />);
    const root = screen.getByTestId('event-root');
    expect(root.className).toMatch(/bg-gray-50|opacity-/);
  });

  it('文案保持 L1+L2 立场（不含"买入/推荐"）', () => {
    render(<EventItem event={mk()} themeName="科技" />);
    const txt = document.body.textContent ?? '';
    expect(txt).not.toMatch(/推荐买入|建议买入|可买/);
  });

  it('未传 currentHoldings 不渲染副标题（向后兼容）', () => {
    render(<EventItem event={mk()} themeName="科技" />);
    expect(screen.queryByTestId('event-affected')).not.toBeInTheDocument();
  });

  it('传 currentHoldings 且仍持有 → 显示"影响你持仓的 XXX"', () => {
    render(<EventItem
      event={mk({
        payload: { version: 1, from: 'weak', to: 'leading', etf_codes: ['510300', '512760'] },
      })}
      themeName="科技"
      currentHoldings={new Set(['510300'])}
    />);
    const sub = screen.getByTestId('event-affected');
    expect(sub.textContent).toMatch(/影响你持仓的.*510300/);
    expect(sub.textContent).not.toMatch(/512760/);  // 未持有的不显示
  });

  it('传 currentHoldings 但已全部卖出 → 显示"曾涉及…已卖出"', () => {
    render(<EventItem
      event={mk({
        payload: { version: 1, from: 'weak', to: 'leading', etf_codes: ['510300'] },
      })}
      themeName="科技"
      currentHoldings={new Set(['999999'])}
    />);
    const sub = screen.getByTestId('event-affected');
    expect(sub.textContent).toMatch(/曾涉及你持仓的.*510300.*已卖出/);
  });

  it('payload.etf_codes 为空数组时不渲染副标题', () => {
    render(<EventItem
      event={mk({
        payload: { version: 1, from: 'weak', to: 'leading', etf_codes: [] },
      })}
      themeName="科技"
      currentHoldings={new Set(['510300'])}
    />);
    expect(screen.queryByTestId('event-affected')).not.toBeInTheDocument();
  });
});

describe('EventItem — tone 灰色分支', () => {
  it('象限切到 weakening（非 leading/weak）→ gray', () => {
    render(<EventItem event={mk({
      event_type: 'theme_quadrant_change',
      payload: { version: 1, from: 'leading', to: 'weakening', etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'gray');
  });

  it('象限切到 following（非 leading/weak）→ gray', () => {
    render(<EventItem event={mk({
      event_type: 'theme_quadrant_change',
      payload: { version: 1, from: 'leading', to: 'following', etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'gray');
  });
});

describe('EventItem — signal_change 非共振/背离', () => {
  it('信号切到 transmission（非 resonance/divergence）→ gray', () => {
    render(<EventItem event={mk({
      event_type: 'theme_signal_change',
      payload: { version: 1, from: 'resonance', to: 'transmission', etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'gray');
  });

  it('信号切到 divergence → red', () => {
    render(<EventItem event={mk({
      event_type: 'theme_signal_change',
      payload: { version: 1, from: 'resonance', to: 'divergence', etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'red');
  });
});

describe('EventItem — strength_cross_down', () => {
  it('强度下穿 → red', () => {
    render(<EventItem event={mk({
      event_type: 'theme_strength_cross_down',
      payload: { version: 1, threshold: 25, from: 30, to: 20, etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByTestId('event-color')).toHaveAttribute('data-color', 'red');
  });
});

describe('EventItem — label threshold 分支', () => {
  it('强度上穿 75 → 强势区文案', () => {
    render(<EventItem event={mk({
      event_type: 'theme_strength_cross_up',
      payload: { version: 1, threshold: 75, from: 70, to: 80, etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByText(/强势区/)).toBeInTheDocument();
  });

  it('强度上穿 50 → 上穿 50 文案', () => {
    render(<EventItem event={mk({
      event_type: 'theme_strength_cross_up',
      payload: { version: 1, threshold: 50, from: 40, to: 55, etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByText(/上穿 50/)).toBeInTheDocument();
    expect(screen.queryByText(/强势区/)).not.toBeInTheDocument();
  });

  it('强度上穿 25 → 上穿 25 文案', () => {
    render(<EventItem event={mk({
      event_type: 'theme_strength_cross_up',
      payload: { version: 1, threshold: 25, from: 20, to: 30, etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByText(/上穿 25/)).toBeInTheDocument();
  });

  it('强度下穿 25 → 弱势区文案', () => {
    render(<EventItem event={mk({
      event_type: 'theme_strength_cross_down',
      payload: { version: 1, threshold: 25, from: 30, to: 20, etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByText(/弱势区/)).toBeInTheDocument();
  });

  it('强度下穿 50 → 下穿 50 文案', () => {
    render(<EventItem event={mk({
      event_type: 'theme_strength_cross_down',
      payload: { version: 1, threshold: 50, from: 55, to: 45, etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByText(/下穿 50/)).toBeInTheDocument();
  });

  it('强度下穿 75 → 下穿 75 文案', () => {
    render(<EventItem event={mk({
      event_type: 'theme_strength_cross_down',
      payload: { version: 1, threshold: 75, from: 80, to: 70, etf_codes: ['510300'] },
    })} themeName="科技" />);
    expect(screen.getByText(/下穿 75/)).toBeInTheDocument();
  });
});
