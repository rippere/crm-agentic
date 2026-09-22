"use client";

import Header from "@/components/layout/Header";
import ChatPanel from "@/components/chat/ChatPanel";

// Autonomous Lead Engine — operator chat surface (Increment 1, R15).
// The operator drives discovery by prompt ("find leads in Burlington, begin GTM");
// the panel dispatches the clamped discovery action (fail-closed — needs a Confirm),
// polls the run via the shared job poller, and reports venues loaded to /leads.
export default function AssistantPage() {
  return (
    <div className="flex flex-col min-h-screen p-4 md:p-6 gap-4">
      <Header title="Assistant" subtitle="Nova — your autonomous lead engine" />
      <div className="flex flex-1 min-h-[560px] flex-col">
        <ChatPanel />
      </div>
    </div>
  );
}
