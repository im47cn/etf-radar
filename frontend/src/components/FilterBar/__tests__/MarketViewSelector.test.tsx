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
  it('默认渲染 us 高亮', () => {
    renderWith();
    expect(screen.getByTestId('mv-val').textContent).toBe('us');
    expect(screen.getByRole('button', { name: /美股/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('点击 A 股全部 切到 cn-all', () => {
    renderWith();
    fireEvent.click(screen.getByRole('button', { name: /A股全部/i }));
    expect(screen.getByTestId('mv-val').textContent).toBe('cn-all');
  });

  it('点击 A 股专属 切到 cn-only', () => {
    renderWith();
    fireEvent.click(screen.getByRole('button', { name: /A股专属/i }));
    expect(screen.getByTestId('mv-val').textContent).toBe('cn-only');
  });

  it('role=group + 三个 aria-pressed 按钮', () => {
    renderWith();
    const group = screen.getByRole('group', { name: /市场视角/i });
    expect(group).toBeInTheDocument();
    const btns = screen.getAllByRole('button');
    expect(btns).toHaveLength(3);
    btns.forEach((b) => expect(b).toHaveAttribute('aria-pressed'));
  });
});
