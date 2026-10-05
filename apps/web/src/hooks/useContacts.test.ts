import { test } from "node:test";
import assert from "node:assert/strict";
import { rowToContact } from "@/hooks/useContacts";
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
