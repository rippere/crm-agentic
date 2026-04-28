"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";
import { cn } from "@/lib/utils";
import {
  PhoneCall, Upload, X, Loader2, Clock, CheckCircle2,
  ChevronRight, Trash2, FileAudio, Mic, ListTodo, AlignLeft,
} from "lucide-react";

interface ActionItem { owner: string; task: string; due: string | null }
interface CallRecord {
  id: string;
  contact_id: string | null;
  title: string;
  duration_seconds: number | null;
  summary: string;
  action_items: ActionItem[];
  participants: string | null;
  call_date: string;
  processing: boolean;
}

function formatDuration(secs: number | null): string {
  if (!secs) return "—";
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function UploadModal({
  onClose,
  onUploaded,
  workspaceId,
  token,
}: {
  onClose: () => void;
  onUploaded: () => void;
  workspaceId: string;
  token: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [participants, setParticipants] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) { setFile(f); setTitle(f.name.replace(/\.[^.]+$/, "")); }
  };

  const handleSubmit = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", title || file.name);
      if (participants) fd.append("participants", participants);
      await apiClient.uploadCall(workspaceId, fd, token);
      onUploaded();
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <Mic className="h-4 w-4 text-indigo-400" />
            <p className="text-sm font-semibold text-zinc-100">Log a Call</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 cursor-pointer"><X className="h-4 w-4" /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* Drop zone */}
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 cursor-pointer transition-colors",
              file ? "border-indigo-500/50 bg-indigo-500/5" : "border-zinc-700 hover:border-zinc-600"
            )}
          >
            <input
              ref={inputRef}
              type="file"
              accept="audio/*,.mp3,.mp4,.m4a,.wav,.ogg,.webm,.flac"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) { setFile(f); setTitle(f.name.replace(/\.[^.]+$/, "")); }
              }}
            />
            {file ? (
              <>
                <FileAudio className="h-8 w-8 text-indigo-400" />
                <p className="text-sm font-medium text-zinc-100">{file.name}</p>
                <p className="text-xs text-zinc-500">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
              </>
            ) : (
              <>
                <Upload className="h-8 w-8 text-zinc-500" />
                <p className="text-sm text-zinc-400">Drop audio file or click to browse</p>
                <p className="text-xs text-zinc-600">MP3, M4A, WAV, OGG, WEBM · max 50 MB</p>
              </>
            )}
          </div>

          {/* Title */}
          <div>
            <label className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">Call Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Q2 Review with TechCorp"
              className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 placeholder-zinc-600 outline-none focus:border-indigo-500/50"
            />
          </div>

          {/* Participants */}
          <div>
            <label className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">Participants (optional)</label>
            <input
              type="text"
              value={participants}
              onChange={(e) => setParticipants(e.target.value)}
              placeholder="e.g. Sarah Chen, Marcus Rivera"
              className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-300 placeholder-zinc-600 outline-none focus:border-indigo-500/50"
            />
          </div>

          {error && <p className="text-xs text-rose-400 font-mono">{error}</p>}

          <Button
            variant="primary"
            className="w-full justify-center"
            onClick={handleSubmit}
            disabled={!file || uploading}
          >
            {uploading ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Uploading…</> : <><Upload className="h-3.5 w-3.5" /> Upload & Transcribe</>}
          </Button>
        </div>
      </div>
    </div>
  );
}

