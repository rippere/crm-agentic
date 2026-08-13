"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import type { Segment } from "@/lib/types";
import type { SegmentRow } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-mode";
import { demoSegments } from "@/lib/demo-data";

function rowToSegment(row: SegmentRow): Segment {
  return {
    id: row.id,
    workspaceId: row.workspace_id,
    name: row.name,
    description: row.description,
    kind: row.kind,
    filter: row.filter ?? {},
    memberCount: row.member_count ?? 0,
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

export function useSegments(opts?: { kind?: string }) {
  const kind = opts?.kind;
  const [segments, setSegments] = useState<Segment[]>(isDemoMode ? demoSegments : []);
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const fetchSegments = useCallback(async () => {
    if (isDemoMode) {
      setSegments(kind && kind !== "all" ? demoSegments.filter((s) => s.kind === kind) : demoSegments);
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
      const data = await apiClient.listSegments(workspaceId, token, kind ? { kind } : undefined);
      setSegments(Array.isArray(data) ? (data as SegmentRow[]).map(rowToSegment) : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load segments");
    } finally {
      setLoading(false);
    }
  }, [kind]);

  useEffect(() => {
    if (isDemoMode) {
      setSegments(kind && kind !== "all" ? demoSegments.filter((s) => s.kind === kind) : demoSegments);
      return;
    }
    fetchSegments();
  }, [fetchSegments, kind]);

  const createSegment = async (data: Parameters<typeof apiClient.createSegment>[1]) => {
    if (isDemoMode) return {};
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.createSegment(workspaceId, data, token);
    await fetchSegments();
    return result;
  };

  const updateSegment = async (id: string, data: Parameters<typeof apiClient.updateSegment>[2]) => {
    if (isDemoMode) return {};
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.updateSegment(workspaceId, id, data, token);
    await fetchSegments();
    return result;
  };

  const deleteSegment = async (id: string) => {
    if (isDemoMode) return;
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    await apiClient.deleteSegment(workspaceId, id, token);
    await fetchSegments();
  };

  const getMembers = async (id: string) => {
    if (isDemoMode) return apiClient.getSegmentMembers("demo", id, "demo");
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    return apiClient.getSegmentMembers(workspaceId, id, token);
  };

  const addMembers = async (id: string, leadIds: string[]) => {
    if (isDemoMode) return { segment_id: id, added: leadIds.length, member_count: leadIds.length };
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.addSegmentMembers(workspaceId, id, leadIds, token);
    await fetchSegments();
    return result;
  };

  const removeMember = async (id: string, leadId: string) => {
    if (isDemoMode) return;
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    await apiClient.removeSegmentMember(workspaceId, id, leadId, token);
    await fetchSegments();
  };

  return { segments, items: segments, loading, error, refetch: fetchSegments, createSegment, updateSegment, deleteSegment, getMembers, addMembers, removeMember };
}
