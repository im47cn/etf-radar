import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { useUIState } from '@/providers/uiStateContext';
import { MarketViewSelector } from '../MarketViewSelector';

const Spy = () => {
  const { state } = useUIState();
  return <span data-testid="mv-val">{state.marketView}</span>;
};

const renderWith = () =>
  render(
    <MemoryRouter>
      <UIStateProvider>
        <MarketViewSelector />
        <Spy />
      </UIStateProvider>
    </MemoryRouter>,
  );

describe('MarketViewSelector', () => {
  it('默认渲染 cn-all 高亮 (A 股投资者开箱即用)', () => {
    renderWith();
    expect(screen.getByTestId('mv-val').textContent).toBe('cn-all');
    expect(screen.getByRole('button', { name: /A股/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('点击 美股 切到 us', () => {
    renderWith();
    fireEvent.click(screen.getByRole('button', { name: /美股/i }));
    expect(screen.getByTestId('mv-val').textContent).toBe('us');
  });

  it('role=group + 两个 aria-pressed 按钮', () => {
    renderWith();
    const group = screen.getByRole('group', { name: /市场视角/i });
    expect(group).toBeInTheDocument();
    const btns = screen.getAllByRole('button');
    expect(btns).toHaveLength(2);
    btns.forEach((b) => expect(b).toHaveAttribute('aria-pressed'));
  });
});
