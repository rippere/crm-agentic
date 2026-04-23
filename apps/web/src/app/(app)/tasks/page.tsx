"use client";

import { useState, useEffect, useMemo } from "react";
import {
  DndContext,
  DragEndEvent,
  DragOverEvent,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
  closestCorners,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { createBrowserClient } from "@/lib/supabase";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { apiClient } from "@/lib/api-client";
import { Plus, Brain, Calendar, X, GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";

interface Task {
  id: string;
  title: string;
  description: string | null;
  status: "open" | "in_progress" | "done";
  due_date: string | null;
  contact_id: string | null;
  contact_name?: string;
  clarity_score?: { score: number; rationale?: string } | null;
  message_snippet?: string | null;
}

type TaskStatus = "open" | "in_progress" | "done";

const COLUMNS: { id: TaskStatus; label: string; color: string }[] = [
  { id: "open", label: "Open", color: "text-zinc-400 border-zinc-700" },
  { id: "in_progress", label: "In Progress", color: "text-indigo-400 border-indigo-500/40" },
  { id: "done", label: "Done", color: "text-emerald-400 border-emerald-500/40" },
];

function clarityVariant(score: number): "emerald" | "amber" | "rose" {
  return score >= 70 ? "emerald" : score >= 40 ? "amber" : "rose";
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function TaskCard({
  task,
  onClick,
  dragging = false,
}: {
  task: Task;
  onClick: () => void;
  dragging?: boolean;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "group rounded-xl border border-zinc-800 bg-zinc-900 p-3 space-y-2 cursor-pointer hover:border-zinc-700 transition-all",
        dragging && "shadow-xl border-indigo-500/40"
      )}
      onClick={onClick}
    >
      <div className="flex items-start gap-2">
        <button
          {...attributes}
          {...listeners}
          className="text-zinc-600 hover:text-zinc-400 mt-0.5 flex-shrink-0 cursor-grab active:cursor-grabbing"
          onClick={(e) => e.stopPropagation()}
          aria-label="Drag task"
        >
          <GripVertical className="h-3.5 w-3.5" />
        </button>
        <p className="text-sm font-medium text-zinc-100 flex-1 leading-snug">{task.title}</p>
      </div>

      {task.message_snippet && (
        <p className="text-xs text-zinc-500 line-clamp-2 pl-5">
          {task.message_snippet.slice(0, 80)}{task.message_snippet.length > 80 ? "…" : ""}
        </p>
      )}

      <div className="flex items-center gap-2 flex-wrap pl-5">
        {task.clarity_score && (
          <Badge variant={clarityVariant(task.clarity_score.score)} size="sm">
            <Brain className="h-2.5 w-2.5 mr-1" />
            {task.clarity_score.score}
          </Badge>
        )}
        {task.due_date && (
          <span className="flex items-center gap-1 text-[10px] text-zinc-400 font-mono">
            <Calendar className="h-2.5 w-2.5" />
            {formatDate(task.due_date)}
          </span>
        )}
        {task.contact_name && (
          <span className="text-[10px] text-zinc-500 truncate max-w-[100px]">{task.contact_name}</span>
        )}
      </div>
    </div>
  );
}

function TaskDetailModal({ task, onClose }: { task: Task; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-950 p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-bold text-zinc-100">{task.title}</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 cursor-pointer flex-shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>

        {task.clarity_score && (
          <div className="flex items-center gap-2">
            <Badge variant={clarityVariant(task.clarity_score.score)} size="sm">
              <Brain className="h-2.5 w-2.5 mr-1" />
              Clarity: {task.clarity_score.score}
            </Badge>
            {task.clarity_score.rationale && (
              <p className="text-xs text-zinc-500">{task.clarity_score.rationale}</p>
            )}
          </div>
        )}

        {task.description && (
          <div>
            <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest mb-1">Description</p>
            <p className="text-sm text-zinc-300 leading-relaxed">{task.description}</p>
          </div>
        )}

        {task.message_snippet && (
          <div>
            <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest mb-1">Source Message</p>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-3 max-h-40 overflow-y-auto">
              <pre className="text-xs text-zinc-400 whitespace-pre-wrap font-sans">{task.message_snippet}</pre>
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          {task.due_date && (
            <span className="flex items-center gap-1 text-xs text-zinc-400 font-mono">
              <Calendar className="h-3 w-3" />
              Due {formatDate(task.due_date)}
            </span>
          )}
          {task.contact_name && (
            <span className="text-xs text-zinc-400">{task.contact_name}</span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<TaskStatus | "all">("all");
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [detailTask, setDetailTask] = useState<Task | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [showNewForm, setShowNewForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const isDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

  useEffect(() => {
    if (isDemoMode) {
      // In demo mode, skip auth and load mock data directly
      apiClient.getTasks('demo-workspace-1', 'demo-token')
        .then((data) => setTasks(Array.isArray(data) ? data : []))
        .catch(() => setTasks([]))
        .finally(() => setLoading(false));
      setWorkspaceId('demo-workspace-1');
      setToken('demo-token');
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId(session.user.user_metadata?.workspace_id ?? null);
      }
    });
  }, [isDemoMode]);

  useEffect(() => {
    if (isDemoMode) return; // already loaded above
    if (!workspaceId || !token) return;
    apiClient
      .getTasks(workspaceId, token)
      .then((data) => setTasks(Array.isArray(data) ? data : []))
      .catch(() => setTasks([]))
      .finally(() => setLoading(false));
  }, [workspaceId, token, isDemoMode]);

  const tasksByColumn = useMemo(() => {
    const visible = filter === "all" ? tasks : tasks.filter((t) => t.status === filter);
    return {
      open: visible.filter((t) => t.status === "open"),
      in_progress: visible.filter((t) => t.status === "in_progress"),
      done: visible.filter((t) => t.status === "done"),
    };
  }, [tasks, filter]);

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveTask(null);
    if (!over || !workspaceId || !token) return;

    const taskId = active.id as string;
    const overId = over.id as string;

    // Determine target column
    const targetCol = COLUMNS.find((c) => c.id === overId)?.id
      ?? tasks.find((t) => t.id === overId)?.status;
    if (!targetCol) return;

    const task = tasks.find((t) => t.id === taskId);
    if (!task || task.status === targetCol) return;

    // Optimistic update
    setTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, status: targetCol as TaskStatus } : t));

    try {
      await apiClient.updateTask(workspaceId, taskId, { status: targetCol }, token);
    } catch {
      // Revert on failure
      setTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, status: task.status } : t));
    }
  };

  const handleDragOver = (event: DragOverEvent) => {
    const { active } = event;
    const task = tasks.find((t) => t.id === active.id);
    if (task) setActiveTask(task);
  };

  const handleCreate = async () => {
    if (!newTitle.trim() || !workspaceId || !token) return;
    setCreating(true);
    try {
      const created = await apiClient.createTask(workspaceId, {
        title: newTitle.trim(),
        description: newDesc.trim() || null,
        status: "open",
      }, token);
      setTasks((prev) => [created, ...prev]);
      setNewTitle("");
      setNewDesc("");
      setShowNewForm(false);
    } catch {
      // silently fail — API may not be running
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6">
      <Header title="Tasks" subtitle={`${tasks.length} total tasks`} />

      {/* Filter + New Task */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1">
          {([["all", "All"], ["open", "Open"], ["in_progress", "In Progress"], ["done", "Done"]] as const).map(
            ([val, label]) => (
              <button
                key={val}
                onClick={() => setFilter(val)}
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-xs font-medium transition-all cursor-pointer",
                  filter === val
                    ? "border-indigo-500/40 bg-indigo-600/10 text-indigo-400"
                    : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                )}
              >
                {label}
              </button>
            )
          )}
        </div>
        <Button variant="cta" size="sm" className="ml-auto" onClick={() => setShowNewForm(true)}>
          <Plus className="h-3.5 w-3.5" />
          New Task
        </Button>
      </div>

      {/* New task inline form */}
      {showNewForm && (
        <Card className="space-y-3">
          <input
            type="text"
            placeholder="Task title…"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            autoFocus
            className="w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-indigo-500/50"
          />
          <textarea
            placeholder="Description (optional)…"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            rows={2}
            className="w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-indigo-500/50 resize-none"
          />
          <div className="flex gap-2">
            <Button variant="primary" size="sm" onClick={handleCreate} disabled={creating || !newTitle.trim()}>
              {creating ? "Creating…" : "Create"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setShowNewForm(false)}>Cancel</Button>
          </div>
        </Card>
      )}

      {/* Kanban board */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {COLUMNS.map((col) => (
            <div key={col.id} className="space-y-3">
              <div className="h-6 w-24 rounded bg-zinc-800 animate-pulse" />
              {[1, 2].map((i) => (
                <div key={i} className="h-24 rounded-xl border border-zinc-800 bg-zinc-900 animate-pulse" />
              ))}
            </div>
          ))}
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragEnd={handleDragEnd}
          onDragOver={handleDragOver}
        >
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {COLUMNS.map((col) => {
              const colTasks = tasksByColumn[col.id];
              return (
                <div key={col.id} className="flex flex-col gap-3">
                  <div className={cn("flex items-center gap-2 pb-2 border-b", col.color)}>
                    <h2 className="text-xs font-semibold uppercase tracking-widest font-mono">{col.label}</h2>
                    <Badge variant="zinc" size="sm">{colTasks.length}</Badge>
                  </div>

                  <SortableContext
                    items={colTasks.map((t) => t.id)}
                    strategy={verticalListSortingStrategy}
                    id={col.id}
                  >
                    <div className="flex flex-col gap-2 min-h-[120px]">
                      {colTasks.length === 0 && (
                        <div className="rounded-xl border border-dashed border-zinc-800 py-8 text-center text-xs text-zinc-600">
                          No tasks
                        </div>
                      )}
                      {colTasks.map((task) => (
                        <TaskCard
                          key={task.id}
                          task={task}
                          onClick={() => setDetailTask(task)}
                        />
                      ))}
                    </div>
                  </SortableContext>
                </div>
              );
            })}
          </div>

          <DragOverlay>
            {activeTask && (
              <TaskCard task={activeTask} onClick={() => {}} dragging />
            )}
          </DragOverlay>
        </DndContext>
      )}

      {/* Task detail modal */}
      {detailTask && (
        <TaskDetailModal task={detailTask} onClose={() => setDetailTask(null)} />
      )}
    </div>
  );
}
