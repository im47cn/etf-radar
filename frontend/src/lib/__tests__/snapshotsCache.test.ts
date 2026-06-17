import { describe, it, expect } from 'vitest';
import { createLRU } from '../snapshotsCache';

describe('createLRU', () => {
  it('evicts oldest when over capacity', () => {
    const lru = createLRU<string>(3);
    (['a', 'b', 'c', 'd'] as const).forEach(k => lru.put(k, k.toUpperCase()));
    expect(lru.has('a')).toBe(false);
    expect(lru.has('b')).toBe(true);
    expect(lru.has('d')).toBe(true);
    expect(lru.size()).toBe(3);
  });

  it('get refreshes recency (a stays after d evicts oldest)', () => {
    const lru = createLRU<string>(3);
    (['a', 'b', 'c'] as const).forEach(k => lru.put(k, k));
    expect(lru.get('a')).toBe('a');
    lru.put('d', 'd');
    expect(lru.has('a')).toBe(true);
    expect(lru.has('b')).toBe(false);
  });

  it('put on existing key updates value and refreshes', () => {
    const lru = createLRU<string>(2);
    lru.put('a', '1');
    lru.put('b', '2');
    lru.put('a', '11');
    lru.put('c', '3');
    expect(lru.get('a')).toBe('11');
    expect(lru.has('b')).toBe(false);
    expect(lru.has('c')).toBe(true);
  });
});
