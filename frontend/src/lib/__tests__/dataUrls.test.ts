import { describe, it, expect } from 'vitest';
import { LATEST_URLS, HOLDINGS_URLS, STOCKS_URLS, frameUrl, holdingsEtfUrl, stockOhlcUrl } from '../dataUrls';

describe('dataUrls', () => {
  describe('LATEST_URLS', () => {
    it('所有 URL 以 BASE_URL 前缀开头', () => {
      // 默认 BASE_URL = '/'
      expect(LATEST_URLS.themes).toBe('/latest/themes.json');
      expect(LATEST_URLS.etfs).toBe('/latest/etfs.json');
      expect(LATEST_URLS.signals).toBe('/latest/signals.json');
      expect(LATEST_URLS.meta).toBe('/latest/meta.json');
      expect(LATEST_URLS.snapshotsIndex).toBe('/latest/snapshots-index.json');
      expect(LATEST_URLS.stocksSpot).toBe('/latest/stocks_spot.json');
      expect(LATEST_URLS.marketTemperature).toBe('/latest/market_temperature.json');
      expect(LATEST_URLS.indexSeries).toBe('/latest/index_series.json');
      expect(LATEST_URLS.signalEvidence).toBe('/latest/signal_evidence.json');
    });
  });

  describe('frameUrl', () => {
    it('拼接 themesPath 到 BASE', () => {
      expect(frameUrl('snapshots/2026-01-01/themes.json')).toBe(
        '/snapshots/2026-01-01/themes.json',
      );
    });
  });

  describe('HOLDINGS_URLS', () => {
    it('index URL 拼接正确', () => {
      expect(HOLDINGS_URLS.index).toBe('/holdings/index.json');
    });
  });

  describe('holdingsEtfUrl', () => {
    it('按 etfCode 拼接', () => {
      expect(holdingsEtfUrl('159870')).toBe('/holdings/159870.json');
    });
  });

  describe('STOCKS_URLS', () => {
    it('holdingsIndicators URL', () => {
      expect(STOCKS_URLS.holdingsIndicators).toBe('/stocks/holdings_indicators.json');
    });
    it('index URL', () => {
      expect(STOCKS_URLS.index).toBe('/stocks/index.json');
    });
  });

  describe('stockOhlcUrl', () => {
    it('按 stockCode 拼接', () => {
      expect(stockOhlcUrl('600519')).toBe('/stocks/ohlc/600519.json');
    });
  });
});
