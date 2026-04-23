"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { createBrowserClient } from "@/lib/supabase";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { apiClient } from "@/lib/api-client";
import { Briefcase, Brain, Clock, ChevronRight, FolderOpen } from "lucide-react";

interface Task {
  id: string;
  title: string;
  status: "open" | "in_progress" | "done";
  contact_id: string | null;
  contact_name?: string;
  contact_company?: string;
  updated_at?: string | null;
  clarity_score?: { score: number } | null;
}

interface ProjectGroup {
  contactId: string;
  contactName: string;
  company: string;
  openCount: number;
  avgClarity: number | null;
  lastActivity: string | null;
  tasks: Task[];
}

function formatRelative(dateStr: string | null): string {
  if (!dateStr) return "No activity";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function clarityVariant(score: number | null): "emerald" | "amber" | "rose" | "zinc" {
  if (score === null) return "zinc";
  return score >= 70 ? "emerald" : score >= 40 ? "amber" : "rose";
}

function ProjectCard({ group, onClick }: { group: ProjectGroup; onClick: () => void }) {
  return (
    <Card hover className="flex flex-col gap-4 cursor-pointer" onClick={onClick}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-indigo-500/20 bg-indigo-500/10 flex-shrink-0">
            <Briefcase className="h-5 w-5 text-indigo-400" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100 truncate">{group.company || group.contactName}</p>
            <p className="text-xs text-zinc-500 truncate">{group.contactName}</p>
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-zinc-600 flex-shrink-0 mt-1" />
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-2.5 py-2 text-center">
          <p className="text-lg font-bold font-mono text-zinc-100">{group.openCount}</p>
          <p className="text-[10px] text-zinc-500 mt-0.5">Open Tasks</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-2.5 py-2 text-center">
          <p className="text-lg font-bold font-mono text-zinc-100">{group.tasks.length}</p>
          <p className="text-[10px] text-zinc-500 mt-0.5">Total Tasks</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-2.5 py-2 text-center">
          {group.avgClarity !== null ? (
            <>
              <Badge variant={clarityVariant(group.avgClarity)} size="sm" className="mx-auto">
                <Brain className="h-2.5 w-2.5 mr-1" />
                {group.avgClarity}
              </Badge>
              <p className="text-[10px] text-zinc-500 mt-0.5">Avg Clarity</p>
            </>
          ) : (
            <>
              <p className="text-sm font-mono text-zinc-600">—</p>
              <p className="text-[10px] text-zinc-500 mt-0.5">Avg Clarity</p>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 font-mono">
        <Clock className="h-3 w-3" />
        {formatRelative(group.lastActivity)}
      </div>
    </Card>
  );
}

export default function ProjectsPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId(session.user.user_metadata?.workspace_id ?? null);
      }
    });
  }, []);

  useEffect(() => {
    if (!workspaceId || !token) return;
    apiClient
      .getTasks(workspaceId, token)
      .then((data) => setTasks(Array.isArray(data) ? data : []))
      .catch(() => setTasks([]))
      .finally(() => setLoading(false));
  }, [workspaceId, token]);

  const projects = useMemo<ProjectGroup[]>(() => {
    const linked = tasks.filter((t) => t.contact_id);
    const byContact: Record<string, Task[]> = {};
    for (const t of linked) {
      if (!byContact[t.contact_id!]) byContact[t.contact_id!] = [];
      byContact[t.contact_id!].push(t);
    }

    return Object.entries(byContact).map(([contactId, contactTasks]) => {
      const openCount = contactTasks.filter((t) => t.status === "open").length;
      const scored = contactTasks.filter((t) => t.clarity_score?.score != null);
      const avgClarity =
        scored.length > 0
          ? Math.round(scored.reduce((s, t) => s + (t.clarity_score?.score ?? 0), 0) / scored.length)
          : null;
      const lastActivity =
        contactTasks
          .map((t) => t.updated_at)
          .filter(Boolean)
          .sort()
          .reverse()[0] ?? null;

      return {
        contactId,
        contactName: contactTasks[0].contact_name ?? "Unknown Contact",
        company: contactTasks[0].contact_company ?? "",
        openCount,
        avgClarity,
        lastActivity,
        tasks: contactTasks,
      };
    });
  }, [tasks]);

  const handleProjectClick = (group: ProjectGroup) => {
    // Navigate to tasks filtered by contact — uses URL search param
    router.push(`/tasks?contact=${group.contactId}`);
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <Header title="Projects" subtitle={`${projects.length} active projects`} />

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-44 rounded-2xl border border-zinc-800 bg-zinc-900 animate-pulse" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-20 px-4 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900">
            <FolderOpen className="h-7 w-7 text-zinc-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-zinc-300">No projects yet</p>
            <p className="text-xs text-zinc-500 mt-1 max-w-xs">
              Projects appear here as tasks are extracted from your Gmail conversations.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((group) => (
            <ProjectCard
              key={group.contactId}
              group={group}
              onClick={() => handleProjectClick(group)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
