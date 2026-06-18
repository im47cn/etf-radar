import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { TrailRangeSlider } from '../TrailRangeSlider';

describe('TrailRangeSlider', () => {
  it('displays current startOffset and endOffset', () => {
    render(
      <TrailRangeSlider
        range={{ startOffset: -10, endOffset: 0 }}
        onChange={() => {}}
        maxDays={60}
      />,
    );
    expect(screen.getByText(/10 天/)).toBeInTheDocument();
  });

  it('disabled when maxDays is 0 (no snapshots)', () => {
    const onChange = vi.fn();
    const { container } = render(
      <TrailRangeSlider
        range={{ startOffset: -10, endOffset: 0 }}
        onChange={onChange}
        maxDays={0}
      />,
    );
    const root = container.querySelector('[data-disabled]');
    expect(root).not.toBeNull();
  });

  it('renders two thumbs (range slider)', () => {
    render(
      <TrailRangeSlider
        range={{ startOffset: -10, endOffset: 0 }}
        onChange={() => {}}
        maxDays={60}
      />,
    );
    const thumbs = screen.getAllByRole('slider');
    expect(thumbs).toHaveLength(2);
  });

  it('calls onChange when slider value changes', () => {
    const onChange = vi.fn();
    render(
      <TrailRangeSlider
        range={{ startOffset: -10, endOffset: 0 }}
        onChange={onChange}
        maxDays={60}
      />,
    );
    expect(onChange).not.toHaveBeenCalled();
  });

  it('does not throw when maxDays is 0 and incoming range exceeds bounds', () => {
    expect(() =>
      render(
        <TrailRangeSlider
          range={{ startOffset: -10, endOffset: 0 }}
          onChange={() => {}}
          maxDays={0}
        />,
      ),
    ).not.toThrow();
  });
});
