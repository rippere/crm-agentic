"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { createBrowserClient } from "@/lib/supabase";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { apiClient } from "@/lib/api-client";
import { Briefcase, Brain, Clock, ChevronRight, FolderOpen, Plus, X, Folder } from "lucide-react";

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

interface ManualProject {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  status: string;
  contact_id: string | null;
  created_at: string;
  updated_at: string;
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

function statusVariant(status: string): "emerald" | "amber" | "zinc" {
  if (status === "active") return "emerald";
  if (status === "completed") return "amber";
  return "zinc";
}

function AutoProjectCard({ group, onClick }: { group: ProjectGroup; onClick: () => void }) {
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

function ManualProjectCard({ project, onDelete, onClick }: { project: ManualProject; onDelete: (id: string) => void; onClick: () => void }) {
  return (
    <Card hover className="flex flex-col gap-4 cursor-pointer" onClick={onClick}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-violet-500/20 bg-violet-500/10 flex-shrink-0">
            <Folder className="h-5 w-5 text-violet-400" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-zinc-100 truncate">{project.name}</p>
            {project.description && (
              <p className="text-xs text-zinc-500 truncate mt-0.5">{project.description}</p>
            )}
          </div>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(project.id); }}
          className="text-zinc-600 hover:text-rose-400 transition-colors flex-shrink-0 mt-0.5"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex items-center justify-between">
        <Badge variant={statusVariant(project.status)} size="sm">
          {project.status}
        </Badge>
        <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 font-mono">
          <Clock className="h-3 w-3" />
          {formatRelative(project.updated_at)}
        </div>
      </div>
    </Card>
  );
}

function NewProjectModal({ onClose, onCreate }: { onClose: () => void; onCreate: (data: { name: string; description?: string; status: string }) => Promise<void> }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("active");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    try {
      await onCreate({ name: name.trim(), description: description.trim() || undefined, status });
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-base font-semibold text-zinc-100">New Project</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-xs font-medium text-zinc-400 mb-1.5 block">Name *</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Q3 Enterprise Expansion"
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-violet-500/50 focus:outline-none focus:ring-1 focus:ring-violet-500/30"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-zinc-400 mb-1.5 block">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional — what is this project about?"
              rows={3}
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-violet-500/50 focus:outline-none focus:ring-1 focus:ring-violet-500/30 resize-none"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-zinc-400 mb-1.5 block">Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-base sm:text-sm text-zinc-100 focus:border-violet-500/50 focus:outline-none focus:ring-1 focus:ring-violet-500/30"
            >
              <option value="active">Active</option>
              <option value="completed">Completed</option>
              <option value="archived">Archived</option>
            </select>
          </div>

          <div className="flex gap-3 mt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim() || saving}
              className="flex-1 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? "Creating…" : "Create Project"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [manualProjects, setManualProjects] = useState<ManualProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);

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
    Promise.all([
      apiClient.getTasks(workspaceId, token).catch(() => []),
      apiClient.listProjects(workspaceId, token).catch(() => []),
    ]).then(([taskData, projectData]) => {
      setTasks(Array.isArray(taskData) ? taskData : []);
      setManualProjects(Array.isArray(projectData) ? projectData : []);
    }).finally(() => setLoading(false));
  }, [workspaceId, token]);

  const autoProjects = useMemo<ProjectGroup[]>(() => {
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
        contactTasks.map((t) => t.updated_at).filter(Boolean).sort().reverse()[0] ?? null;
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

  async function handleCreate(data: { name: string; description?: string; status: string }) {
    if (!workspaceId || !token) return;
    const project = await apiClient.createProject(workspaceId, data, token);
    setManualProjects((prev) => [project, ...prev]);
  }

  async function handleDelete(projectId: string) {
    if (!workspaceId || !token) return;
    await apiClient.deleteProject(workspaceId, projectId, token);
    setManualProjects((prev) => prev.filter((p) => p.id !== projectId));
  }

  const totalCount = manualProjects.length + autoProjects.length;

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <div className="flex items-center justify-between">
        <Header title="Projects" subtitle={`${totalCount} project${totalCount !== 1 ? "s" : ""}`} />
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 rounded-lg bg-violet-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-violet-500 transition-colors"
        >
          <Plus className="h-4 w-4" />
          New Project
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-44 rounded-2xl border border-zinc-800 bg-zinc-900 animate-pulse" />
          ))}
        </div>
      ) : totalCount === 0 ? (
        <div className="flex flex-col items-center gap-4 py-20 px-4 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900">
            <FolderOpen className="h-7 w-7 text-zinc-600" />
          </div>
          <div>
            <p className="text-sm font-medium text-zinc-300">No projects yet</p>
            <p className="text-xs text-zinc-500 mt-1 max-w-xs">
              Create a project manually or sync Gmail to extract them from conversations.
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 transition-colors"
          >
            <Plus className="h-4 w-4" />
            New Project
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-8">
          {manualProjects.length > 0 && (
            <section>
              <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">Manual</p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {manualProjects.map((p) => (
                  <ManualProjectCard key={p.id} project={p} onDelete={handleDelete} onClick={() => router.push(`/projects/${p.id}`)} />
                ))}
              </div>
            </section>
          )}

          {autoProjects.length > 0 && (
            <section>
              <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">From Conversations</p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {autoProjects.map((group) => (
                  <AutoProjectCard
                    key={group.contactId}
                    group={group}
                    onClick={() => router.push(`/tasks?contact=${group.contactId}`)}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {showModal && (
        <NewProjectModal onClose={() => setShowModal(false)} onCreate={handleCreate} />
      )}
    </div>
  );
}