function CallDrawer({ call, onClose }: { call: CallRecord; onClose: () => void }) {
  const [tab, setTab] = useState<"summary" | "transcript">("summary");

  return (
    <aside className="fixed right-0 top-0 h-full w-[440px] border-l border-zinc-800 bg-zinc-950 z-40 overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 border-b border-zinc-800 bg-zinc-950/90 backdrop-blur z-10">
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex items-center gap-2 min-w-0">
            <PhoneCall className="h-4 w-4 text-indigo-400 flex-shrink-0" />
            <p className="text-sm font-semibold text-zinc-100 truncate">{call.title}</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-100 cursor-pointer ml-2 flex-shrink-0">✕</button>
        </div>
        {/* Meta */}
        <div className="flex items-center gap-3 px-5 pb-3 text-xs text-zinc-500">
          <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{formatDuration(call.duration_seconds)}</span>
          {call.participants && <span className="truncate">{call.participants}</span>}
          <span className="ml-auto font-mono">{formatRelative(call.call_date)}</span>
        </div>
        {/* Tabs */}
        <div className="flex border-t border-zinc-800">
          {(["summary", "transcript"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex-1 py-2.5 text-xs font-medium transition-colors cursor-pointer capitalize",
                tab === t ? "border-b-2 border-indigo-500 text-indigo-400" : "text-zinc-500 hover:text-zinc-300"
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="p-5 space-y-5">
        {call.processing ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <Loader2 className="h-8 w-8 text-indigo-400 animate-spin" />
            <p className="text-sm text-zinc-400">Transcribing with Whisper…</p>
            <p className="text-xs text-zinc-600">This may take a minute for longer recordings.</p>
          </div>
        ) : tab === "summary" ? (
          <>
            {/* AI Summary */}
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <AlignLeft className="h-3.5 w-3.5 text-indigo-400" />
                <p className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">Summary</p>
              </div>
              <Card className="text-sm text-zinc-300 leading-relaxed">
                {call.summary || <span className="text-zinc-600 italic">No summary available.</span>}
              </Card>
            </div>

            {/* Action Items */}
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <ListTodo className="h-3.5 w-3.5 text-indigo-400" />
                <p className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">Action Items</p>
                {call.action_items.length > 0 && (
                  <Badge variant="indigo" size="sm">{call.action_items.length}</Badge>
                )}
              </div>
              {call.action_items.length > 0 ? (
                <div className="space-y-2">
                  {call.action_items.map((item, i) => (
                    <div key={i} className="flex items-start gap-3 rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-2.5">
                      <CheckCircle2 className="h-4 w-4 text-indigo-400 flex-shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-zinc-200">{item.task}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          {item.owner && <span className="text-[10px] text-indigo-400 font-mono">{item.owner}</span>}
                          {item.due && <span className="text-[10px] text-zinc-500 font-mono">· due {item.due}</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-zinc-600 italic">No action items extracted.</p>
              )}
            </div>
          </>
        ) : (
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <AlignLeft className="h-3.5 w-3.5 text-zinc-400" />
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-widest font-mono">Full Transcript</p>
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 max-h-[60vh] overflow-y-auto">
              <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">
                {(call as unknown as Record<string, string>).transcript || "Transcript not available."}
              </pre>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

export default function CallsPage() {
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<CallRecord | null>(null);
  const [uploading, setUploading] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
      setToken("demo-token");
      setWorkspaceId("demo-workspace-1");
      return;
    }
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId(session.user.user_metadata?.workspace_id ?? null);
      }
    });
  }, []);

  const fetchCalls = useCallback(async () => {
    if (!workspaceId || !token) { setLoading(false); return; }
    try {
      const data = await apiClient.getCalls(workspaceId, token);
      setCalls(Array.isArray(data) ? data : []);
    } catch {
      setCalls([]);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, token]);

  useEffect(() => {
    if (workspaceId && token) fetchCalls();
  }, [workspaceId, token, fetchCalls]);

  // Poll while any call is processing
  useEffect(() => {
    const hasProcessing = calls.some((c) => c.processing);
    if (hasProcessing) {
      pollRef.current = setInterval(fetchCalls, 5000);
    } else {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [calls, fetchCalls]);

  const handleDelete = async (id: string) => {
    if (!workspaceId || !token) return;
    try {
      await apiClient.deleteCall(workspaceId, id, token);
      setCalls((prev) => prev.filter((c) => c.id !== id));
      if (selected?.id === id) setSelected(null);
    } catch { /* silent */ }
  };

  const processingCount = calls.filter((c) => c.processing).length;

  return (
    <div className="flex flex-col gap-6 p-6">
      <Header
        title="Calls"
        subtitle={`${calls.length} recording${calls.length !== 1 ? "s" : ""} · Whisper + Claude extraction`}
      />

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Total Calls", value: calls.length, color: "text-zinc-100" },
          { label: "Processing", value: processingCount, color: processingCount > 0 ? "text-amber-400" : "text-zinc-100" },
          { label: "Action Items", value: calls.reduce((s, c) => s + c.action_items.length, 0), color: "text-indigo-400" },
          { label: "Hours Recorded", value: `${(calls.reduce((s, c) => s + (c.duration_seconds ?? 0), 0) / 3600).toFixed(1)}h`, color: "text-emerald-400" },
        ].map(({ label, value, color }) => (
          <Card key={label} compact>
            <p className={cn("text-xl font-bold font-mono", color)}>{value}</p>
            <p className="text-xs text-zinc-500 mt-0.5">{label}</p>
          </Card>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {processingCount > 0 && (
            <div className="flex items-center gap-1.5 text-xs text-amber-400 font-mono">
              <Loader2 className="h-3 w-3 animate-spin" />
              {processingCount} transcribing…
            </div>
          )}
        </div>
        <Button variant="cta" size="sm" onClick={() => setUploading(true)} disabled={!workspaceId}>
          <Upload className="h-3.5 w-3.5" />
          Log a Call
        </Button>
      </div>

      {/* Call list */}
      <Card className="overflow-hidden p-0">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 text-indigo-400 animate-spin" />
          </div>
        ) : calls.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <PhoneCall className="h-10 w-10 text-zinc-700" />
            <p className="text-sm text-zinc-500">No calls logged yet.</p>
            <p className="text-xs text-zinc-600">Upload a recording to get an AI transcript + action items.</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {calls.map((call) => (
              <div
                key={call.id}
                className="group flex items-center gap-4 px-4 py-3 hover:bg-zinc-800/40 transition-colors cursor-pointer"
                onClick={() => setSelected(call)}
              >
                {/* Icon */}
                <div className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-xl border flex-shrink-0",
                  call.processing ? "border-amber-500/20 bg-amber-500/10" : "border-indigo-500/20 bg-indigo-500/10"
                )}>
                  {call.processing
                    ? <Loader2 className="h-4 w-4 text-amber-400 animate-spin" />
                    : <PhoneCall className="h-4 w-4 text-indigo-400" />}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-zinc-100 truncate">{call.title}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    {call.participants && (
                      <span className="text-xs text-zinc-500 truncate">{call.participants}</span>
                    )}
                    {call.processing && <Badge variant="amber" size="sm">Transcribing</Badge>}
                  </div>
                </div>

                {/* Duration + action items */}
                <div className="hidden sm:flex items-center gap-4 flex-shrink-0 text-right">
                  <div>
                    <p className="text-xs font-mono text-zinc-400">{formatDuration(call.duration_seconds)}</p>
                    <p className="text-[10px] text-zinc-600">{call.action_items.length} actions</p>
                  </div>
                  <p className="text-xs text-zinc-500 font-mono w-16">{formatRelative(call.call_date)}</p>
                </div>

                {/* Delete */}
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(call.id); }}
                  className="flex-shrink-0 p-1 text-zinc-700 hover:text-rose-400 transition-colors cursor-pointer opacity-0 group-hover:opacity-100"
                  aria-label="Delete call"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>

                <ChevronRight className="h-4 w-4 text-zinc-700 group-hover:text-zinc-400 transition-colors flex-shrink-0" />
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Upload modal */}
      {uploading && workspaceId && token && (
        <UploadModal
          onClose={() => setUploading(false)}
          onUploaded={fetchCalls}
          workspaceId={workspaceId}
          token={token}
        />
      )}

      {/* Detail drawer */}
      {selected && (
        <>
          <div className="fixed inset-0 bg-black/50 z-30" onClick={() => setSelected(null)} />
          <CallDrawer call={selected} onClose={() => setSelected(null)} />
        </>
      )}
    </div>
  );
}
