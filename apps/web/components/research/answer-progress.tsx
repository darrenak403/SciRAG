import { Check, Circle, Loader2 } from "lucide-react";

import type { Progress } from "@/lib/chat-runtime";
import { cn } from "@/lib/utils";

const STAGES: Record<"comparison" | "synthesis", [stage: string, label: string][]> = {
  synthesis: [
    ["selecting", "Selecting relevant papers"],
    ["gathering", "Gathering evidence"],
    ["comparing", "Comparing findings"],
    ["writing", "Synthesizing answer"],
  ],
  comparison: [
    ["selecting", "Selecting relevant papers"],
    ["gathering", "Gathering evidence"],
    ["comparing", "Building the comparison"],
    // Reached only when the table could not be built and the comparison is written out instead.
    ["writing", "Writing the comparison"],
  ],
};

/** The steps of an answer that takes a while: which are done, which is under way. */
export function AnswerProgress({ progress }: { progress: Progress }) {
  const all = STAGES[progress.mode === "comparison" ? "comparison" : "synthesis"];
  const stages = progress.mode === "comparison" && progress.stage !== "writing" ? all.slice(0, 3) : all;
  const current = stages.findIndex(([stage]) => stage === progress.stage);
  return (
    <ol className="flex flex-col gap-1.5 text-sm" aria-label="Progress of the answer">
      {stages.map(([stage, label], index) => (
        <li
          key={stage}
          aria-current={index === current ? "step" : undefined}
          className={cn("flex items-center gap-2", index === current ? "text-foreground" : "text-muted-foreground")}
        >
          {index < current ? (
            <Check className="size-3.5 text-success" aria-hidden />
          ) : index === current ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <Circle className="size-3.5" aria-hidden />
          )}
          {label}
          {index === current && progress.total != null && (
            <span className="text-xs text-muted-foreground tabular-nums">
              {progress.done ?? 0} / {progress.total}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
