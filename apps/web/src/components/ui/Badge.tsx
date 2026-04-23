"use client";

import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "indigo" | "emerald" | "amber" | "rose" | "zinc";
  size?: "sm" | "md";
  dot?: boolean;
  pulse?: boolean;
  className?: string;
}

const variantClasses = {
  indigo: "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20",
  emerald: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  amber: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  rose: "bg-rose-500/10 text-rose-400 border border-rose-500/20",
  zinc: "bg-zinc-700/50 text-zinc-400 border border-zinc-700",
};

const dotColors = {
  indigo: "bg-indigo-400",
  emerald: "bg-emerald-400",
  amber: "bg-amber-400",
  rose: "bg-rose-400",
  zinc: "bg-zinc-400",
};

export default function Badge({
  children,
  variant = "indigo",
  size = "sm",
  dot = false,
  pulse = false,
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-mono font-medium",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm",
        variantClasses[variant],
        className
      )}
    >
      {dot && (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full flex-shrink-0",
            dotColors[variant],
            pulse && "agent-pulse"
          )}
        />
      )}
      {children}
    </span>
  );
}
