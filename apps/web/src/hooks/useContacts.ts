"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
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

    try {
      const supabase = createBrowserClient();
      const { data: { user } } = await supabase.auth.getUser();
      const workspaceId = user?.user_metadata?.workspace_id as string | undefined;
      if (!workspaceId) {
        setError("No workspace found");
        return;
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let query: any = supabase
        .from("contacts")
        .select("*")
        .eq("workspace_id", workspaceId)
        .order("created_at", { ascending: false });

      if (options.status && options.status !== "all") {
        query = query.eq("status", options.status);
      }
      if (options.search) {
        query = query.or(
          `name.ilike.%${options.search}%,email.ilike.%${options.search}%,company.ilike.%${options.search}%`
        );
      }

      const { data, error: fetchError } = await query;
      if (fetchError) throw new Error(fetchError.message);

      let rows = (data ?? []) as ContactRow[];

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
    fetchContacts();
  }, [fetchContacts]);

  const createContact = async (payload: Partial<Contact>) => {
    const supabase = createBrowserClient();
    const { data: { user } } = await supabase.auth.getUser();
    const workspaceId = user?.user_metadata?.workspace_id as string;

    const { data, error: insertError } = await supabase
      .from("contacts")
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .insert({ ...payload, workspace_id: workspaceId } as any)
      .select()
      .single();

    if (insertError) throw new Error(insertError.message);
    await fetchContacts();
    return data;
  };

  const updateContact = async (id: string, payload: Partial<Contact>) => {
    const supabase = createBrowserClient();
    const { data, error: updateError } = await supabase
      .from("contacts")
      .update(payload as Partial<ContactRow>)
      .eq("id", id)
      .select()
      .single();

    if (updateError) throw new Error(updateError.message);
    await fetchContacts();
    return data;
  };

  const deleteContact = async (id: string) => {
    const supabase = createBrowserClient();
    const { error: deleteError } = await supabase.from("contacts").delete().eq("id", id);
    if (deleteError) throw new Error(deleteError.message);
    await fetchContacts();
  };

  return { contacts, loading, error, refetch: fetchContacts, createContact, updateContact, deleteContact };
}
