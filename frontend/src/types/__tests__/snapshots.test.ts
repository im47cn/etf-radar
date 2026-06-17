import { describe, it, expect } from 'vitest';
import { SnapshotsIndexSchema, SnapshotEntrySchema } from '../snapshots';

describe('SnapshotEntrySchema', () => {
  it('accepts valid entry', () => {
    expect(() => SnapshotEntrySchema.parse({
      date: '2026-06-15',
      themes_path: 'snapshots/2026-06-15/themes.json',
    })).not.toThrow();
  });

  it('rejects invalid date format', () => {
    expect(() => SnapshotEntrySchema.parse({
      date: '2026/06/15',
      themes_path: 'x',
    })).toThrow();
  });
});

describe('SnapshotsIndexSchema', () => {
  it('rejects empty snapshots array', () => {
    expect(() => SnapshotsIndexSchema.parse({
      schema_version: '1.0',
      generated_at: '2026-06-15T00:00:00+08:00',
      snapshots: [],
    })).toThrow();
  });

  it('accepts well-formed index', () => {
    const parsed = SnapshotsIndexSchema.parse({
      schema_version: '1.0',
      generated_at: '2026-06-15T00:00:00+08:00',
      snapshots: [{ date: '2026-06-15', themes_path: 'snapshots/2026-06-15/themes.json' }],
    });
    expect(parsed.snapshots).toHaveLength(1);
  });
});
