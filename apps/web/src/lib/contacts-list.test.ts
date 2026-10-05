import { test } from "node:test";
import assert from "node:assert/strict";
import { CONTACTS_PAGE_LIMIT, summarizeContactCounts, formatCount } from "@/lib/contacts-list";

const loaded = [
  { status: "lead" },
  { status: "lead" },
  { status: "prospect" },
  { status: "customer" },
];
const server = { total: 1240, by_status: { lead: 900, prospect: 300, customer: 40 } };

test("page limit is the API's max (limit le=500), not the old default of 100", () => {
  assert.equal(CONTACTS_PAGE_LIMIT, 500);
});

test("a complete list counts the loaded rows, so optimistic edits show at once", () => {
  const c = summarizeContactCounts({ contacts: loaded, server, complete: true });
  assert.deepEqual(c, { total: 4, byStatus: { lead: 2, prospect: 1, customer: 1 }, lowerBound: false });
});

test("a capped or server-searched list uses the workspace counts", () => {
  const c = summarizeContactCounts({ contacts: loaded, server, complete: false });
  assert.deepEqual(c, { total: 1240, byStatus: { lead: 900, prospect: 300, customer: 40 }, lowerBound: false });
});

test("without workspace counts, a capped list reports a lower bound", () => {
  const c = summarizeContactCounts({ contacts: loaded, server: null, complete: false });
  assert.equal(c.total, 4);
  assert.equal(c.lowerBound, true);
  assert.equal(formatCount(c.total, c.lowerBound), "4+");
  assert.equal(formatCount(12, false), "12");
});
