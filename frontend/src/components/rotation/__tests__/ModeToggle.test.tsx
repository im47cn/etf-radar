import { render, screen } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ModeToggle } from '../ModeToggle';

describe('ModeToggle', () => {
  it('renders both modes with counts', () => {
    render(<ModeToggle mode="us" onChange={() => {}} usCount={14} cnCount={21} />);
    expect(screen.getByText(/美股/)).toBeInTheDocument();
    expect(screen.getByText(/A股/)).toBeInTheDocument();
    expect(screen.getByText('14')).toBeInTheDocument();
    expect(screen.getByText('21')).toBeInTheDocument();
  });

  it('highlights active mode', () => {
    render(<ModeToggle mode="cn" onChange={() => {}} usCount={14} cnCount={21} />);
    const cnBtn = screen.getByRole('button', { name: /A股/ });
    expect(cnBtn).toHaveAttribute('aria-pressed', 'true');
    const usBtn = screen.getByRole('button', { name: /美股/ });
    expect(usBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('calls onChange when switched', () => {
    const fn = vi.fn();
    render(<ModeToggle mode="us" onChange={fn} usCount={14} cnCount={21} />);
    fireEvent.click(screen.getByRole('button', { name: /A股/ }));
    expect(fn).toHaveBeenCalledWith('cn');
  });
});
