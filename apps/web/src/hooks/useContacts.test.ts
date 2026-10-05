import { test } from "node:test";
import assert from "node:assert/strict";
import { rowToContact, fetchContactById } from "@/hooks/useContacts";
import { apiClient } from "@/lib/api-client";
import type { ContactRow } from "@/lib/supabase";

function row(overrides: Partial<ContactRow> = {}): ContactRow {
  return {
    id: "c1",
    workspace_id: "ws1",
    name: "Wanda Wells",
    email: "wanda@acme.com",
    company: "Acme",
    role: "VP Ops",
    avatar: null,
    status: "lead",
    ml_score: { value: 72, label: "hot", trend: "up", signals: ["opened"] },
    semantic_tags: [],
    last_activity: "Never",
    revenue: 0,
    deal_count: 0,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...overrides,
  };
}

test("derives initials when avatar is null", () => {
  assert.equal(rowToContact(row()).avatar, "WW");
});

test("keeps an explicit avatar", () => {
  assert.equal(rowToContact(row({ avatar: "ZZ" })).avatar, "ZZ");
});

test("null name does not throw and renders a '?' avatar", () => {
  // Ingest auto-create and CSV import can store name = NULL. A throw here
  // made fetchContacts fall into its catch and blank the whole list.
  const c = rowToContact(row({ name: null }));
  assert.equal(c.name, "");
  assert.equal(c.avatar, "?");
});

test("collapses repeated spaces when building initials", () => {
  assert.equal(rowToContact(row({ name: "  Dana   Reyes " })).avatar, "DR");
});

test("null email, company and role become empty strings", () => {
  const c = rowToContact(row({ email: null, company: null, role: null }));
  assert.equal(c.email, "");
  assert.equal(c.company, "");
  assert.equal(c.role, "");
});

test("defaults a missing ml_score and semantic_tags", () => {
  const c = rowToContact(row({ ml_score: null, semantic_tags: null }));
  assert.deepEqual(c.mlScore, { value: 50, label: "warm", trend: "stable", signals: [] });
  assert.deepEqual(c.semanticTags, []);
});

test("passes a real ml_score through", () => {
  assert.deepEqual(rowToContact(row()).mlScore, { value: 72, label: "hot", trend: "up", signals: ["opened"] });
});

// The detail page used to scan listContacts() (capped at 100, unordered) and
// treat the raw snake_case row as a camelCase Contact, so any contact past the
// cap showed "not found" and mlScore/semanticTags were undefined.
test("fetchContactById loads one contact by id and maps it to a Contact", async (t) => {
  const getContact = t.mock.method(apiClient, "getContact", async () => row({ id: "c-741", name: "Dana Reyes", email: null }));
  const listContacts = t.mock.method(apiClient, "listContacts", async () => []);

  const c = await fetchContactById("ws1", "c-741", "tok");

  assert.equal(getContact.mock.callCount(), 1);
  assert.deepEqual(getContact.mock.calls[0].arguments, ["ws1", "c-741", "tok"]);
  assert.equal(listContacts.mock.callCount(), 0);
  assert.equal(c?.id, "c-741");
  assert.equal(c?.email, "");
  assert.equal(c?.mlScore.label, "hot");
  assert.deepEqual(c?.semanticTags, []);
});

test("fetchContactById returns null when the API has no such contact", async (t) => {
  t.mock.method(apiClient, "getContact", async () => null);
  assert.equal(await fetchContactById("ws1", "missing", "tok"), null);
});
