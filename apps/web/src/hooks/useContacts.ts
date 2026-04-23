"use client";

import { useState, useEffect, useCallback } from "react";
import type { Contact } from "@/lib/types";
import type { ContactRow } from "@/lib/supabase";

// Map DB snake_case row → frontend camelCase Contact type
function rowToContact(row: ContactRow): Contact {
  return {
    id: row.id,
    name: row.name,
    email: row.email,
    company: row.company,
    role: row.role,
    avatar: row.avatar || row.name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase(),
    status: row.status,
    mlScore: row.ml_score,
    semanticTags: row.semantic_tags,
    lastActivity: row.last_activity,
    deals: row.deal_count,
    revenue: row.revenue,
    createdAt: row.created_at,
  };
}

interface UseContactsOptions {
  status?: string;
  search?: string;
  score?: string;
}

export function useContacts(options: UseContactsOptions = {}) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchContacts = useCallback(async () => {
    setLoading(true);
    setError(null);

    const params = new URLSearchParams();
    if (options.status && options.status !== "all") params.set("status", options.status);
    if (options.search) params.set("search", options.search);
    if (options.score && options.score !== "all") params.set("score", options.score);

    try {
      const res = await fetch(`/api/contacts?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ContactRow[] = await res.json();
      setContacts(data.map(rowToContact));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load contacts");
    } finally {
      setLoading(false);
    }
  }, [options.status, options.search, options.score]);

  useEffect(() => {
    fetchContacts();
  }, [fetchContacts]);

  const createContact = async (payload: Partial<Contact>) => {
    const res = await fetch("/api/contacts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    await fetchContacts();
    return res.json();
  };

  const updateContact = async (id: string, payload: Partial<Contact>) => {
    const res = await fetch(`/api/contacts/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    await fetchContacts();
    return res.json();
  };

  const deleteContact = async (id: string) => {
    const res = await fetch(`/api/contacts/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await res.text());
    await fetchContacts();
  };

  return { contacts, loading, error, refetch: fetchContacts, createContact, updateContact, deleteContact };
}
