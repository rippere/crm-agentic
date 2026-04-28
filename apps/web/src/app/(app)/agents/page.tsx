"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Avatar from "@/components/ui/Avatar";
import { mockAgents } from "@/lib/mock-data";
import { cn, agentStatusConfig } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import {
  Brain, Sparkles, Mail, Mic, TrendingUp, Heart,
  Play, Pause, Settings, ChevronRight, Cpu, Target,
  ArrowRight, GitBranch, Zap,
} from "lucide-react";
import type { Agent, AgentType, WorkflowNode } from "@/lib/types";

interface Toast {
  id: number;
  message: string;
  type: "success" | "error" | "info";
}

const agentTypeIcon: Record<AgentType, React.ReactNode> = {
  semantic_sorter: <Sparkles className="h-4 w-4" />,
  lead_scorer: <Brain className="h-4 w-4" />,
  email_composer: <Mail className="h-4 w-4" />,
  call_summarizer: <Mic className="h-4 w-4" />,
  pipeline_optimizer: <TrendingUp className="h-4 w-4" />,
  sentiment_analyzer: <Heart className="h-4 w-4" />,
};

const agentTypeColor: Record<AgentType, string> = {
  semantic_sorter: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20",
  lead_scorer: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  email_composer: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  call_summarizer: "text-rose-400 bg-rose-500/10 border-rose-500/20",
  pipeline_optimizer: "text-primary-300 bg-indigo-500/10 border-indigo-500/20",
  sentiment_analyzer: "text-pink-400 bg-pink-500/10 border-pink-500/20",
};

