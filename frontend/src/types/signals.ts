export type SignalType = 'resonance' | 'transmission' | 'divergence';

export type Votes = {
  short: SignalType | null;
  mid: SignalType | null;
  long: SignalType | null;
};

export interface TopTheme {
  id: string;
  name: string;
  primary_us: string;
  composite_strength: number;
}

export interface SignalsSummary {
  themes_total: number;
  etfs_total: number;
  resonance_count: number;
  transmission_count: number;
  divergence_count: number;
  top_theme: TopTheme | null;
}

export interface ThemeSignal {
  theme_id: string;
  signal: SignalType | null;
  trigger_cn_etf: string | null;
  votes: Votes;
  description: string;
}

export interface PairSignal {
  theme_id: string;
  cn_code: string;
  mapping_score: number | null;
  confidence: number;
  signal: SignalType | null;
  votes: Votes;
}

export interface SignalsFile {
  schema_version: string;
  generated_at: string;
  summary: SignalsSummary;
  theme_signals: ThemeSignal[];
  pair_signals: PairSignal[];
}
