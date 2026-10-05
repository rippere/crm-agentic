import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { apiClient } from "@/lib/api-client";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

function captureFetch(body: unknown): string[] {
  const urls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    urls.push(String(input));
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  return urls;
}

test("listContacts sends limit, offset and a trimmed q", async () => {
  const urls = captureFetch([]);
  await apiClient.listContacts("ws1", "tok", { q: "  reyes ", limit: 500, offset: 0, status: "all" });
  const url = new URL(urls[0]);
  assert.equal(url.pathname, "/workspaces/ws1/contacts");
  assert.equal(url.searchParams.get("limit"), "500");
  assert.equal(url.searchParams.get("q"), "reyes");
  assert.equal(url.searchParams.has("status"), false);
});

test("listContacts omits a blank q", async () => {
  const urls = captureFetch([]);
  await apiClient.listContacts("ws1", "tok", { q: "   ", limit: 500 });
  assert.equal(new URL(urls[0]).searchParams.has("q"), false);
});

test("getContactCounts reads the counts endpoint", async () => {
  const urls = captureFetch({ total: 3, by_status: { lead: 3 } });
  const counts = await apiClient.getContactCounts("ws1", "tok");
  assert.equal(new URL(urls[0]).pathname, "/workspaces/ws1/contacts/counts");
  assert.deepEqual(counts, { total: 3, by_status: { lead: 3 } });
});
