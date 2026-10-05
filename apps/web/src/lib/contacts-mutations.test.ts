import { test } from "node:test";
import assert from "node:assert/strict";
import { patchById, removeById, rejectedIds } from "@/lib/contacts-mutations";

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

test("rolling back only failed ids restores their prior status", () => {
  const prior = new Map(rows.map((r) => [r.id, r.status]));
  let list = patchById(rows, ["a", "b"], { status: "customer" });
  for (const id of ["b"]) list = patchById(list, [id], { status: prior.get(id)! });
  assert.deepEqual(list.map((r) => r.status), ["customer", "prospect", "lead"]);
});
