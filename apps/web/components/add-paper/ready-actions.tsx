"use client";

import { AlertTriangle, Check, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { messageOf } from "@/lib/api-client";
import { plural } from "@/lib/format";
import { isInProgress } from "@/lib/paper-status";
import { type Scope, startResearch } from "@/lib/research";
import type { AskMode, Paper } from "@/lib/types";

/** Opens a research session over these papers, or over a collection. */
export function useAskPapers(onNavigate?: () => void) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function ask(scope: Scope, question?: string, mode?: AskMode) {
    setBusy(true);
    try {
      router.push(await startResearch(scope, question, mode));
      onNavigate?.();
    } catch (error) {
      toast.error(messageOf(error));
    } finally {
      setBusy(false);
    }
  }
  return { ask, busy };
}

/**
 * What to do next with the papers of an upload: the step after "ready" is offered
 * here, so nobody has to go and look for the paper they just added.
 */
export function ReadyActions({
  papers,
  onNavigate,
  onCollect,
}: {
  papers: Paper[];
  onNavigate: () => void;
  // Asks which collection these papers should go into.
  onCollect: (paperIds: string[]) => void;
}) {
  const { ask, busy } = useAskPapers(onNavigate);
  const ready = papers.filter((paper) => paper.status === "READY");
  const running = papers.filter(isInProgress);
  const failed = papers.filter((paper) => paper.status === "FAILED");
  if (papers.length === 0) return null;

  const readyIds = ready.map((paper) => paper.id);
  const single = papers.length === 1;
  const allReady = ready.length === papers.length;

  return (
    <div className="flex flex-col gap-3">
      {!single && (
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span className="inline-flex items-center gap-1.5">
            <Check className="size-3.5 text-success" aria-hidden /> {ready.length} ready
          </span>
          {running.length > 0 && (
            <span className="inline-flex items-center gap-1.5 text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" aria-hidden /> {running.length} processing
            </span>
          )}
          {failed.length > 0 && (
            <span className="inline-flex items-center gap-1.5 text-muted-foreground">
              <AlertTriangle className="size-3.5 text-warning" aria-hidden /> {failed.length} need attention
            </span>
          )}
        </p>
      )}
      {running.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {single ? "Your paper is being prepared." : "Your papers are being prepared."} You can continue using
          ScientRAG. {single ? "It" : "They"} will appear as ready when processing finishes.
        </p>
      )}
      {ready.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => ask(readyIds)} disabled={busy}>
            {single ? "Ask this paper" : allReady ? "Ask all papers" : `Ask ${plural(ready.length, "ready paper")}`}
          </Button>
          {single ? (
            <Link
              href={`/library/${ready[0].id}`}
              onClick={onNavigate}
              className={buttonVariants({ variant: "outline" })}
            >
              Open paper
            </Link>
          ) : (
            <Link href="/library" onClick={onNavigate} className={buttonVariants({ variant: "outline" })}>
              Open library
            </Link>
          )}
          <Button variant="outline" onClick={() => onCollect(readyIds)}>
            {single ? "Add to collection" : "Create collection"}
          </Button>
        </div>
      )}
    </div>
  );
}
