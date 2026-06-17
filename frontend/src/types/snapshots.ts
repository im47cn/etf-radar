import { z } from 'zod';
import { ThemeSchema, type Theme } from './themes';

export const SnapshotEntrySchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  themes_path: z.string(),
});
export type SnapshotEntry = z.infer<typeof SnapshotEntrySchema>;

export const SnapshotsIndexSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  snapshots: z.array(SnapshotEntrySchema).min(1),
});
export type SnapshotsIndex = z.infer<typeof SnapshotsIndexSchema>;

export const SnapshotThemesFileSchema = z.object({
  schema_version: z.string(),
  generated_at: z.string(),
  themes: z.array(ThemeSchema),
});
export type SnapshotThemesFile = z.infer<typeof SnapshotThemesFileSchema>;

export interface SnapshotFrame {
  date: string;
  themes: Theme[];
}
