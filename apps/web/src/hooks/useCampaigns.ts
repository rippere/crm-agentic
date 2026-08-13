"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import type { Campaign } from "@/lib/types";
import type { CampaignRow } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-mode";
import { demoCampaigns } from "@/lib/demo-data";

function rowToCampaign(row: CampaignRow): Campaign {
  return {
    id: row.id,
    workspaceId: row.workspace_id,
    segmentId: row.segment_id,
    sequenceId: row.sequence_id,
    name: row.name,
    status: row.status,
    channel: row.channel,
    scheduledAt: row.scheduled_at,
    startedAt: row.started_at,
    completedAt: row.completed_at,
    stats: row.stats ?? {},
    settings: row.settings ?? {},
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

async function getAuth() {
  const supabase = createBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
  return { token, workspaceId };
}

function filterDemoCampaigns(status?: string): Campaign[] {
  if (status && status !== "all") return demoCampaigns.filter((c) => c.status === status);
  return demoCampaigns;
}

// Build a fully-shaped Campaign from a create payload for local demo insertion.
function makeDemoCampaign(data: Parameters<typeof apiClient.createCampaign>[1]): Campaign {
  const now = new Date().toISOString();
  return {
    id: `demo-cmp-${Date.now()}`,
    workspaceId: demoCampaigns[0]?.workspaceId ?? "demo-workspace",
    segmentId: data.segment_id ?? null,
    sequenceId: data.sequence_id ?? null,
    name: data.name,
    status: "draft",
    channel: (data.channel as Campaign["channel"]) ?? "email",
    scheduledAt: null,
    startedAt: null,
    completedAt: null,
    stats: {},
    settings: data.settings ?? {},
    createdAt: now,
    updatedAt: now,
  };
}

export function useCampaigns(opts?: { status?: string }) {
  const status = opts?.status;
  const [campaigns, setCampaigns] = useState<Campaign[]>(isDemoMode ? filterDemoCampaigns(status) : []);
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const fetchCampaigns = useCallback(async () => {
    if (isDemoMode) {
      setCampaigns(filterDemoCampaigns(status));
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
      const data = await apiClient.listCampaigns(workspaceId, token, status ? { status } : undefined);
      setCampaigns(Array.isArray(data) ? (data as CampaignRow[]).map(rowToCampaign) : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load campaigns");
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    if (isDemoMode) {
      setCampaigns(filterDemoCampaigns(status));
      return;
    }
    fetchCampaigns();
  }, [fetchCampaigns, status]);

  const createCampaign = async (data: Parameters<typeof apiClient.createCampaign>[1]) => {
    if (isDemoMode) {
      const campaign = makeDemoCampaign(data);
      setCampaigns((prev) => [campaign, ...prev]);
      return { id: campaign.id };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.createCampaign(workspaceId, data, token);
    await fetchCampaigns();
    return result;
  };

  const updateCampaign = async (id: string, data: Parameters<typeof apiClient.updateCampaign>[2]) => {
    if (isDemoMode) {
      setCampaigns((prev) =>
        prev.map((c) =>
          c.id === id
            ? {
                ...c,
                name: data.name ?? c.name,
                segmentId: data.segment_id ?? c.segmentId,
                sequenceId: data.sequence_id ?? c.sequenceId,
                channel: (data.channel as Campaign["channel"]) ?? c.channel,
                settings: data.settings ?? c.settings,
                updatedAt: new Date().toISOString(),
              }
            : c
        )
      );
      return { id };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.updateCampaign(workspaceId, id, data, token);
    await fetchCampaigns();
    return result;
  };

  const scheduleCampaign = async (id: string, scheduledAt: string) => {
    if (isDemoMode) {
      setCampaigns((prev) =>
        prev.map((c) =>
          c.id === id ? { ...c, status: "scheduled", scheduledAt, updatedAt: new Date().toISOString() } : c
        )
      );
      return { id, status: "scheduled", scheduled_at: scheduledAt };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.scheduleCampaign(workspaceId, id, scheduledAt, token);
    await fetchCampaigns();
    return result;
  };

  const launchCampaign = async (id: string) => {
    if (isDemoMode) {
      const now = new Date().toISOString();
      setCampaigns((prev) =>
        prev.map((c) =>
          c.id === id ? { ...c, status: "active", startedAt: c.startedAt ?? now, updatedAt: now } : c
        )
      );
      return { status: "queued", job_id: "demo-enroll" };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.launchCampaign(workspaceId, id, token);
    await fetchCampaigns();
    return result;
  };

  const pauseCampaign = async (id: string) => {
    if (isDemoMode) {
      setCampaigns((prev) =>
        prev.map((c) => (c.id === id ? { ...c, status: "paused", updatedAt: new Date().toISOString() } : c))
      );
      return { id, status: "paused" };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.pauseCampaign(workspaceId, id, token);
    await fetchCampaigns();
    return result;
  };

  const resumeCampaign = async (id: string) => {
    if (isDemoMode) {
      setCampaigns((prev) =>
        prev.map((c) => (c.id === id ? { ...c, status: "active", updatedAt: new Date().toISOString() } : c))
      );
      return { id, status: "active" };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.resumeCampaign(workspaceId, id, token);
    await fetchCampaigns();
    return result;
  };

  const getStats = async (id: string) => {
    if (isDemoMode) return apiClient.getCampaignStats("demo", id, "demo");
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    return apiClient.getCampaignStats(workspaceId, id, token);
  };

  const getEnrollments = async (id: string) => {
    if (isDemoMode) return apiClient.getCampaignEnrollments("demo", id, "demo");
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    return apiClient.getCampaignEnrollments(workspaceId, id, token);
  };

  return { campaigns, items: campaigns, loading, error, refetch: fetchCampaigns, createCampaign, updateCampaign, scheduleCampaign, launchCampaign, pauseCampaign, resumeCampaign, getStats, getEnrollments };
}
