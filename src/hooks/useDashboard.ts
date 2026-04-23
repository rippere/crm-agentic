"use client";

import { useState, useEffect, useCallback } from "react";
import { formatCurrency } from "@/lib/utils";
import type { KPI } from "@/lib/types";

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
  const [data, setData] = useState<DashboardData | null>(null);
  const [kpis, setKpis] = useState<KPI[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/dashboard");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: DashboardData = await res.json();
      setData(json);
      setKpis(dataToKPIs(json));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  return { data, kpis, loading, error, refetch: fetchDashboard };
}
