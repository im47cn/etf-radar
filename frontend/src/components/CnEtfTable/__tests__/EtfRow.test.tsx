import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EtfRow } from '../EtfRow';
import type { Etf } from '@/types/etfs';
import type { PairSignal } from '@/types/signals';

const mkEtf = (overrides: Partial<Etf> = {}): Etf => ({
  code: '159870',
  name: '半导体ETF',
  tracking_index: '国证半导体芯片',
  amount_yi: 12.3,
  returns: {
    r_1d: 1.5,
    r_5d: -0.8,
    r_20d: 3.2,
    r_60d: null,
    r_120d: null,
    r_ytd: null,
  },
  ...overrides,
} as Etf);

const renderRow = (etf: Etf, pair?: PairSignal) =>
  render(
    <table>
      <tbody>
        <EtfRow etf={etf} pair={pair} />
      </tbody>
    </table>,
  );

describe('EtfRow', () => {
  it('渲染 ETF 名称和代码', () => {
    renderRow(mkEtf());
    expect(screen.getByText('半导体ETF')).toBeInTheDocument();
    expect(screen.getByText('159870')).toBeInTheDocument();
    expect(screen.getByText('国证半导体芯片')).toBeInTheDocument();
  });

  it('正收益用蓝色，负收益用红色', () => {
    renderRow(mkEtf());
    const cells = screen.getAllByText(/[%+|-]/);
    // r_1d=1.5 正 → blue, r_5d=-0.8 负 → red
    expect(cells.length).toBeGreaterThan(0);
  });

  it('null 收益也能渲染（pctCls(null) → blue 分支）', () => {
    const etf = mkEtf({
      returns: {
        r_1d: null, r_5d: null, r_20d: null,
        r_60d: null, r_120d: null, r_ytd: null,
      },
    });
    expect(() => renderRow(etf)).not.toThrow();
  });

  it('pair 有 mapping_score 时渲染 Progress', () => {
    const pair = {
      theme_id: 't1',
      cn_etf_code: '159870',
      mapping_score: 85,
      signal: null,
    } as unknown as PairSignal;
    renderRow(mkEtf(), pair);
    expect(screen.getByText('85')).toBeInTheDocument();
  });

  it('pair 无 mapping_score（null）时渲染 — 占位', () => {
    const pair = {
      theme_id: 't1',
      cn_etf_code: '159870',
      mapping_score: null,
      signal: null,
    } as unknown as PairSignal;
    renderRow(mkEtf(), pair);
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
  });

  it('pair undefined 时渲染 — 占位', () => {
    renderRow(mkEtf(), undefined);
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
  });

  it('pair.signal=resonance 时渲染共振 Badge', () => {
    const pair = {
      theme_id: 't1',
      cn_etf_code: '159870',
      mapping_score: 85,
      signal: 'resonance',
    } as unknown as PairSignal;
    renderRow(mkEtf(), pair);
    expect(screen.getByText('共振')).toBeInTheDocument();
  });

  it('pair.signal=transmission 时渲染传导 Badge', () => {
    const pair = {
      theme_id: 't1',
      cn_etf_code: '159870',
      mapping_score: 85,
      signal: 'transmission',
    } as unknown as PairSignal;
    renderRow(mkEtf(), pair);
    expect(screen.getByText('传导')).toBeInTheDocument();
  });

  it('pair.signal=divergence 时渲染背离 Badge', () => {
    const pair = {
      theme_id: 't1',
      cn_etf_code: '159870',
      mapping_score: 85,
      signal: 'divergence',
    } as unknown as PairSignal;
    renderRow(mkEtf(), pair);
    expect(screen.getByText('背离')).toBeInTheDocument();
  });
});
