import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { HealthScore } from '@/types/rotation';
import { RotationHealthBar } from '../RotationHealthBar';

const mkHealth = (
  coverageScore: number,
  coverageGrade: HealthScore['coverage']['grade'],
  robustnessScore: number,
  robustnessGrade: HealthScore['robustness']['grade'],
): HealthScore => ({
  coverage: { score: coverageScore, grade: coverageGrade },
  robustness: { score: robustnessScore, grade: robustnessGrade },
});

describe('RotationHealthBar', () => {
  it('renders score numbers for both metrics', () => {
    render(<RotationHealthBar health={mkHealth(72, 'caution', 85, 'healthy')} />);
    expect(screen.getByText('72')).toBeInTheDocument();
    expect(screen.getByText('85')).toBeInTheDocument();
  });

  it('renders both labels', () => {
    render(<RotationHealthBar health={mkHealth(72, 'caution', 85, 'healthy')} />);
    expect(screen.getByText('覆盖度')).toBeInTheDocument();
    expect(screen.getByText('鲁棒度')).toBeInTheDocument();
  });

  it('renders both grade labels', () => {
    render(<RotationHealthBar health={mkHealth(72, 'caution', 85, 'healthy')} />);
    expect(screen.getByText('警示')).toBeInTheDocument();
    expect(screen.getByText('健康')).toBeInTheDocument();
  });

  it('applies green class for healthy grade', () => {
    const { container } = render(
      <RotationHealthBar health={mkHealth(90, 'healthy', 90, 'healthy')} />,
    );
    expect(container.querySelectorAll('.bg-green-100').length).toBe(2);
  });

  it('applies amber class for caution grade', () => {
    const { container } = render(
      <RotationHealthBar health={mkHealth(75, 'caution', 75, 'caution')} />,
    );
    expect(container.querySelectorAll('.bg-amber-100').length).toBe(2);
  });

  it('applies red class for imbalanced grade', () => {
    const { container } = render(
      <RotationHealthBar health={mkHealth(50, 'imbalanced', 50, 'imbalanced')} />,
    );
    expect(container.querySelectorAll('.bg-red-100').length).toBe(2);
  });

  it('shows em-dash placeholder when grade is insufficient', () => {
    render(<RotationHealthBar health={mkHealth(0, 'insufficient', 85, 'healthy')} />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('85')).toBeInTheDocument();
  });

  it('exposes status role and aria-label on each cell', () => {
    render(<RotationHealthBar health={mkHealth(72, 'caution', 85, 'healthy')} />);
    const cells = screen.getAllByRole('status');
    expect(cells).toHaveLength(2);
    expect(cells[0].getAttribute('aria-label')).toContain('覆盖度');
    expect(cells[0].getAttribute('aria-label')).toContain('72');
    expect(cells[0].getAttribute('aria-label')).toContain('警示');
  });
});
