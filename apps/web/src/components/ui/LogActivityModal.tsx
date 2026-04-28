"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { X, ClipboardList, Phone, Mail, Users, Calendar } from "lucide-react";
import Button from "@/components/ui/Button";

type ActivityType = "note" | "call" | "email" | "meeting";

interface LogActivityModalProps {
  contactName?: string;
  dealTitle?: string;
  onClose: () => void;
  onSubmit: (activity: { type: ActivityType; note: string }) => void;
}

const ACTIVITY_TYPES: { type: ActivityType; icon: React.ReactNode; label: string }[] = [
  { type: "note",    icon: <ClipboardList className="h-3.5 w-3.5" />, label: "Note"    },
  { type: "call",    icon: <Phone         className="h-3.5 w-3.5" />, label: "Call"    },
  { type: "email",   icon: <Mail          className="h-3.5 w-3.5" />, label: "Email"   },
  { type: "meeting", icon: <Users         className="h-3.5 w-3.5" />, label: "Meeting" },
];

const placeholders: Record<ActivityType, string> = {
  note:    "Add a note…",
  call:    "What was discussed on the call?",
  email:   "What was the email about?",
  meeting: "What was covered in the meeting?",
};

export default function LogActivityModal({
  contactName,
  dealTitle,
  onClose,
  onSubmit,
}: LogActivityModalProps) {
  const [type, setType] = useState<ActivityType>("note");
  const [note, setNote] = useState("");

  const handleSubmit = () => {
    if (!note.trim()) return;
    onSubmit({ type, note: note.trim() });
    onClose();
  };

  const today = new Date().toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <div>
            <p className="text-sm font-semibold text-zinc-100">Log Activity</p>
            {(contactName || dealTitle) && (
              <p className="text-[11px] text-zinc-500 mt-0.5 font-mono">
                {contactName ?? dealTitle}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Type selector */}
          <div className="flex gap-2">
            {ACTIVITY_TYPES.map(({ type: t, icon, label }) => (
              <button
                key={t}
                onClick={() => setType(t)}
                className={cn(
                  "flex-1 flex items-center justify-center gap-1.5 rounded-xl border py-2 text-xs font-medium transition-all cursor-pointer",
                  type === t
                    ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-400"
                    : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
                )}
              >
                <span>{icon}</span>
                {label}
              </button>
            ))}
          </div>

          {/* Note textarea */}
          <textarea
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit();
            }}
            placeholder={placeholders[type]}
            rows={4}
            className="w-full resize-none rounded-xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-indigo-500/50 transition-colors leading-relaxed"
          />

          {/* Date hint */}
          <div className="flex items-center gap-2 text-[11px] text-zinc-600 font-mono">
            <Calendar className="h-3.5 w-3.5" />
            Logged as {today}
          </div>

          {/* Actions */}
          <div className="flex gap-2">
            <Button variant="secondary" className="flex-1 justify-center" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              className="flex-1 justify-center"
              onClick={handleSubmit}
              disabled={!note.trim()}
            >
              Log Activity
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
