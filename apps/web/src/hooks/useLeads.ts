"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import type { Lead } from "@/lib/types";
import type { LeadRow } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-mode";
import { demoLeads } from "@/lib/demo-data";

function rowToLead(row: LeadRow): Lead {
  return {
    id: row.id,
    workspaceId: row.workspace_id,
    contactId: row.contact_id,
    name: row.name,
    email: row.email,
    phone: row.phone,
    company: row.company,
    title: row.title,
    source: row.source,
    stage: row.stage,
    score: row.score,
    scoreDetail: row.score_detail ?? { value: row.score ?? 0, label: "cold", signals: [] },
    ownerId: row.owner_id,
    customFields: row.custom_fields ?? {},
    externalId: row.external_id,
    lastEngagedAt: row.last_engaged_at,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function filterDemoLeads(leads: Lead[], stage?: string): Lead[] {
  if (stage && stage !== "all") return leads.filter((l) => l.stage === stage);
  return leads;
}

// Build a fully-shaped Lead from a create/import payload so the demo UI can
// insert it locally (no API round-trip in demo mode).
function makeDemoLead(data: Partial<Parameters<typeof apiClient.createLead>[1]>): Lead {
  const now = new Date().toISOString();
  const score = data.score ?? 0;
  const label: Lead["scoreDetail"]["label"] = score >= 70 ? "hot" : score >= 40 ? "warm" : "cold";
  return {
    id: `demo-lead-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    workspaceId: demoLeads[0]?.workspaceId ?? "demo-workspace",
    contactId: null,
    name: data.name ?? null,
    email: data.email ?? null,
    phone: data.phone ?? null,
    company: data.company ?? null,
    title: data.title ?? null,
    source: (data.source as Lead["source"]) ?? "manual",
    stage: (data.stage as Lead["stage"]) ?? "new",
    score,
    scoreDetail: { value: score, label, signals: [] },
    ownerId: data.owner_id ?? null,
    customFields: data.custom_fields ?? {},
    externalId: data.external_id ?? null,
    lastEngagedAt: null,
    createdAt: now,
    updatedAt: now,
  };
}

async function getAuth() {
  const supabase = createBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
  return { token, workspaceId };
}

export function useLeads(opts?: { stage?: string; source?: string; minScore?: number; segmentId?: string; q?: string; sort?: string }) {
  const stage = opts?.stage;
  const [leads, setLeads] = useState<Lead[]>(
    isDemoMode ? filterDemoLeads(demoLeads, stage) : []
  );
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const fetchLeads = useCallback(async () => {
    if (isDemoMode) {
      setLeads(filterDemoLeads(demoLeads, stage));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { token, workspaceId } = await getAuth();
      if (!workspaceId || !token) {
        setError("No workspace found");
        return;
      }
      const data = await apiClient.listLeads(workspaceId, token, opts);
      setLeads(Array.isArray(data) ? (data as LeadRow[]).map(rowToLead) : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load leads");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, opts?.source, opts?.minScore, opts?.segmentId, opts?.q, opts?.sort]);

  useEffect(() => {
    if (isDemoMode) {
      setLeads(filterDemoLeads(demoLeads, stage));
      return;
    }
    fetchLeads();
  }, [fetchLeads, stage]);

  const createLead = async (data: Parameters<typeof apiClient.createLead>[1]) => {
    if (isDemoMode) {
      const lead = makeDemoLead(data);
      setLeads((prev) => [lead, ...prev]);
      return { id: lead.id };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.createLead(workspaceId, data, token);
    await fetchLeads();
    return result;
  };

  const updateLead = async (id: string, data: Parameters<typeof apiClient.updateLead>[2]) => {
    if (isDemoMode) return {};
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.updateLead(workspaceId, id, data, token);
    await fetchLeads();
    return result;
  };

  const deleteLead = async (id: string) => {
    if (isDemoMode) {
      setLeads((prev) => prev.filter((l) => l.id !== id));
      return;
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    await apiClient.deleteLead(workspaceId, id, token);
    await fetchLeads();
  };

  const updateStage = async (id: string, stageValue: Lead["stage"]) => {
    if (isDemoMode) {
      setLeads((prev) =>
        prev.map((l) => (l.id === id ? { ...l, stage: stageValue, updatedAt: new Date().toISOString() } : l))
      );
      return { id, stage: stageValue };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.updateLeadStage(workspaceId, id, stageValue, token);
    await fetchLeads();
    return result;
  };

  const promoteLead = async (id: string, data?: { create_deal?: boolean; owner_id?: string }) => {
    if (isDemoMode) {
      const contactId = `demo-contact-${Date.now()}`;
      const dealId = data?.create_deal ? `demo-deal-${Date.now()}` : null;
      const nextStage: Lead["stage"] = data?.create_deal ? "converted" : "qualified";
      setLeads((prev) =>
        prev.map((l) =>
          l.id === id ? { ...l, stage: nextStage, contactId, updatedAt: new Date().toISOString() } : l
        )
      );
      return { lead: { id }, contact_id: contactId, deal_id: dealId };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.promoteLead(workspaceId, id, data ?? {}, token);
    await fetchLeads();
    return result;
  };

  const importLeads = async (rows: Array<Record<string, unknown>>, mapping?: Record<string, string>, dedupeOn?: string) => {
    if (isDemoMode) {
      const str = (v: unknown) => (typeof v === "string" && v.trim() !== "" ? v.trim() : undefined);
      const imported = rows.map((row) =>
        makeDemoLead({
          name: str(row.name),
          email: str(row.email),
          phone: str(row.phone),
          company: str(row.company),
          title: str(row.title),
          external_id: str(row.external_id),
          source: "import",
        })
      );
      setLeads((prev) => [...imported, ...prev]);
      return { status: "queued", job_id: `demo-import-${Date.now()}` };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    return apiClient.importLeads(workspaceId, { rows, mapping, dedupe_on: dedupeOn }, token);
  };

  return { leads, items: leads, loading, error, refetch: fetchLeads, createLead, updateLead, deleteLead, updateStage, promoteLead, importLeads };
}
