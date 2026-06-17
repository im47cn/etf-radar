export interface LRU<V> {
  get(key: string): V | undefined;
  put(key: string, value: V): void;
  has(key: string): boolean;
  size(): number;
}

export function createLRU<V>(max: number): LRU<V> {
  if (max < 1) throw new Error('LRU max must be >= 1');
  const store = new Map<string, V>();

  const refresh = (key: string, value: V): void => {
    if (store.has(key)) store.delete(key);
    store.set(key, value);
    while (store.size > max) {
      const oldest = store.keys().next().value as string | undefined;
      if (oldest !== undefined) store.delete(oldest);
    }
  };

  return {
    get(key) {
      const v = store.get(key);
      if (v !== undefined) refresh(key, v);
      return v;
    },
    put(key, value) { refresh(key, value); },
    has(key) { return store.has(key); },
    size() { return store.size; },
  };
}
