"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import type { Deal } from "@/lib/types";
import type { DealRow } from "@/lib/supabase";

function rowToDeal(row: DealRow): Deal {
  return {
    id: row.id,
    title: row.title,
    company: row.company,
    contactName: row.contact_name,
    value: row.value,
    stage: row.stage,
    mlWinProbability: row.ml_win_probability,
    expectedClose: row.expected_close,
    assignedAgent: row.assigned_agent,
    notes: row.notes,
    createdAt: row.created_at,
  };
}

export function useDeals(stage?: string) {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDeals = useCallback(async () => {
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
        .from("deals")
        .select("*")
        .eq("workspace_id", workspaceId);

      if (stage && stage !== "all") {
        query = query.eq("stage", stage);
      }

      const { data, error: fetchError } = await query;
      if (fetchError) throw new Error(fetchError.message);

      setDeals((data ?? []).map((r: DealRow) => rowToDeal(r)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deals");
    } finally {
      setLoading(false);
    }
  }, [stage]);

  useEffect(() => {
    fetchDeals();
  }, [fetchDeals]);

  const createDeal = async (payload: Partial<Deal>) => {
    const supabase = createBrowserClient();
    const { data: { user } } = await supabase.auth.getUser();
    const workspaceId = user?.user_metadata?.workspace_id as string;

    const { data, error: insertError } = await supabase
      .from("deals")
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .insert({ ...payload, workspace_id: workspaceId } as any)
      .select()
      .single();

    if (insertError) throw new Error(insertError.message);
    await fetchDeals();
    return data;
  };

  const updateDeal = async (id: string, payload: Partial<Deal> & { stage?: Deal["stage"] }) => {
    const supabase = createBrowserClient();
    const { data, error: updateError } = await supabase
      .from("deals")
      .update(payload as Partial<DealRow>)
      .eq("id", id)
      .select()
      .single();

    if (updateError) throw new Error(updateError.message);
    await fetchDeals();
    return data;
  };

  const deleteDeal = async (id: string) => {
    const supabase = createBrowserClient();
    const { error: deleteError } = await supabase.from("deals").delete().eq("id", id);
    if (deleteError) throw new Error(deleteError.message);
    await fetchDeals();
  };

  return { deals, loading, error, refetch: fetchDeals, createDeal, updateDeal, deleteDeal };
}
