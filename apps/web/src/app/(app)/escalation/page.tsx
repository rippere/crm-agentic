"use client";

import Header from "@/components/layout/Header";
import EscalationPanel from "@/components/escalation/EscalationPanel";

// Autonomous Lead Engine — operator control-plane (Increment 2, R15).
// Per-stage auto/ask/off caps + the autonomy master switch (fail-closed off, R12),
// the escalation queue (waiting enrollments the graph flagged), and the post-call
// outcome form (a human outcome re-enters the event-sourced graph).
export default function EscalationPage() {
  return (
    <div className="flex flex-col min-h-screen p-4 md:p-6 gap-4">
      <Header title="Escalation" subtitle="Operator control-plane for the autonomous lead engine" />
      <EscalationPanel />
    </div>
  );
}
