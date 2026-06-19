import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { UIStateProvider } from '@/providers/UIStateProvider';
import { useUIState } from '@/providers/uiStateContext';
import { OnlyCnOnlyToggle } from '../OnlyCnOnlyToggle';

const StateProbe = () => {
  const { state } = useUIState();
  return <div data-testid="only">{String(state.onlyCnOnly)}</div>;
};

const renderToggle = () =>
  render(
    <MemoryRouter>
      <UIStateProvider>
        <OnlyCnOnlyToggle />
        <StateProbe />
      </UIStateProvider>
    </MemoryRouter>,
  );

describe('OnlyCnOnlyToggle', () => {
  it('initially unchecked, state false', () => {
    renderToggle();
    const cb = screen.getByLabelText('仅看 A 股专属') as HTMLInputElement;
    expect(cb.checked).toBe(false);
    expect(screen.getByTestId('only')).toHaveTextContent('false');
  });

  it('toggles state on click', async () => {
    const user = userEvent.setup();
    renderToggle();
    const cb = screen.getByLabelText('仅看 A 股专属') as HTMLInputElement;
    await user.click(cb);
    expect(cb.checked).toBe(true);
    expect(screen.getByTestId('only')).toHaveTextContent('true');
    await user.click(cb);
    expect(cb.checked).toBe(false);
    expect(screen.getByTestId('only')).toHaveTextContent('false');
  });
});
