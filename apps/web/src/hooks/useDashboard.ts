"use client";

import { useState, useEffect, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { formatCurrency } from "@/lib/utils";
import type { KPI } from "@/lib/types";
import type { ContactRow, DealRow, AgentRow, ActivityEventRow } from "@/lib/supabase";
import { isDemoMode } from "@/lib/demo-mode";
import { demoKPIs, demoDashboard } from "@/lib/demo-data";

interface DashboardData {
  totalRevenue: number;
  activeDeals: number;
  totalDeals: number;
  avgAccuracy: number;
  activeAgents: number;
  totalAgents: number;
  tasksToday: number;
  closedWonValue: number;
  avgWinProbability: number;
}

function dataToKPIs(d: DashboardData): KPI[] {
  return [
    {
      id: "k1",
      label: "Total Revenue",
      value: formatCurrency(d.totalRevenue),
      delta: "",
      deltaType: "positive",
      icon: "dollar",
      sparkData: [],
    },
    {
      id: "k2",
      label: "Active Deals",
      value: String(d.activeDeals),
      delta: `${d.totalDeals} total`,
      deltaType: "neutral",
      icon: "briefcase",
      sparkData: [],
    },
    {
      id: "k3",
      label: "ML Lead Accuracy",
      value: `${d.avgAccuracy}%`,
      delta: "",
      deltaType: "positive",
      icon: "brain",
      sparkData: [],
    },
    {
      id: "k4",
      label: "Agents Running",
      value: `${d.activeAgents} / ${d.totalAgents}`,
      delta: `${d.totalAgents - d.activeAgents} idle`,
      deltaType: "neutral",
      icon: "bot",
      sparkData: [],
    },
  ];
}

export function useDashboard() {
  const [data, setData] = useState<DashboardData | null>(
    isDemoMode ? (demoDashboard as unknown as DashboardData) : null
  );
  const [kpis, setKpis] = useState<KPI[]>(isDemoMode ? demoKPIs : []);
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    if (isDemoMode) {
      setData(demoDashboard as unknown as DashboardData);
      setKpis(demoKPIs);
      return;
    }

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

      // Parallel aggregate queries
      const [contactsRes, dealsRes, agentsRes, activityRes] = await Promise.all([
        supabase.from("contacts").select("revenue").eq("workspace_id", workspaceId),
        supabase.from("deals").select("value, stage, ml_win_probability").eq("workspace_id", workspaceId),
        supabase.from("agents").select("status, accuracy, tasks_today").eq("workspace_id", workspaceId),
        supabase
          .from("activity_events")
          .select("id")
          .eq("workspace_id", workspaceId)
          .gte("created_at", new Date(new Date().setHours(0, 0, 0, 0)).toISOString()),
      ]);

      const contacts = (contactsRes.data ?? []) as Pick<ContactRow, "revenue">[];
      const deals = (dealsRes.data ?? []) as Pick<DealRow, "value" | "stage" | "ml_win_probability">[];
      const agents = (agentsRes.data ?? []) as Pick<AgentRow, "status" | "accuracy" | "tasks_today">[];
      const todayActivity = (activityRes.data ?? []) as Pick<ActivityEventRow, "id">[];

      const totalRevenue = contacts.reduce((sum, c) => sum + (c.revenue ?? 0), 0);
      const activeDeals = deals.filter((d) => !["closed_won", "closed_lost"].includes(d.stage)).length;
      const closedWonValue = deals.filter((d) => d.stage === "closed_won").reduce((sum, d) => sum + (d.value ?? 0), 0);
      const avgWinProbability = deals.length
        ? Math.round(deals.reduce((sum, d) => sum + (d.ml_win_probability ?? 0), 0) / deals.length)
        : 0;
      const activeAgents = agents.filter((a) => a.status === "active" || a.status === "processing").length;
      const avgAccuracy = agents.length
        ? Math.round(agents.reduce((sum, a) => sum + (a.accuracy ?? 0), 0) / agents.length)
        : 0;
      const tasksToday = agents.reduce((sum, a) => sum + (a.tasks_today ?? 0), 0);

      const dashboardData: DashboardData = {
        totalRevenue,
        activeDeals,
        totalDeals: deals.length,
        avgAccuracy,
        activeAgents,
        totalAgents: agents.length,
        tasksToday: tasksToday || todayActivity.length,
        closedWonValue,
        avgWinProbability,
      };

      setData(dashboardData);
      setKpis(dataToKPIs(dashboardData));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isDemoMode) return;
    fetchDashboard();
  }, [fetchDashboard]);

  return { data, kpis, loading, error, refetch: fetchDashboard };
}
