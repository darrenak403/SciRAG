"use client";

import { AlertTriangle, Check, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { api, messageOf } from "@/lib/api-client";
import type { IngestionRun } from "@/lib/types";

function seconds(run: IngestionRun): string | null {
  if (!run.finished_at) return null;
  const spent = (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000;
  return `${spent < 10 ? spent.toFixed(1) : Math.round(spent)} s`;
}

/** Every step a paper went through, with what each one recorded. Only shown in the advanced view. */
export function ProcessingDetails({ paperId, status }: { paperId: string; status: string }) {
  const [runs, setRuns] = useState<IngestionRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Again whenever the paper moves on: a step has finished or failed.
  useEffect(() => {
    let cancelled = false;
    api<IngestionRun[]>(`/papers/${paperId}/ingestion`)
      .then((loaded) => {
        if (cancelled) return;
        setRuns(loaded);
        setError(null);
      })
      .catch((failure: unknown) => !cancelled && setError(messageOf(failure)));
    return () => {
      cancelled = true;
    };
  }, [paperId, status]);

  if (error) return <p className="text-sm text-muted-foreground">{error}</p>;
  if (runs === null) return null;
  if (runs.length === 0) return <p className="text-sm text-muted-foreground">Nothing has been recorded yet.</p>;
  return (
    <ol className="flex flex-col gap-2 text-sm">
      {runs.map((run) => (
        <li key={`${run.step}:${run.attempt}:${run.started_at}`} className="flex gap-2">
          {run.status === "done" ? (
            <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-label="Done" />
          ) : run.status === "failed" ? (
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" aria-label="Failed" />
          ) : (
            <Loader2 className="mt-0.5 size-3.5 shrink-0 animate-spin" aria-label="Running" />
          )}
          <div className="min-w-0 flex-1">
            <p className="flex items-baseline justify-between gap-2">
              <span className="font-medium">
                {run.step}
                {run.attempt > 1 && <span className="font-normal text-muted-foreground"> · attempt {run.attempt}</span>}
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">{seconds(run)}</span>
            </p>
            {Object.entries(run.details).map(([key, value]) => (
              <p key={key} className="text-xs break-words text-muted-foreground">
                {key}: {typeof value === "object" ? JSON.stringify(value) : String(value)}
              </p>
            ))}
            {run.error && <p className="text-xs break-words text-warning">{run.error}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
