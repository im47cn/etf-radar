export type DimName = 'short' | 'mid' | 'long' | 'composite';

export interface Returns {
  r_1d: number | null;
  r_5d: number | null;
  r_20d: number | null;
  r_60d: number | null;
  r_120d: number | null;
  r_ytd: number | null;
}

export interface Strength {
  short: number;
  mid: number;
  long: number;
  composite: number;
}

export interface Rank {
  short: number;
  mid: number;
  long: number;
  composite: number;
}

export interface Theme {
  id: string;
  name: string;
  us_etfs: string[];
  primary_us: string;
  tags: string[];
  note: string;
  returns: Returns;
  strength: Strength;
  rank: Rank;
}

export interface ThemesFile {
  schema_version: string;
  generated_at: string;
  themes: Theme[];
}
