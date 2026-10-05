// Loading and counting the contacts list. GET /contacts is capped (limit
// <= 500, newest first), so once a workspace outgrows one page the loaded rows
// are no longer the whole workspace and their count is not the total.

/** Rows requested per load: the API's maximum. */
export const CONTACTS_PAGE_LIMIT = 500;

export type ServerContactCounts = { total: number; by_status: Record<string, number> };
export type ContactCounts = { total: number; byStatus: Record<string, number>; lowerBound: boolean };

/**
 * Totals for the header, stat cards and footer.
 * - `complete` (every workspace contact is loaded): count the loaded rows, so
 *   optimistic status changes and deletes show immediately.
 * - otherwise (list capped, or narrowed by a server-side search): use the
 *   workspace counts; without them, the loaded rows are only a lower bound.
 */
export function summarizeContactCounts({ contacts, server, complete }: {
  contacts: ReadonlyArray<{ status: string }>;
  server: ServerContactCounts | null;
  complete: boolean;
}): ContactCounts {
  if (!complete && server) {
    return { total: server.total, byStatus: { ...server.by_status }, lowerBound: false };
  }
  const byStatus: Record<string, number> = {};
  for (const c of contacts) byStatus[c.status] = (byStatus[c.status] ?? 0) + 1;
  return { total: contacts.length, byStatus, lowerBound: !complete };
}

export function formatCount(n: number, lowerBound: boolean): string {
  return lowerBound ? `${n}+` : String(n);
}
