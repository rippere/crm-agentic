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

/**
 * Apply `value` to `ids` optimistically, send one request per id, and put back
 * the `prior` value for each id whose request rejected. Returns the failed ids.
 */
export async function updateEachWithRollback<V>({ ids, value, prior, apply, request }: {
  ids: string[];
  value: V;
  prior: Map<string, V>;
  apply: (ids: string[], value: V) => void;
  request: (id: string) => Promise<unknown>;
}): Promise<string[]> {
  apply(ids, value);
  const results = await Promise.allSettled(ids.map((id) => request(id)));
  const failed = rejectedIds(ids, results);
  for (const id of failed) {
    const was = prior.get(id);
    if (was !== undefined) apply([id], was);
  }
  return failed;
}

/**
 * Orders overlapping list loads so a slow, older response can't overwrite a
 * newer one. Each load calls begin() and checks its ticket before applying:
 * - isLatest(): no newer load has started since (it still owns `loading`);
 * - canApply(): isLatest(), and no local write (optimistic patch or remove)
 *   happened after the load started, so its rows aren't older than the screen.
 */
export class LatestRequestGate {
  private latest = 0;
  private writes = 0;

  begin(): { isLatest: () => boolean; canApply: () => boolean } {
    const id = ++this.latest;
    const writesAtStart = this.writes;
    const isLatest = () => id === this.latest;
    return { isLatest, canApply: () => isLatest() && writesAtStart === this.writes };
  }

  noteLocalWrite(): void {
    this.writes += 1;
  }
}

/** Outcome of firing one enrich request per contact (POST …/enrich answers 202 with a job_id). */
export function summarizeEnrichResults(ids: string[], results: PromiseSettledResult<unknown>[]): {
  jobIds: string[];
  failed: string[];
  rateLimited: number;
} {
  const jobIds: string[] = [];
  let rateLimited = 0;
  results.forEach((r) => {
    if (r.status === "fulfilled") {
      const jobId = (r.value as { job_id?: unknown } | null)?.job_id;
      if (typeof jobId === "string" && jobId) jobIds.push(jobId);
    } else if ((r.reason as { status?: unknown } | null)?.status === 429) {
      rateLimited += 1;
    }
  });
  return { jobIds, failed: rejectedIds(ids, results), rateLimited };
}

const TERMINAL_JOB_STATES = new Set(["success", "failure", "unknown", "revoked"]);

/**
 * Poll each job until every one reaches a terminal state, `maxPolls` rounds
 * pass, or `cancelled()` returns true. A failed poll counts as still pending.
 */
export async function waitForJobs(
  jobIds: string[],
  getState: (jobId: string) => Promise<string>,
  {
    intervalMs = 2000,
    maxPolls = 60,
    sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
    cancelled = () => false,
  }: {
    intervalMs?: number;
    maxPolls?: number;
    sleep?: (ms: number) => Promise<void>;
    cancelled?: () => boolean;
  } = {},
): Promise<void> {
  let pending = [...jobIds];
  for (let poll = 0; poll < maxPolls && pending.length > 0; poll++) {
    await sleep(intervalMs);
    if (cancelled()) return;
    const states = await Promise.all(
      pending.map((id) => getState(id).then((s) => s.toLowerCase(), () => "pending")),
    );
    pending = pending.filter((_, i) => !TERMINAL_JOB_STATES.has(states[i]));
  }
}
