// pdf.js calls Map.getOrInsertComputed, which browsers released before 2026 do not have.
// Without this the viewer stays empty there.

type Upsert = {
  getOrInsert?: (key: unknown, value: unknown) => unknown;
  getOrInsertComputed?: (key: unknown, compute: (key: unknown) => unknown) => unknown;
};

for (const { prototype } of [Map, WeakMap]) {
  const target = prototype as (Map<unknown, unknown> | WeakMap<WeakKey, unknown>) & Upsert;
  if (!target.getOrInsert) {
    Object.defineProperty(target, "getOrInsert", {
      configurable: true,
      writable: true,
      value(this: Map<unknown, unknown>, key: unknown, value: unknown) {
        if (!this.has(key)) this.set(key, value);
        return this.get(key);
      },
    });
  }
  if (!target.getOrInsertComputed) {
    Object.defineProperty(target, "getOrInsertComputed", {
      configurable: true,
      writable: true,
      value(this: Map<unknown, unknown>, key: unknown, compute: (key: unknown) => unknown) {
        if (!this.has(key)) this.set(key, compute(key));
        return this.get(key);
      },
    });
  }
}

export {};
