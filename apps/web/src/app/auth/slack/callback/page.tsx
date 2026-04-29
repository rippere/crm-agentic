"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";

const FASTAPI_URL = process.env.NEXT_PUBLIC_FASTAPI_URL || "http://localhost:8000";

function SlackCallbackInner() {
  const searchParams = useSearchParams();

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const error = searchParams.get("error");

    if (error) {
      window.location.href = "/connectors?error=slack_oauth_denied";
      return;
    }

    if (code && state) {
      const params = new URLSearchParams({ code, state });
      window.location.href = `${FASTAPI_URL}/auth/slack/callback?${params.toString()}`;
    }
  }, [searchParams]);

  return (
    <div className="flex h-screen items-center justify-center bg-[#09090B]">
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-indigo-500" />
        <p className="text-sm text-zinc-400">Connecting Slack…</p>
      </div>
    </div>
  );
}

export default function SlackCallbackPage() {
  return (
    <Suspense fallback={
      <div className="flex h-screen items-center justify-center bg-[#09090B]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-indigo-500" />
      </div>
    }>
      <SlackCallbackInner />
    </Suspense>
  );
}
