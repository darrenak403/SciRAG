"use client";

import { AlertTriangle, Check, ChevronDown, Loader2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAskPapers } from "@/components/add-paper/ready-actions";
import { Button } from "@/components/ui/button";
import { plural } from "@/lib/format";
import { displayStatus, isInProgress } from "@/lib/paper-status";
import { dismissFinished, useProcessing } from "@/lib/processing-store";

/** Follows the papers being prepared from any page, in the corner of the screen. */
export function ProcessingWidget() {
  const papers = useProcessing();
  const [collapsed, setCollapsed] = useState(false);
  const { ask, busy } = useAskPapers(dismissFinished);
  if (papers.length === 0) return null;

  const ready = papers.filter((paper) => paper.status === "READY");
  const running = papers.filter(isInProgress);
  const done = running.length === 0;
  const title = done
    ? ready.length === papers.length
      ? `${plural(ready.length, "paper")} ${ready.length === 1 ? "is" : "are"} ready`
      : `${ready.length} of ${plural(papers.length, "paper")} ready`
    : "Preparing papers";

  return (
    <section
      aria-label="Paper processing"
      // Under the page header on a phone: at the bottom it would sit on the question box.
      className="fixed top-14 right-4 z-40 w-80 max-w-[calc(100vw-2rem)] rounded-lg border bg-popover text-popover-foreground shadow-md sm:top-auto sm:bottom-4"
    >
      <header className="flex items-center gap-2 px-3 py-2">
        <p className="flex-1 text-sm font-medium" aria-live="polite">
          {title}
        </p>
        {!done && (
          <span className="text-xs text-muted-foreground tabular-nums">
            {ready.length} / {papers.length} ready
          </span>
        )}
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Show papers" : "Hide papers"}
          aria-expanded={!collapsed}
        >
          <ChevronDown className={collapsed ? "rotate-180" : undefined} />
        </Button>
        {done && (
          <Button variant="ghost" size="icon-xs" onClick={dismissFinished} aria-label="Dismiss">
            <X />
          </Button>
        )}
      </header>

      {!collapsed && (
        <ul className="max-h-48 overflow-y-auto border-t px-3 py-2 text-sm">
          {papers.map((paper) => (
            <li key={paper.id} className="flex items-center gap-2 py-1">
              {paper.status === "READY" ? (
                <Check className="size-3.5 shrink-0 text-success" aria-hidden />
              ) : paper.status === "FAILED" ? (
                <AlertTriangle className="size-3.5 shrink-0 text-warning" aria-hidden />
              ) : (
                <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" aria-hidden />
              )}
              <Link href={`/library/${paper.id}`} className="min-w-0 flex-1 truncate hover:underline">
                {paper.title}
              </Link>
              <span className="shrink-0 text-xs text-muted-foreground">{displayStatus(paper).label}</span>
            </li>
          ))}
        </ul>
      )}

      {done && ready.length > 0 && (
        <footer className="border-t px-3 py-2">
          <Button size="sm" disabled={busy} onClick={() => ask(ready.map((paper) => paper.id))}>
            {ready.length === 1 ? "Ask it" : "Ask them"}
          </Button>
        </footer>
      )}
    </section>
  );
}
