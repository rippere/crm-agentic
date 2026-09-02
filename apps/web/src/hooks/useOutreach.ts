"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import type { PendingOutreach } from "@/lib/types";
import { isDemoMode } from "@/lib/demo-mode";
import { demoPendingOutreach } from "@/lib/demo-data";

// The pending-queue API returns snake_case rows; map to the camelCase app shape.
type PendingOutreachRow = {
  enrollment_id: string;
  lead_id: string;
  campaign_id: string | null;
  sequence_id: string | null;
  current_step: number;
  status: string;
  subject: string | null;
  body: string;
  lead_name?: string | null;
  lead_company?: string | null;
  ai_generated?: boolean;
};

function rowToPending(row: PendingOutreachRow): PendingOutreach {
  return {
    enrollmentId: row.enrollment_id,
    leadId: row.lead_id,
    campaignId: row.campaign_id,
    sequenceId: row.sequence_id,
    currentStep: row.current_step,
    status: row.status,
    subject: row.subject,
    body: row.body,
    leadName: row.lead_name ?? null,
    leadCompany: row.lead_company ?? null,
    aiGenerated: row.ai_generated ?? false,
  };
}

async function getAuth() {
  const supabase = createBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
  return { token, workspaceId };
}

export function useOutreach() {
  const [pending, setPending] = useState<PendingOutreach[]>(isDemoMode ? demoPendingOutreach : []);
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const fetchPending = useCallback(async () => {
    if (isDemoMode) {
      setPending(demoPendingOutreach);
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
      const data = await apiClient.listPendingOutreach(workspaceId, token);
      setPending(Array.isArray(data) ? (data as PendingOutreachRow[]).map(rowToPending) : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load outreach queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isDemoMode) {
      setPending(demoPendingOutreach);
      return;
    }
    fetchPending();
  }, [fetchPending]);

  const draft = async (enrollmentId: string) => {
    if (isDemoMode) {
      const p = demoPendingOutreach.find((x) => x.enrollmentId === enrollmentId);
      return { enrollment_id: enrollmentId, subject: p?.subject ?? null, body: p?.body ?? "", ai_generated: p?.aiGenerated ?? false };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    return apiClient.draftOutreach(workspaceId, enrollmentId, token);
  };

  const approve = async (enrollmentId: string, edited?: { subject?: string | null; body?: string | null }) => {
    if (isDemoMode) {
      setPending((prev) => prev.filter((p) => p.enrollmentId !== enrollmentId));
      return { status: "approved", enrollment_id: enrollmentId };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.approveOutreach(workspaceId, enrollmentId, edited, token);
    await fetchPending();
    return result;
  };

  const reject = async (enrollmentId: string, reason?: string) => {
    if (isDemoMode) {
      setPending((prev) => prev.filter((p) => p.enrollmentId !== enrollmentId));
      return { status: "rejected", enrollment_id: enrollmentId };
    }
    const { token, workspaceId } = await getAuth();
    if (!workspaceId || !token) throw new Error("Not authenticated");
    const result = await apiClient.rejectOutreach(workspaceId, enrollmentId, reason, token);
    await fetchPending();
    return result;
  };

  return { pending, items: pending, loading, error, refetch: fetchPending, draft, approve, reject };
}
