export type ProviderStatus = 'ok' | 'degraded' | 'stale';

export interface ProviderInfo {
  status: ProviderStatus;
  name: string;
}

export interface MetaFile {
  schema_version: string;
  last_full_refresh: { us: string | null; cn: string | null };
  last_intraday_refresh: string | null;
  providers: { us: ProviderInfo; cn: ProviderInfo };
  failed_symbols: string[];
  stale_minutes: number;
  calendar: {
    us_trading_today: boolean;
    cn_trading_today: boolean;
    us_session_active: boolean;
    cn_session_active: boolean;
  };
}
