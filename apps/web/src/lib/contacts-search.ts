// Client-side contact search predicate. Every field is optional/nullable on
// purpose: the API returns NULL name/email/company/role, and calling
// .toLowerCase() on one crashed the contacts page on the first keystroke.
// Add new searchable fields (city, state, …) to SEARCH_FIELDS.

export type SearchableContact = {
  name?: string | null;
  email?: string | null;
  company?: string | null;
  role?: string | null;
};

const SEARCH_FIELDS = ["name", "company", "email", "role"] as const;

export function matchesContactSearch(contact: SearchableContact, query: string): boolean {
  const q = (query ?? "").trim().toLowerCase();
  if (!q) return true;
  return SEARCH_FIELDS.some((field) => (contact[field] ?? "").toLowerCase().includes(q));
}
