import { describe, it, expect } from 'vitest';
import { LATEST_URLS, frameUrl } from '@/lib/dataUrls';

// URL 契约测试 — 防止 publicDir 平铺结构与 fetch URL 前缀错配再次溜过 MSW 通配匹配.
// 背景: vite.config.ts publicDir 把 ../data 内容平铺到 dist 根 (dist/latest/, dist/snapshots/),
// 而非 dist/data/latest/. 若 URL 误加 data/ 前缀, 生产会 404, 但 MSW 通配仍命中,
// 单测全绿. 此契约测试直接断言常量值, 杜绝该错配.

describe('data URL contract', () => {
  describe('LATEST_URLS — Phase A 的 4 个常驻数据文件 + snapshots 索引', () => {
    it('每个 URL 必须以 /latest/<file>.json 结尾, 不能含 data/ 前缀', () => {
      const cases: Array<[keyof typeof LATEST_URLS, RegExp]> = [
        ['themes', /\/latest\/themes\.json$/],
        ['etfs', /\/latest\/etfs\.json$/],
        ['signals', /\/latest\/signals\.json$/],
        ['meta', /\/latest\/meta\.json$/],
        ['snapshotsIndex', /\/latest\/snapshots-index\.json$/],
      ];
      for (const [key, suffix] of cases) {
        const url = LATEST_URLS[key];
        expect(url, `LATEST_URLS.${key}`).toMatch(suffix);
        expect(url, `LATEST_URLS.${key}`).not.toContain('/data/');
      }
    });
  });

  describe('frameUrl — Phase B 历史快照帧', () => {
    it('直接将 themes_path 拼到 BASE_URL 后 (themes_path 已含 snapshots/ 前缀)', () => {
      const url = frameUrl('snapshots/2026-06-15/themes.json');
      expect(url).toMatch(/\/snapshots\/2026-06-15\/themes\.json$/);
      expect(url).not.toContain('/data/');
      expect(url).not.toContain('/snapshots/snapshots/');
    });

    it('不应产生连续双斜杠', () => {
      expect(frameUrl('snapshots/x/themes.json')).not.toMatch(/\/\/snapshots/);
    });
  });
});
