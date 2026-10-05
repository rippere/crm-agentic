import { test } from "node:test";
import assert from "node:assert/strict";
import {
  patchById,
  removeById,
  rejectedIds,
  updateEachWithRollback,
  LatestRequestGate,
  summarizeEnrichResults,
  waitForJobs,
} from "@/lib/contacts-mutations";

const rows = [
  { id: "a", status: "lead" },
  { id: "b", status: "prospect" },
  { id: "c", status: "lead" },
];

test("patchById updates only the listed ids and leaves the input untouched", () => {
  const out = patchById(rows, ["a", "c"], { status: "customer" });
  assert.deepEqual(out.map((r) => r.status), ["customer", "prospect", "customer"]);
  assert.equal(rows[0].status, "lead");
  assert.equal(out[1], rows[1]);
});

test("patchById ignores unknown ids and returns the same array for no ids", () => {
  assert.deepEqual(patchById(rows, ["zzz"], { status: "customer" }), rows);
  assert.equal(patchById(rows, [], { status: "customer" }), rows);
});

test("removeById drops the listed ids and accepts a Set", () => {
  assert.deepEqual(removeById(rows, new Set(["b"])).map((r) => r.id), ["a", "c"]);
  assert.equal(removeById(rows, []), rows);
});

test("rejectedIds pairs allSettled results with ids by position", async () => {
  const ids = ["a", "b", "c"];
  const results = await Promise.allSettled([
    Promise.resolve(1),
    Promise.reject(new Error("409")),
    Promise.resolve(3),
  ]);
  assert.deepEqual(rejectedIds(ids, results), ["b"]);
});

// ── Bulk status rollback ──────────────────────────────────────────────────

test("updateEachWithRollback applies optimistically and restores only the failed ids", async () => {
  let list = rows;
  const seenDuringRequest: string[][] = [];
  const failed = await updateEachWithRollback({
    ids: ["a", "b"],
    value: "customer",
    prior: new Map(rows.map((r) => [r.id, r.status])),
    apply: (ids, status) => { list = patchById(list, ids, { status }); },
    request: async (id) => {
      seenDuringRequest.push(list.map((r) => r.status));
      if (id === "b") throw Object.assign(new Error("API error 500"), { status: 500 });
    },
  });
  assert.deepEqual(failed, ["b"]);
  // Both rows showed the new status while the requests were in flight.
  assert.deepEqual(seenDuringRequest[0], ["customer", "customer", "lead"]);
  // Only the failed row went back.
  assert.deepEqual(list.map((r) => r.status), ["customer", "prospect", "lead"]);
});

test("updateEachWithRollback leaves the optimistic value when every request succeeds", async () => {
  let list = rows;
  const failed = await updateEachWithRollback({
    ids: ["a", "c"],
    value: "churned",
    prior: new Map(rows.map((r) => [r.id, r.status])),
    apply: (ids, status) => { list = patchById(list, ids, { status }); },
    request: async () => ({}),
  });
  assert.deepEqual(failed, []);
  assert.deepEqual(list.map((r) => r.status), ["churned", "prospect", "churned"]);
});

// ── Overlapping refetches ─────────────────────────────────────────────────

/** A promise plus the function that resolves it, to finish requests out of order. */
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

/** Mirrors useContacts.fetchContacts: apply the response only if the ticket allows it. */
async function load(gate: LatestRequestGate, response: Promise<string[]>, screen: { rows: string[] }) {
  const ticket = gate.begin();
  const rowsFromApi = await response;
  if (ticket.canApply()) screen.rows = rowsFromApi;
}

test("a slow earlier refetch that finishes last does not overwrite a newer one", async () => {
  // Status change → refetch A (slow); a second status change → refetch B (fast).
  const gate = new LatestRequestGate();
  const screen = { rows: ["jason:lead"] };
  const a = deferred<string[]>();
  const b = deferred<string[]>();
  const loadA = load(gate, a.promise, screen);
  const loadB = load(gate, b.promise, screen);
  b.resolve(["jason:prospect"]);
  await loadB;
  a.resolve(["jason:customer"]);
  await loadA;
  assert.deepEqual(screen.rows, ["jason:prospect"]);
});

test("a deleted contact does not come back from a refetch that started before the delete", async () => {
  const gate = new LatestRequestGate();
  const screen = { rows: ["jason", "priya"] };
  const a = deferred<string[]>();
  const loadA = load(gate, a.promise, screen); // refetch after a status change
  gate.noteLocalWrite(); // delete succeeds: removeContacts(["jason"])
  screen.rows = screen.rows.filter((r) => r !== "jason");
  const b = deferred<string[]>();
  const loadB = load(gate, b.promise, screen); // refetch after the delete
  b.resolve(["priya"]);
  await loadB;
  a.resolve(["jason", "priya"]); // the older response lands last
  await loadA;
  assert.deepEqual(screen.rows, ["priya"]);
});

test("a local write while the only refetch is in flight keeps the local state", async () => {
  const gate = new LatestRequestGate();
  const ticket = gate.begin();
  assert.equal(ticket.canApply(), true);
  gate.noteLocalWrite(); // optimistic status patch
  assert.equal(ticket.canApply(), false);
  // It is still the newest load, so it still owns (and clears) the spinner.
  assert.equal(ticket.isLatest(), true);
  assert.equal(gate.begin().canApply(), true);
  assert.equal(ticket.isLatest(), false);
});

// ── Bulk enrich ───────────────────────────────────────────────────────────

test("summarizeEnrichResults collects job ids, failed ids and rate-limited rejections", async () => {
  const results = await Promise.allSettled([
    Promise.resolve({ status: "queued", job_id: "job-1" }),
    Promise.reject(Object.assign(new Error("API error 429"), { status: 429 })),
    Promise.reject(Object.assign(new Error("API error 404"), { status: 404 })),
    Promise.resolve({ status: "queued", fields_updated: [] }), // demo mode: no job id
  ]);
  assert.deepEqual(summarizeEnrichResults(["a", "b", "c", "d"], results), {
    jobIds: ["job-1"],
    failed: ["b", "c"],
    rateLimited: 1,
  });
});

test("waitForJobs polls until every job is terminal, treating poll errors as pending", async () => {
  const states: Record<string, string[]> = {
    j1: ["PENDING", "STARTED", "SUCCESS"],
    j2: ["boom", "FAILURE"],
  };
  const polled: string[] = [];
  await waitForJobs(["j1", "j2"], async (id) => {
    polled.push(id);
    const s = states[id].shift()!;
    if (s === "boom") throw new Error("network");
    return s;
  }, { sleep: async () => {} });
  assert.deepEqual(polled, ["j1", "j2", "j1", "j2", "j1"]);
});

test("waitForJobs gives up after maxPolls and stops when cancelled", async () => {
  let polls = 0;
  await waitForJobs(["j1"], async () => { polls++; return "PENDING"; }, { sleep: async () => {}, maxPolls: 3 });
  assert.equal(polls, 3);

  polls = 0;
  let cancelled = false;
  await waitForJobs(["j1"], async () => { polls++; cancelled = true; return "PENDING"; }, {
    sleep: async () => {},
    cancelled: () => cancelled,
  });
  assert.equal(polls, 1);
});
