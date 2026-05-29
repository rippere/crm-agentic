"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { ArrowLeft, Plus, CheckCircle2, Circle, Clock, Folder } from "lucide-react";

interface Project {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

interface Task {
  id: string;
  title: string;
  description: string;
  status: "open" | "in_progress" | "done";
  due_date: string | null;
  project_id: string | null;
  updated_at: string | null;
}

function statusVariant(s: string): "emerald" | "amber" | "zinc" {
  if (s === "active") return "emerald";
  if (s === "completed") return "amber";
  return "zinc";
}

function taskStatusIcon(s: string) {
  if (s === "done") return <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />;
  if (s === "in_progress") return <Clock className="h-4 w-4 text-amber-400 flex-shrink-0" />;
  return <Circle className="h-4 w-4 text-zinc-600 flex-shrink-0" />;
}

function nextStatus(current: string): string {
  if (current === "open") return "in_progress";
  if (current === "in_progress") return "done";
  return "open";
}

export default function ProjectDetailPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [addingTask, setAddingTask] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

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
      apiClient.getProject(workspaceId, projectId, token).catch(() => null),
      apiClient.getProjectTasks(workspaceId, projectId, token).catch(() => []),
    ]).then(([proj, taskData]) => {
      setProject(proj);
      setTasks(Array.isArray(taskData) ? taskData : []);
    }).finally(() => setLoading(false));
  }, [workspaceId, token, projectId]);

  async function handleToggleTask(task: Task) {
    if (!workspaceId || !token) return;
    const updated = await apiClient.updateTask(workspaceId, task.id, { status: nextStatus(task.status) }, token);
    setTasks((prev) => prev.map((t) => (t.id === task.id ? { ...t, status: updated.status } : t)));
  }

  async function handleAddTask(e: React.FormEvent) {
    e.preventDefault();
    if (!newTaskTitle.trim() || !workspaceId || !token) return;
    setAddingTask(true);
    try {
      const created = await apiClient.createTask(workspaceId, {
        title: newTaskTitle.trim(),
        project_id: projectId,
        status: "open",
      }, token);
      setTasks((prev) => [created, ...prev]);
      setNewTaskTitle("");
      setShowAddForm(false);
    } finally {
      setAddingTask(false);
    }
  }

  const total = tasks.length;
  const done = tasks.filter((t) => t.status === "done").length;
  const open = tasks.filter((t) => t.status === "open").length;
  const inProgress = tasks.filter((t) => t.status === "in_progress").length;
  const progress = total > 0 ? Math.round((done / total) * 100) : 0;

  if (loading) {
    return (
      <div className="flex flex-col gap-6 p-4 md:p-6">
        <div className="h-8 w-48 rounded-lg bg-zinc-800 animate-pulse" />
        <div className="h-32 rounded-2xl bg-zinc-900 animate-pulse" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center gap-4 py-20 p-6">
        <p className="text-sm text-zinc-500">Project not found.</p>
        <button onClick={() => router.push("/projects")} className="text-xs text-violet-400 hover:text-violet-300">
          Back to Projects
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      {/* Back + Header */}
      <div className="flex items-start gap-4">
        <button
          onClick={() => router.push("/projects")}
          className="mt-0.5 text-zinc-500 hover:text-zinc-300 transition-colors flex-shrink-0"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-violet-500/20 bg-violet-500/10 flex-shrink-0">
              <Folder className="h-4 w-4 text-violet-400" />
            </div>
            <h1 className="text-lg font-semibold text-zinc-100">{project.name}</h1>
            <Badge variant={statusVariant(project.status)} size="sm">{project.status}</Badge>
          </div>
          {project.description && (
            <p className="text-sm text-zinc-500 mt-1.5 ml-12">{project.description}</p>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Total", value: total },
          { label: "Open", value: open },
          { label: "In Progress", value: inProgress },
          { label: "Done", value: done },
        ].map(({ label, value }) => (
          <Card key={label} className="text-center py-3">
            <p className="text-2xl font-bold font-mono text-zinc-100">{value}</p>
            <p className="text-[11px] text-zinc-500 mt-0.5">{label}</p>
          </Card>
        ))}
      </div>

      {/* Progress bar */}
      {total > 0 && (
        <div>
          <div className="flex justify-between text-xs text-zinc-500 mb-1.5">
            <span>Progress</span>
            <span className="font-mono">{progress}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-zinc-800">
            <div
              className="h-2 rounded-full bg-gradient-to-r from-violet-500 to-emerald-500 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Tasks */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider">Tasks</p>
          <button
            onClick={() => setShowAddForm((v) => !v)}
            className="flex items-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Task
          </button>
        </div>

        {showAddForm && (
          <form onSubmit={handleAddTask} className="flex gap-2">
            <input
              autoFocus
              value={newTaskTitle}
              onChange={(e) => setNewTaskTitle(e.target.value)}
              placeholder="Task title…"
              className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-base sm:text-sm text-zinc-100 placeholder-zinc-600 focus:border-violet-500/50 focus:outline-none focus:ring-1 focus:ring-violet-500/30"
            />
            <button
              type="submit"
              disabled={!newTaskTitle.trim() || addingTask}
              className="rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40 transition-colors"
            >
              {addingTask ? "…" : "Add"}
            </button>
            <button
              type="button"
              onClick={() => { setShowAddForm(false); setNewTaskTitle(""); }}
              className="rounded-lg border border-zinc-800 px-3 py-2 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Cancel
            </button>
          </form>
        )}

        {tasks.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <p className="text-sm text-zinc-500">No tasks yet — add one above to start tracking progress.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {tasks.map((task) => (
              <Card key={task.id} className="flex items-start gap-3 py-3">
                <button
                  onClick={() => handleToggleTask(task)}
                  className="mt-0.5 transition-opacity hover:opacity-70"
                  title="Cycle status"
                >
                  {taskStatusIcon(task.status)}
                </button>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium ${task.status === "done" ? "line-through text-zinc-500" : "text-zinc-100"}`}>
                    {task.title}
                  </p>
                  {task.description && (
                    <p className="text-xs text-zinc-600 mt-0.5 truncate">{task.description}</p>
                  )}
                </div>
                {task.due_date && (
                  <span className="text-[10px] font-mono text-zinc-600 flex-shrink-0">{task.due_date}</span>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
