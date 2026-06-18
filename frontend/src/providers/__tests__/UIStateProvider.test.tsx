import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { UIStateProvider } from '../UIStateProvider';
import { useUIState } from '../uiStateContext';

const StateProbe = () => {
  const { state, dispatch } = useUIState();
  const loc = useLocation();
  return (
    <div>
      <div data-testid="theme">{state.selectedThemeId ?? '(none)'}</div>
      <div data-testid="dim">{state.dimension}</div>
      <div data-testid="sig">{state.signalFilter}</div>
      <div data-testid="search">{state.searchQuery}</div>
      <div data-testid="search-url">{loc.search}</div>
      <button onClick={() => dispatch({ type: 'SELECT_THEME', id: 'ai' })}>select-ai</button>
      <button onClick={() => dispatch({ type: 'SELECT_THEME', id: null })}>clear-theme</button>
      <button onClick={() => dispatch({ type: 'SET_DIM', dim: 'long' })}>dim-long</button>
      <button onClick={() => dispatch({ type: 'SET_DIM', dim: 'short' })}>dim-short</button>
      <button onClick={() => dispatch({ type: 'SET_SIGNAL_FILTER', v: 'resonance' })}>sig-res</button>
      <button onClick={() => dispatch({ type: 'SET_SIGNAL_FILTER', v: 'all' })}>sig-all</button>
      <button onClick={() => dispatch({ type: 'SET_SEARCH', q: 'foo' })}>search-foo</button>
    </div>
  );
};

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <UIStateProvider>
        <StateProbe />
      </UIStateProvider>
    </MemoryRouter>,
  );

describe('UIStateProvider', () => {
  describe('initial state from URL', () => {
    it('parses theme/dim/sig from search params', () => {
      renderAt('/?theme=ai&dim=long&sig=resonance');
      expect(screen.getByTestId('theme')).toHaveTextContent('ai');
      expect(screen.getByTestId('dim')).toHaveTextContent('long');
      expect(screen.getByTestId('sig')).toHaveTextContent('resonance');
    });

    it('falls back to defaults when params are absent', () => {
      renderAt('/');
      expect(screen.getByTestId('theme')).toHaveTextContent('(none)');
      expect(screen.getByTestId('dim')).toHaveTextContent('short');
      expect(screen.getByTestId('sig')).toHaveTextContent('all');
    });

    it('falls back to defaults for illegal dim/sig', () => {
      renderAt('/?dim=bogus&sig=nope');
      expect(screen.getByTestId('dim')).toHaveTextContent('short');
      expect(screen.getByTestId('sig')).toHaveTextContent('all');
    });

    it('searchQuery is always memory-only (never read from URL)', () => {
      renderAt('/?q=irrelevant');
      expect(screen.getByTestId('search')).toHaveTextContent('');
    });
  });

  describe('dispatch writes URL', () => {
    it('SELECT_THEME sets theme param', async () => {
      const user = userEvent.setup();
      renderAt('/');
      await user.click(screen.getByText('select-ai'));
      expect(screen.getByTestId('search-url').textContent).toContain('theme=ai');
      expect(screen.getByTestId('theme')).toHaveTextContent('ai');
    });

    it('SELECT_THEME with null removes theme param', async () => {
      const user = userEvent.setup();
      renderAt('/?theme=ai');
      await user.click(screen.getByText('clear-theme'));
      expect(screen.getByTestId('search-url').textContent).not.toContain('theme=');
      expect(screen.getByTestId('theme')).toHaveTextContent('(none)');
    });

    it('SET_DIM omits dim=short (default) from URL', async () => {
      const user = userEvent.setup();
      renderAt('/?dim=long');
      await user.click(screen.getByText('dim-short'));
      expect(screen.getByTestId('search-url').textContent).not.toContain('dim=');
      expect(screen.getByTestId('dim')).toHaveTextContent('short');
    });

    it('SET_DIM writes non-default value to URL', async () => {
      const user = userEvent.setup();
      renderAt('/');
      await user.click(screen.getByText('dim-long'));
      expect(screen.getByTestId('search-url').textContent).toContain('dim=long');
    });

    it('SET_SIGNAL_FILTER omits sig=all (default) from URL', async () => {
      const user = userEvent.setup();
      renderAt('/?sig=resonance');
      await user.click(screen.getByText('sig-all'));
      expect(screen.getByTestId('search-url').textContent).not.toContain('sig=');
    });

    it('SET_SIGNAL_FILTER writes non-default value to URL', async () => {
      const user = userEvent.setup();
      renderAt('/');
      await user.click(screen.getByText('sig-res'));
      expect(screen.getByTestId('search-url').textContent).toContain('sig=resonance');
    });

    it('SET_SEARCH updates state without touching URL', async () => {
      const user = userEvent.setup();
      renderAt('/');
      await user.click(screen.getByText('search-foo'));
      expect(screen.getByTestId('search')).toHaveTextContent('foo');
      expect(screen.getByTestId('search-url').textContent).toBe('');
    });

    it('preserves unrelated params when updating one field', async () => {
      const user = userEvent.setup();
      renderAt('/?dim=long&sig=resonance');
      await user.click(screen.getByText('select-ai'));
      const search = screen.getByTestId('search-url').textContent ?? '';
      expect(search).toContain('theme=ai');
      expect(search).toContain('dim=long');
      expect(search).toContain('sig=resonance');
    });
  });

  it('throws when useUIState is called outside provider', () => {
    const Boom = () => {
      useUIState();
      return null;
    };
    // suppress React error boundary noise
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() =>
      act(() => {
        render(<Boom />);
      }),
    ).toThrow(/useUIState must be inside UIStateProvider/);
    spy.mockRestore();
  });
});
