"use client";

import { useState, useEffect, useCallback } from "react";
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
    const params = new URLSearchParams();
    if (stage && stage !== "all") params.set("stage", stage);

    try {
      const res = await fetch(`/api/deals?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: DealRow[] = await res.json();
      setDeals(data.map(rowToDeal));
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
    const res = await fetch("/api/deals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    await fetchDeals();
    return res.json();
  };

  const updateDeal = async (id: string, payload: Partial<Deal> & { stage?: Deal["stage"] }) => {
    const res = await fetch(`/api/deals/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    await fetchDeals();
    return res.json();
  };

  const deleteDeal = async (id: string) => {
    const res = await fetch(`/api/deals/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await res.text());
    await fetchDeals();
  };

  return { deals, loading, error, refetch: fetchDeals, createDeal, updateDeal, deleteDeal };
}
