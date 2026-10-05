// Pure list updates the contacts page applies locally after a mutation, so the
// table and stat cards change immediately instead of waiting for a reload.

type WithId = { id: string };

/** Return a copy of `items` with `patch` merged into every item whose id is in `ids`. */
export function patchById<T extends WithId>(items: T[], ids: Iterable<string>, patch: Partial<T>): T[] {
  const idSet = new Set(ids);
  if (idSet.size === 0) return items;
  return items.map((item) => (idSet.has(item.id) ? { ...item, ...patch } : item));
}

/** Return a copy of `items` without the items whose id is in `ids`. */
export function removeById<T extends WithId>(items: T[], ids: Iterable<string>): T[] {
  const idSet = new Set(ids);
  if (idSet.size === 0) return items;
  return items.filter((item) => !idSet.has(item.id));
}

/** The ids whose request rejected, given `results` from Promise.allSettled in the same order as `ids`. */
export function rejectedIds(ids: string[], results: PromiseSettledResult<unknown>[]): string[] {
  return ids.filter((_, i) => results[i]?.status === "rejected");
}
