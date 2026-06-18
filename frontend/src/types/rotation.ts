export type Quadrant = 'leading' | 'rising' | 'lagging' | 'fading';

export interface RotationPoint {
  themeId: string;
  themeName: string;
  x: number;
  y: number;
  size: number;
  quadrant: Quadrant;
  tags: string[];
}

export type HealthGrade = 'healthy' | 'caution' | 'imbalanced' | 'insufficient';

export interface HealthMetric {
  score: number;
  grade: HealthGrade;
}

export interface HealthScore {
  coverage: HealthMetric;
  robustness: HealthMetric;
}
