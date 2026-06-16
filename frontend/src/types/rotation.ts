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
