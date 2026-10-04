import { AlertTriangle, Check, Circle, Loader2 } from "lucide-react";

import { displayStatus, type Tone } from "@/lib/paper-status";
import type { Paper } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONES: Record<Tone, { icon: typeof Check; className: string; spin?: boolean }> = {
  neutral: { icon: Circle, className: "text-muted-foreground" },
  progress: { icon: Loader2, className: "text-muted-foreground", spin: true },
  success: { icon: Check, className: "text-success" },
  warning: { icon: AlertTriangle, className: "text-warning" },
};

export function PaperStatusBadge({
  paper,
  className,
}: {
  paper: Pick<Paper, "status" | "processing_step" | "warnings">;
  className?: string;
}) {
  const { label, tone } = displayStatus(paper);
  const { icon: Icon, className: toneClass, spin } = TONES[tone];
  const withNote = paper.status === "READY" && paper.warnings.length > 0;
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 text-sm whitespace-nowrap", className)}
      title={withNote ? paper.warnings.join(" ") : undefined}
    >
      <Icon className={cn("size-3.5 shrink-0", toneClass, spin && "animate-spin")} aria-hidden />
      {label}
      {withNote && <AlertTriangle className="size-3.5 text-warning" aria-label="Ready, with notes" />}
    </span>
  );
}
