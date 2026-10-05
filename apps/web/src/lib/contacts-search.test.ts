import { test } from "node:test";
import assert from "node:assert/strict";
import { matchesContactSearch } from "@/lib/contacts-search";

// Shapes the API really returns: name/email/company/role are all nullable
// (ContactResponse in apps/api/app/routers/contacts.py).
const dana = { name: "Dana Reyes", email: null, company: "Acme Events", role: "Owner" };
const walt = { name: "Walt Nocompany", email: "walt@x.com", company: null, role: null };
const inbound = { name: null, email: "unknown@inbound.com", company: null, role: null };

test("does not throw on null email, company, name or role", () => {
  for (const c of [dana, walt, inbound]) {
    assert.doesNotThrow(() => matchesContactSearch(c, "w"));
  }
});

test("empty or whitespace query matches everything", () => {
  for (const c of [dana, walt, inbound]) {
    assert.equal(matchesContactSearch(c, ""), true);
    assert.equal(matchesContactSearch(c, "   "), true);
  }
});

test("matches name, company, email and role case-insensitively", () => {
  assert.equal(matchesContactSearch(dana, "REYES"), true);
  assert.equal(matchesContactSearch(dana, "acme events"), true);
  assert.equal(matchesContactSearch(dana, "owner"), true);
  assert.equal(matchesContactSearch(walt, "WALT@X"), true);
  assert.equal(matchesContactSearch(inbound, "inbound.com"), true);
});

test("trims the query", () => {
  assert.equal(matchesContactSearch(walt, "  walt  "), true);
});

test("non-matching query filters the contact out", () => {
  for (const c of [dana, walt, inbound]) {
    assert.equal(matchesContactSearch(c, "zzz"), false);
  }
});