const nodeTypeStyle: Record<WorkflowNode["type"], { bg: string; border: string; text: string }> = {
  trigger: { bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-300" },
  action: { bg: "bg-indigo-500/10", border: "border-indigo-500/30", text: "text-indigo-300" },
  condition: { bg: "bg-amber-500/10", border: "border-amber-500/30", text: "text-amber-300" },
  output: { bg: "bg-zinc-700/50", border: "border-zinc-600", text: "text-zinc-300" },
};

const nodeTypeIcon: Record<WorkflowNode["type"], React.ReactNode> = {
  trigger: <Zap className="h-3 w-3" />,
  action: <Cpu className="h-3 w-3" />,
  condition: <GitBranch className="h-3 w-3" />,
  output: <Target className="h-3 w-3" />,
};

function WorkflowDiagram({ nodes }: { nodes: WorkflowNode[] }) {
  return (
    <div className="overflow-x-auto" role="img" aria-label="Agent workflow diagram">
      <div className="flex items-center gap-2 py-4 px-2 min-w-max">
        {nodes.map((node, idx) => (
          <div key={node.id} className="flex items-center gap-2">
            {/* Node */}
            <div
              className={cn(
                "flex items-center gap-2 rounded-xl border px-3 py-2.5 text-xs font-medium whitespace-nowrap",
                nodeTypeStyle[node.type].bg,
                nodeTypeStyle[node.type].border,
                nodeTypeStyle[node.type].text
              )}
            >
              <span className="flex-shrink-0">{nodeTypeIcon[node.type]}</span>
              {node.label}
            </div>
            {/* Arrow (not after last node) */}
            {idx < nodes.length - 1 && (
              <ArrowRight className="h-3.5 w-3.5 text-zinc-600 flex-shrink-0" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>
      {/* Legend */}
      <div className="flex flex-wrap gap-3 px-2 pb-2">
        {(["trigger", "action", "condition", "output"] as const).map((type) => (
          <div key={type} className="flex items-center gap-1.5">
            <span className={cn("flex h-5 w-5 items-center justify-center rounded border text-[10px]",
              nodeTypeStyle[type].bg, nodeTypeStyle[type].border, nodeTypeStyle[type].text
            )}>
              {nodeTypeIcon[type]}
            </span>
            <span className="text-[10px] text-zinc-500 capitalize">{type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AgentCard({ agent, onSelect }: { agent: Agent; onSelect: () => void }) {
  const statusCfg = agentStatusConfig[agent.status];
  const typeCfg = agentTypeColor[agent.type];

  return (
    <Card hover glow className="flex flex-col gap-4 cursor-pointer" onClick={onSelect}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl border flex-shrink-0", typeCfg)}>
            {agentTypeIcon[agent.type]}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100">{agent.name}</p>
            <p className="text-[10px] text-zinc-500 font-mono truncate">{agent.model}</p>
          </div>
        </div>
        <Badge
          variant={
            agent.status === "active"
              ? "emerald"
              : agent.status === "processing"
              ? "indigo"
              : agent.status === "error"
              ? "rose"
              : "zinc"
          }
          dot
          pulse={agent.status === "active" || agent.status === "processing"}
          size="sm"
        >
          {statusCfg.label}
        </Badge>
      </div>

      {/* Description */}
      <p className="text-xs text-zinc-400 leading-relaxed line-clamp-2">{agent.description}</p>

      {/* Accuracy bar */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[10px] text-zinc-500 font-mono">Model Accuracy</span>
          <span className="text-xs font-mono text-emerald-400 font-semibold">{agent.accuracy}%</span>
        </div>
        <div
          className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden"
          role="progressbar"
          aria-valuenow={agent.accuracy}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${agent.name} accuracy: ${agent.accuracy}%`}
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-emerald-400"
            style={{ width: `${agent.accuracy}%` }}
          />
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-2">
        {agent.metrics.map((m) => (
          <div key={m.label} className="rounded-lg bg-zinc-800/60 px-2.5 py-2 text-center">
            <p className="text-sm font-mono font-bold text-zinc-100">{m.value}</p>
            {m.delta && (
              <p className="text-[9px] font-mono text-emerald-400">{m.delta}</p>
            )}
            <p className="text-[9px] text-zinc-600 mt-0.5 leading-tight">{m.label}</p>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-zinc-800">
        <span className="text-[10px] text-zinc-500 font-mono">
          Last run: {agent.lastRun}
        </span>
        <div className="flex items-center gap-1.5">
          <ChevronRight className="h-3.5 w-3.5 text-zinc-600" aria-hidden="true" />
        </div>
      </div>
    </Card>
  );
}

function AgentDetailPanel({
  agent,
  onClose,
  token,
  onRun,
}: {
  agent: Agent;
  onClose: () => void;
  token: string | null;
  onRun: (agentId: string) => Promise<void>;
}) {
  const [running, setRunning] = useState(agent.status === "active" || agent.status === "processing");
  const statusCfg = agentStatusConfig[running ? "active" : "idle"];

  return (
    <aside
      className="fixed right-0 top-0 h-full w-[520px] border-l border-zinc-800 bg-zinc-950 z-40 overflow-y-auto"
      aria-label={`${agent.name} configuration`}
    >
      {/* Header */}
      <div className="sticky top-0 flex items-center justify-between border-b border-zinc-800 bg-zinc-950/90 backdrop-blur px-5 py-4">
        <div className="flex items-center gap-3">
          <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg border flex-shrink-0", agentTypeColor[agent.type])}>
            {agentTypeIcon[agent.type]}
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-100">{agent.name}</p>
            <p className="text-[10px] text-zinc-500 font-mono">{agent.model}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-zinc-400 hover:text-zinc-100 cursor-pointer transition-colors text-sm"
          aria-label="Close agent panel"
        >
          ✕
        </button>
      </div>

      <div className="p-5 space-y-6">
        {/* Status + Controls */}
        <div className="flex items-center justify-between">
          <Badge
            variant={running ? "emerald" : "zinc"}
            dot
            pulse={running}
            size="md"
          >
            {running ? "Active" : "Paused"}
          </Badge>
          <div className="flex items-center gap-2">
            <Button
              variant={running ? "secondary" : "cta"}
              size="sm"
              onClick={async () => {
                if (!running) {
                  await onRun(agent.id);
                }
                setRunning(!running);
              }}
            >
              {running ? (
                <><Pause className="h-3.5 w-3.5" aria-hidden="true" /> Pause</>
              ) : (
                <><Play className="h-3.5 w-3.5" aria-hidden="true" /> Start</>
              )}
            </Button>
            <Button variant="secondary" size="sm">
              <Settings className="h-3.5 w-3.5" aria-hidden="true" />
              Configure
            </Button>
          </div>
        </div>

        {/* Description */}
        <div>
          <p className="text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-widest font-mono">Description</p>
          <p className="text-sm text-zinc-300 leading-relaxed">{agent.description}</p>
        </div>

        {/* Accuracy */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-indigo-400" aria-hidden="true" />
              <p className="text-xs font-semibold text-zinc-300">Model Performance</p>
            </div>
            <span className="text-lg font-bold font-mono text-emerald-400">{agent.accuracy}%</span>
          </div>
          <div
            className="h-2 w-full rounded-full bg-zinc-800 overflow-hidden"
            role="progressbar"
            aria-valuenow={agent.accuracy}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Model accuracy: ${agent.accuracy}%`}
          >
            <div
              className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-emerald-400"
              style={{ width: `${agent.accuracy}%` }}
            />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-3">
            {agent.metrics.map((m) => (
              <div key={m.label} className="text-center">
                <p className="text-base font-bold font-mono text-zinc-100">{m.value}</p>
                {m.delta && <p className="text-[10px] font-mono text-emerald-400">{m.delta}</p>}
                <p className="text-[10px] text-zinc-600 mt-0.5">{m.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Workflow */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <GitBranch className="h-4 w-4 text-indigo-400" aria-hidden="true" />
            <p className="text-xs font-semibold text-zinc-300">Workflow Pipeline</p>
          </div>
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/50">
            <WorkflowDiagram nodes={agent.workflow} />
          </div>
        </div>

        {/* Tasks stats */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-center">
            <p className="text-2xl font-bold font-mono text-zinc-100">{agent.tasksToday.toLocaleString()}</p>
            <p className="text-xs text-zinc-500 mt-1">Tasks Today</p>
          </div>
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-center">
            <p className="text-sm font-mono text-zinc-300 mt-1">{agent.lastRun}</p>
            <p className="text-xs text-zinc-500 mt-1">Last Run</p>
          </div>
        </div>

        {/* Danger zone */}
        <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-4">
          <p className="text-xs font-semibold text-rose-400 mb-2">Danger Zone</p>
          <p className="text-xs text-zinc-500 mb-3">Retrain, reset, or decommission this agent.</p>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm">Retrain Model</Button>
            <Button variant="danger" size="sm">Decommission</Button>
          </div>
        </div>
      </div>
    </aside>
  );
}

export default function AgentsPage() {
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [agents, setAgents] = useState(mockAgents);
  const [token, setToken] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const addToast = useCallback((message: string, type: Toast["type"] = "info") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000);
  }, []);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
      setToken('demo-token');
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) setToken(session.access_token);
    });
  }, []);

  const normalizeAgent = (a: Record<string, unknown>): Agent => ({
    ...(a as unknown as Agent),
    tasksToday: (a.tasks_today ?? a.tasksToday ?? 0) as number,
    lastRun: (a.last_run ?? a.lastRun ?? "Never") as string,
    metrics: (a.metrics ?? []) as Agent["metrics"],
    workflow: (a.workflow ?? []) as Agent["workflow"],
  });

  // Initial fetch from API
  useEffect(() => {
    if (!token) return;
    if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') return;
    fetch(
      `${process.env.NEXT_PUBLIC_FASTAPI_URL || "http://localhost:8000"}/agents`,
      { headers: { Authorization: `Bearer ${token}` } }
    )
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) setAgents(data.map(normalizeAgent));
      })
      .catch(() => {});
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll /agents every 5s if any agent is processing
  const pollAgents = useCallback(async () => {
    if (!token) return;
    try {
      const data = await fetch(
        `${process.env.NEXT_PUBLIC_FASTAPI_URL || "http://localhost:8000"}/agents`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (data.ok) {
        const updated = await data.json();
        if (Array.isArray(updated)) setAgents(updated.map(normalizeAgent));
      }
    } catch {
      // silently ignore polling failures
    }
  }, [token]);

  useEffect(() => {
    const hasProcessing = agents.some((a) => a.status === "processing");
    if (hasProcessing) {
      pollRef.current = setInterval(pollAgents, 5000);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [agents, pollAgents]);

  const handleRun = useCallback(async (agentId: string) => {
    if (!token) return;
    try {
      const result = await apiClient.triggerAgent(agentId, token);
      const jobId = result?.job_id ?? result?.id ?? "unknown";
      addToast(`Agent started — job ${jobId}`, "success");
      // Mark as processing
      setAgents((prev) => prev.map((a) => a.id === agentId ? { ...a, status: "processing" as const } : a));
    } catch {
      addToast("Failed to start agent — check API connection", "error");
    }
  }, [token, addToast]);

  const activeCount = agents.filter((a) => a.status === "active").length;
  const processingCount = agents.filter((a) => a.status === "processing").length;
  const avgAccuracy = (
    agents.reduce((sum, a) => sum + a.accuracy, 0) / agents.length
  ).toFixed(1);

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Toast stack */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`rounded-xl border px-4 py-3 text-sm font-medium shadow-xl animate-slide-up pointer-events-auto ${
              t.type === "success"
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                : t.type === "error"
                ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                : "border-indigo-500/40 bg-indigo-600/10 text-indigo-300"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>

      <Header
        title="Agents"
        subtitle={`${activeCount} active · ${processingCount} processing · avg accuracy ${avgAccuracy}%`}
      />

      {/* Summary */}
      <div className="grid grid-cols-3 gap-3">
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex-shrink-0">
            <Zap className="h-4 w-4 text-emerald-400" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xl font-bold font-mono text-zinc-100">{activeCount}</p>
            <p className="text-xs text-zinc-500">Active Agents</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex-shrink-0">
            <Cpu className="h-4 w-4 text-indigo-400" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xl font-bold font-mono text-zinc-100">
              {agents.reduce((s, a) => s + a.tasksToday, 0).toLocaleString()}
            </p>
            <p className="text-xs text-zinc-500">Tasks Today</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/20 flex-shrink-0">
            <Target className="h-4 w-4 text-amber-400" aria-hidden="true" />
          </div>
          <div>
            <p className="text-xl font-bold font-mono text-emerald-400">{avgAccuracy}%</p>
            <p className="text-xs text-zinc-500">Avg Accuracy</p>
          </div>
        </Card>
      </div>

      {/* Agent grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3" role="list" aria-label="AI Agents">
        {agents.map((agent) => (
          <div key={agent.id} role="listitem">
            <AgentCard agent={agent} onSelect={() => setSelectedAgent(agent)} />
          </div>
        ))}
      </div>

      {/* Detail panel overlay */}
      {selectedAgent && (
        <>
          <div
            className="fixed inset-0 bg-black/50 z-30"
            onClick={() => setSelectedAgent(null)}
            aria-hidden="true"
          />
          <AgentDetailPanel
            agent={selectedAgent}
            onClose={() => setSelectedAgent(null)}
            token={token}
            onRun={handleRun}
          />
        </>
      )}
    </div>
  );
}
