import { useMemo } from 'react';
import useSWR from 'swr';
import { z } from 'zod';
import type { Snapshot, ThemeSnapshotEntry } from '@/lib/portfolio/eventTypes';
import type { SignalKind } from '@/lib/portfolio/types';
import { computeQuadrant } from '@/lib/portfolio/rules';
import { SnapshotThemesFileSchema } from '@/types/snapshots';

// signals.json 校验（与 backend 输出对齐）
const SignalsFileSchema = z.object({
  theme_signals: z.array(z.object({
    theme_id: z.string(),
    signal:   z.enum(['resonance', 'transmission', 'divergence']).nullable(),
  }).passthrough()),
}).passthrough();

export interface UseEventsSnapshotResult {
  snapshot: Snapshot | undefined;
  error:    Error | undefined;
}

type FetcherKey = readonly [string, string];

const fetcher = async ([themesUrl, signalsUrl]: FetcherKey): Promise<{
  themesFile:  z.infer<typeof SnapshotThemesFileSchema>;
  signalsFile: z.infer<typeof SignalsFileSchema>;
}> => {
  const [tRes, sRes] = await Promise.all([fetch(themesUrl), fetch(signalsUrl)]);
  if (!tRes.ok) throw new Error(`themes ${tRes.status}`);
  if (!sRes.ok) throw new Error(`signals ${sRes.status}`);
  return {
    themesFile:  SnapshotThemesFileSchema.parse(await tRes.json()),
    signalsFile: SignalsFileSchema.parse(await sRes.json()),
  };
};

/**
 * 单日完整快照拉取（themes + signals）+ 组装为 detectEvents 友好的 Snapshot。
 *
 * 不复用 useSnapshotsTimeline 的原因：
 *   - timeline 仅拉 themes，无 signals
 *   - Phase 3 仅在 portfolio 页用，独立 hook 解耦
 */
export function useEventsSnapshot(date: string | undefined): UseEventsSnapshotResult {
  const key: FetcherKey | null = date
    ? [`/data/snapshots/${date}/themes.json`, `/data/snapshots/${date}/signals.json`]
    : null;

  const { data, error } = useSWR(key, fetcher, {
    revalidateOnFocus:  false,
    errorRetryInterval: 5000,
  });

  // useMemo 避免每次 render 重建 Map（SWR data 引用在缓存命中时稳定）
  const snapshot = useMemo<Snapshot | undefined>(() => {
    if (!date || !data) return undefined;

    const sigByTheme = new Map<string, SignalKind | null>(
      data.signalsFile.theme_signals.map(s => [s.theme_id, s.signal ?? null]),
    );

    const themes = new Map<string, ThemeSnapshotEntry>();
    for (const t of data.themesFile.themes) {
      themes.set(t.id, {
        themeId:  t.id,
        strength: t.strength,
        quadrant: computeQuadrant(t.strength),
        signal:   sigByTheme.get(t.id) ?? null,
      });
    }

    return { date, themes };
  }, [date, data]);

  return {
    snapshot,
    error: error ? (error as Error) : undefined,
  };
}
