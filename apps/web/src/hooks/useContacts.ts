"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import type { Contact } from "@/lib/types";
import type { ContactRow } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-mode";
import { demoContacts } from "@/lib/demo-data";
import { matchesContactSearch } from "@/lib/contacts-search";
import { patchById, removeById } from "@/lib/contacts-mutations";

// Matches the Contact model's server-side default (apps/api/app/models/contact.py).
const DEFAULT_ML_SCORE: Contact["mlScore"] = { value: 50, label: "warm", trend: "stable", signals: [] };

// Map DB snake_case row → frontend camelCase Contact type.
// The API returns NULL name/email/company/role; normalize them to "" here so
// display and search code never call string methods on null.
export function rowToContact(row: ContactRow): Contact {
  const name = row.name ?? "";
  const initials = name.split(" ").filter(Boolean).map((n) => n[0]).join("").slice(0, 2).toUpperCase();
  return {
    id: row.id,
    name,
    email: row.email ?? "",
    company: row.company ?? "",
    role: row.role ?? "",
    avatar: row.avatar || initials || "?",
    status: row.status,
    mlScore: { ...DEFAULT_ML_SCORE, ...(row.ml_score ?? {}) },
    semanticTags: row.semantic_tags ?? [],
    lastActivity: row.last_activity,
    deals: row.deal_count,
    revenue: row.revenue,
    createdAt: row.created_at,
  };
}

function filterDemoContacts(contacts: Contact[], options: UseContactsOptions): Contact[] {
  let filtered = [...contacts];
  if (options.status && options.status !== "all") {
    filtered = filtered.filter((c) => c.status === options.status);
  }
  if (options.search) {
    const q = options.search;
    filtered = filtered.filter((c) => matchesContactSearch(c, q));
  }
  if (options.score && options.score !== "all") {
    filtered = filtered.filter((c) => c.mlScore.label === options.score);
  }
  return filtered;
}

interface UseContactsOptions {
  status?: string;
  search?: string;
  score?: string;
}

export function useContacts(options: UseContactsOptions = {}) {
  const [contacts, setContacts] = useState<Contact[]>(
    isDemoMode ? filterDemoContacts(demoContacts, options) : []
  );
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const fetchContacts = useCallback(async () => {
    if (isDemoMode) {
      setContacts(filterDemoContacts(demoContacts, options));
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const supabase = createBrowserClient();
      const { data: { session } } = await supabase.auth.getSession();
      const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
      const token = session?.access_token;
      if (!workspaceId || !token) {
        setError("Not authenticated");
        return;
      }

      let rows = (await apiClient.listContacts(workspaceId, token, {
        status: options.status,
        q: options.search,
      })) as ContactRow[];

      // Client-side score filter (ml_score is JSONB)
      if (options.score && options.score !== "all") {
        rows = rows.filter((r) => r.ml_score?.label === options.score);
      }

      setContacts(rows.map(rowToContact));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load contacts");
    } finally {
      setLoading(false);
    }
  }, [options.status, options.search, options.score]);

  useEffect(() => {
    if (isDemoMode) {
      setContacts(filterDemoContacts(demoContacts, options));
      return;
    }
    fetchContacts();
  }, [fetchContacts]);

  const createContact = async (payload: Partial<Contact>) => {
    if (isDemoMode) return {};
    const supabase = createBrowserClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
    if (!workspaceId || !token) throw new Error("Not authenticated");

    await apiClient.createContact(workspaceId, {
      name: payload.name ?? "",
      email: payload.email ?? undefined,
      company: payload.company ?? undefined,
      role: payload.role ?? undefined,
      status: payload.status ?? "lead",
    }, token);
    await fetchContacts();
    return {};
  };

  const updateContact = async (id: string, payload: Partial<Contact>) => {
    if (isDemoMode) return {};
    const supabase = createBrowserClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
    if (!workspaceId || !token) throw new Error("Not authenticated");

    const result = await apiClient.updateContact(workspaceId, id, {
      name: payload.name,
      email: payload.email ?? undefined,
      company: payload.company ?? undefined,
      role: payload.role ?? undefined,
      status: payload.status,
    }, token);
    await fetchContacts();
    return result;
  };

  const deleteContact = async (id: string) => {
    if (isDemoMode) return;
    const supabase = createBrowserClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
    if (!workspaceId || !token) throw new Error("Not authenticated");

    await apiClient.deleteContact(workspaceId, id, token);
    await fetchContacts();
  };

  // Local, optimistic list updates. Callers that also want server truth call
  // refetch() afterwards — except in demo mode, where fetchContacts reloads the
  // static demo data and would undo the change.
  const patchContacts = useCallback((ids: Iterable<string>, patch: Partial<Contact>) => {
    setContacts((prev) => patchById(prev, ids, patch));
  }, []);

  const removeContacts = useCallback((ids: Iterable<string>) => {
    setContacts((prev) => removeById(prev, ids));
  }, []);

  return {
    contacts, loading, error, refetch: fetchContacts,
    createContact, updateContact, deleteContact, patchContacts, removeContacts,
  };
}
