import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TimelineControls } from '../TimelineControls';

const dates = ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04'];

const baseProps = {
  dates,
  currentDate: '2026-01-04',
  onDateChange: vi.fn(),
  playing: false,
  speed: 1 as const,
  onPlay: vi.fn(),
  onPause: vi.fn(),
  onStop: vi.fn(),
  onSpeedChange: vi.fn(),
  showTrails: false,
  onToggleTrails: vi.fn(),
};

describe('TimelineControls', () => {
  it('slider change calls onDateChange with corresponding date', () => {
    const onDateChange = vi.fn();
    render(<TimelineControls {...baseProps} onDateChange={onDateChange} />);
    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '1' } });
    expect(onDateChange).toHaveBeenCalledWith('2026-01-02');
  });

  it('play button shows Play icon when paused, calls onPlay', async () => {
    const onPlay = vi.fn();
    render(<TimelineControls {...baseProps} playing={false} onPlay={onPlay} />);
    const btn = screen.getByLabelText('播放');
    await userEvent.click(btn);
    expect(onPlay).toHaveBeenCalled();
  });

  it('shows Pause when playing, calls onPause on click', async () => {
    const onPause = vi.fn();
    render(<TimelineControls {...baseProps} playing={true} onPause={onPause} />);
    const btn = screen.getByLabelText('暂停');
    await userEvent.click(btn);
    expect(onPause).toHaveBeenCalled();
  });

  it('speed segmented control: clicking 2x calls onSpeedChange(2)', async () => {
    const onSpeedChange = vi.fn();
    render(<TimelineControls {...baseProps} onSpeedChange={onSpeedChange} />);
    await userEvent.click(screen.getByText('2x'));
    expect(onSpeedChange).toHaveBeenCalledWith(2);
  });

  it('trails checkbox toggles onToggleTrails', async () => {
    const onToggleTrails = vi.fn();
    render(<TimelineControls {...baseProps} onToggleTrails={onToggleTrails} />);
    await userEvent.click(screen.getByLabelText('显示尾迹'));
    expect(onToggleTrails).toHaveBeenCalledWith(true);
  });

  it('disabled=true disables slider, play, stop, speed, trails', () => {
    render(<TimelineControls {...baseProps} disabled={true} />);
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(screen.getByLabelText('播放')).toBeDisabled();
    expect(screen.getByLabelText('停止')).toBeDisabled();
    expect(screen.getByText('1x')).toBeDisabled();
    expect(screen.getByLabelText('显示尾迹')).toBeDisabled();
  });
});
