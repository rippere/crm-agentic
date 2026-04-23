"use client";

import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { createBrowserClient } from "@/lib/supabase";
import Header from "@/components/layout/Header";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { apiClient } from "@/lib/api-client";
import { Mail, Slack, RefreshCw, Trash2, Link, CheckCircle, Clock, MessageSquare } from "lucide-react";

interface Connector {
  id: string;
  service: string;
  status: string;
  last_sync: string | null;
  message_count: number;
}

interface Toast {
  id: number;
  message: string;
  type: "success" | "error" | "info";
}

const serviceConfig: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  gmail: {
    icon: <Mail className="h-6 w-6" />,
    label: "Gmail",
    color: "text-rose-400 bg-rose-500/10 border-rose-500/20",
  },
  slack: {
    icon: <Slack className="h-6 w-6" />,
    label: "Slack",
    color: "text-purple-400 bg-purple-500/10 border-purple-500/20",
  },
};

const ALL_SERVICES = ["gmail", "slack"];

function formatRelative(dateStr: string | null): string {
  if (!dateStr) return "Never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function ConnectorsPage() {
  const searchParams = useSearchParams();
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [token, setToken] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  const addToast = useCallback((message: string, type: Toast["type"] = "info") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  // Bootstrap auth
  useEffect(() => {
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        setToken(session.access_token);
        setWorkspaceId(session.user.user_metadata?.workspace_id ?? null);
      }
    });
  }, []);

  const fetchConnectors = useCallback(async () => {
    if (!workspaceId || !token) return;
    try {
      const data = await apiClient.getConnectors(workspaceId, token);
      setConnectors(Array.isArray(data) ? data : []);
    } catch {
      // API may not be running — show empty state gracefully
      setConnectors([]);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, token]);

  useEffect(() => {
    if (workspaceId && token) fetchConnectors();
  }, [workspaceId, token, fetchConnectors]);

  // Handle ?connected=gmail redirect from OAuth callback
  useEffect(() => {
    const connected = searchParams.get("connected");
    if (connected === "gmail") {
      addToast("Gmail connected successfully!", "success");
      fetchConnectors();
    }
  }, [searchParams, addToast, fetchConnectors]);

  const handleConnect = async (service: string) => {
    if (!workspaceId || !token) return;
    try {
      if (service === "gmail") {
        const data = await apiClient.getGmailAuthUrl(workspaceId, token);
        window.open(data.auth_url, "_blank");
      } else {
        addToast(`${service} connector coming soon`, "info");
      }
    } catch {
      addToast(`Failed to get auth URL for ${service}`, "error");
    }
  };

  const handleSync = async (service: string) => {
    if (!workspaceId || !token) return;
    setSyncing(service);
    try {
      await apiClient.triggerGmailSync(workspaceId, token);
      addToast("Sync started", "success");
    } catch {
      addToast("Sync failed — check API connection", "error");
    } finally {
      setSyncing(null);
    }
  };

  const handleDisconnect = async (connector: Connector) => {
    if (!workspaceId || !token) return;
    try {
      await apiClient.deleteConnector(workspaceId, connector.id, token);
      addToast(`${connector.service} disconnected`, "info");
      fetchConnectors();
    } catch {
      addToast("Disconnect failed", "error");
    }
  };

  const connectedServices = new Set(connectors.map((c) => c.service));

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
        title="Connectors"
        subtitle="Manage your data source integrations"
      />

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-48 rounded-2xl border border-zinc-800 bg-zinc-900 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ALL_SERVICES.map((service) => {
            const cfg = serviceConfig[service] ?? { icon: <Link className="h-6 w-6" />, label: service, color: "text-zinc-400 bg-zinc-800 border-zinc-700" };
            const connector = connectors.find((c) => c.service === service);
            const isConnected = connectedServices.has(service);

            return (
              <Card key={service} className="flex flex-col gap-4">
                {/* Header */}
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className={`flex h-12 w-12 items-center justify-center rounded-xl border flex-shrink-0 ${cfg.color}`}>
                      {cfg.icon}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-zinc-100">{cfg.label}</p>
                      <p className="text-xs text-zinc-500 font-mono mt-0.5">
                        {service === "gmail" ? "Google Workspace email" : "Team messaging"}
                      </p>
                    </div>
                  </div>
                  <Badge variant={isConnected ? "emerald" : "zinc"} dot={isConnected} pulse={false} size="sm">
                    {isConnected ? "Connected" : "Disconnected"}
                  </Badge>
                </div>

                {/* Stats (if connected) */}
                {isConnected && connector && (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Clock className="h-3 w-3 text-zinc-500" />
                        <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">Last Sync</span>
                      </div>
                      <p className="text-xs font-mono text-zinc-300">{formatRelative(connector.last_sync)}</p>
                    </div>
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
                      <div className="flex items-center gap-1.5 mb-1">
                        <MessageSquare className="h-3 w-3 text-zinc-500" />
                        <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">Messages</span>
                      </div>
                      <p className="text-xs font-mono text-zinc-300">{connector.message_count.toLocaleString()}</p>
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="flex flex-col gap-2 mt-auto">
                  {!isConnected ? (
                    <Button variant="primary" className="w-full justify-center" onClick={() => handleConnect(service)}>
                      <Link className="h-3.5 w-3.5" />
                      Connect {cfg.label}
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="secondary"
                        className="w-full justify-center"
                        onClick={() => handleSync(service)}
                        disabled={syncing === service}
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${syncing === service ? "animate-spin" : ""}`} />
                        {syncing === service ? "Syncing..." : "Sync Now"}
                      </Button>
                      <Button
                        variant="ghost"
                        className="w-full justify-center text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
                        onClick={() => connector && handleDisconnect(connector)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Disconnect
                      </Button>
                    </>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Info card */}
      <Card className="flex items-start gap-3 border-indigo-500/20 bg-indigo-500/5">
        <CheckCircle className="h-4 w-4 text-indigo-400 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-zinc-200">How connectors work</p>
          <p className="text-xs text-zinc-500 mt-1 leading-relaxed">
            Once connected, CRM Agentic automatically ingests messages and extracts tasks using Claude AI.
            Sync runs automatically every hour, or trigger it manually above.
          </p>
        </div>
      </Card>
    </div>
  );
}
