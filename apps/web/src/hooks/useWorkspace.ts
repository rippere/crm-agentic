"use client";

import { useState, useEffect } from "react";
import { createBrowserClient } from "@/lib/supabase";
import type { Workspace } from "@/lib/types";

interface UseWorkspaceResult {
  workspace: Workspace | null;
  isLoading: boolean;
  error: string | null;
}

export function useWorkspace(): UseWorkspaceResult {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchWorkspace() {
      setIsLoading(true);
      setError(null);
      try {
        const supabase = createBrowserClient();

        const { data: { user }, error: userError } = await supabase.auth.getUser();
        if (userError || !user) {
          if (!cancelled) setError("Not authenticated");
          return;
        }

        const workspaceId = user.user_metadata?.workspace_id as string | undefined;
        if (!workspaceId) {
          if (!cancelled) setError("No workspace found. Please complete onboarding.");
          return;
        }

        const { data, error: wsError } = await supabase
          .from("workspaces")
          .select("*")
          .eq("id", workspaceId)
          .single();

        if (wsError || !data) {
          if (!cancelled) setError(wsError?.message ?? "Failed to load workspace");
          return;
        }

        if (!cancelled) {
          setWorkspace(data as Workspace);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    fetchWorkspace();
    return () => { cancelled = true; };
  }, []);

  return { workspace, isLoading, error };
}
