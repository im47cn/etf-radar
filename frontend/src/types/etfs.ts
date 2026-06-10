import type { Returns, Strength } from './themes';

export interface Etf {
  code: string;
  name: string;
  tracking_index: string;
  returns: Returns;
  amount_yi: number | null;
  price: number | null;
  strength: Strength;
}

export interface EtfsFile {
  schema_version: string;
  generated_at: string;
  etfs: Etf[];
}
