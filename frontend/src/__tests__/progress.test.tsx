import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  Progress,
  ProgressTrack,
  ProgressIndicator,
  ProgressLabel,
  ProgressValue,
} from '@/components/ui/progress';

describe('Progress', () => {
  it('Progress 渲染 data-slot=progress（含内部 Track/Indicator）', () => {
    render(<Progress value={50} />);
    const root = document.querySelector('[data-slot="progress"]');
    expect(root).not.toBeNull();
    // Progress 内部渲染了 Track 和 Indicator
    expect(document.querySelector('[data-slot="progress-track"]')).not.toBeNull();
    expect(document.querySelector('[data-slot="progress-indicator"]')).not.toBeNull();
  });

  it('ProgressTrack 在 Root 内可独立渲染', () => {
    render(
      <Progress value={0}>
        <ProgressTrack />
      </Progress>,
    );
    // Progress 本身已渲染一个 Track, 加上 children 里的 Track, 应有 2 个
    const tracks = document.querySelectorAll('[data-slot="progress-track"]');
    expect(tracks.length).toBeGreaterThanOrEqual(2);
  });

  it('ProgressIndicator 在 Root 内渲染 data-slot', () => {
    render(
      <Progress value={0}>
        <ProgressTrack>
          <ProgressIndicator />
        </ProgressTrack>
      </Progress>,
    );
    const indicators = document.querySelectorAll('[data-slot="progress-indicator"]');
    expect(indicators.length).toBeGreaterThanOrEqual(1);
  });

  it('ProgressLabel 在 Root 内渲染', () => {
    render(
      <Progress value={0}>
        <ProgressLabel>加载中</ProgressLabel>
      </Progress>,
    );
    expect(screen.getByText('加载中')).toBeInTheDocument();
  });

  it('ProgressValue 在 Root 内渲染', () => {
    render(
      <Progress value={50}>
        <ProgressValue>50%</ProgressValue>
      </Progress>,
    );
    expect(screen.getByText('50%')).toBeInTheDocument();
  });
});
