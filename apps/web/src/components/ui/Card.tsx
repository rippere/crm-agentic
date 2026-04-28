"use client";

import { cn } from "@/lib/utils";

type AccentColor = "violet" | "signal" | "amber" | "rose" | "emerald";

const accentClasses: Record<AccentColor, string> = {
  violet:  "border-l-2 border-l-indigo-500",
  signal:  "border-l-2 border-l-[#00C896]",
  amber:   "border-l-2 border-l-amber-400",
  rose:    "border-l-2 border-l-rose-500",
  emerald: "border-l-2 border-l-emerald-500",
};

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: boolean;
  /** Colored 2px left border — carries semantic meaning (delta direction, stage, status) */
  accent?: AccentColor;
  /** Tighter padding for dense data layouts */
  compact?: boolean;
}

export default function Card({
  children,
  className,
  hover = false,
  glow = false,
  accent,
  compact = false,
  ...props
}: CardProps) {
  return (
    <div
      {...props}
      className={cn(
        "rounded-xl border border-zinc-800/80 bg-zinc-900",
        compact ? "p-3" : "p-4",
        accent && accentClasses[accent],
        hover && "cursor-pointer transition-all duration-200 hover:border-zinc-700/80 hover:bg-zinc-900/90",
        glow && "hover:shadow-[0_0_12px_rgba(99,102,241,0.15)] hover:border-indigo-500/25",
        className
      )}
    >
      {children}
    </div>
  );
}
