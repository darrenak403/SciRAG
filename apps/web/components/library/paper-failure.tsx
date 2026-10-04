"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { api, messageOf } from "@/lib/api-client";
import { failureOf } from "@/lib/paper-status";
import { track } from "@/lib/processing-store";
import type { Paper } from "@/lib/types";

/** Sends a paper through processing again and starts watching it. */
export async function retryProcessing(paperId: string): Promise<Paper | null> {
  try {
    const paper = await api<Paper>(`/papers/${paperId}/reingest`, { method: "POST" });
    track(paper);
    return paper;
  } catch (error) {
    toast.error(messageOf(error));
    return null;
  }
}

/**
 * Why a paper could not be prepared and the way out of it. Every failure has an action:
 * try again, use another file, or fix the model connection.
 */
export function PaperFailure({
  paper,
  onReplace,
  onRetried,
}: {
  paper: Pick<Paper, "id" | "error_code" | "error" | "original_filename">;
  // Opens the file picker; left out where there is nowhere to pick a file from.
  onReplace?: () => void;
  onRetried?: (paper: Paper) => void;
}) {
  const failure = failureOf(paper);
  const [details, setDetails] = useState(false);
  const [busy, setBusy] = useState(false);

  async function retry() {
    setBusy(true);
    const retried = await retryProcessing(paper.id);
    setBusy(false);
    if (retried) onRetried?.(retried);
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div>
        <p className="font-medium">{failure.title}</p>
        <p className="text-muted-foreground">{failure.hint}</p>
      </div>
      {details && (
        <p className="rounded-md bg-muted px-2 py-1.5 text-xs text-muted-foreground">
          {paper.original_filename}
          {paper.error ? ` — ${paper.error}` : ""}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {failure.recovery === "retry" && (
          <Button size="sm" variant="outline" onClick={retry} disabled={busy}>
            {busy ? "Retrying…" : "Retry processing"}
          </Button>
        )}
        {failure.recovery === "replace" && onReplace && (
          <Button size="sm" variant="outline" onClick={onReplace}>
            Try another file
          </Button>
        )}
        {failure.recovery === "settings" && (
          <>
            <Link href="/settings" className={buttonVariants({ size: "sm", variant: "outline" })}>
              Open settings
            </Link>
            <Button size="sm" variant="ghost" onClick={retry} disabled={busy}>
              {busy ? "Retrying…" : "Retry processing"}
            </Button>
          </>
        )}
        <Button size="sm" variant="ghost" onClick={() => setDetails((shown) => !shown)}>
          {details ? "Hide details" : "View details"}
        </Button>
      </div>
    </div>
  );
}
