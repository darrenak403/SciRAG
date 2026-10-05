"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { api, messageOf } from "@/lib/api-client";
import type { Retrieval } from "@/lib/types";

// The names the server records things under, in the order they are worth reading.
const LABELS: [key: string, label: string][] = [
  ["mode", "Query type"],
  ["search_query", "Search query"],
  ["outcome", "Outcome"],
  ["papers_in_scope", "Papers in scope"],
  ["papers_searched", "Papers searched"],
  ["papers_considered", "Papers considered"],
  ["candidates", "Candidates"],
  ["rerank", "Rerank"],
  ["evidence", "Passages judged"],
  ["evidence_unjudged", "Passages that could not be judged"],
  ["table", "Table"],
  ["context", "Passages given to the model"],
  ["embedding_model", "Embedding model"],
  ["answer_model", "Answer model"],
  ["retrieved_ms", "Retrieved after (ms)"],
  ["ranked_ms", "Ranked after (ms)"],
  ["first_token_ms", "First token after (ms)"],
  ["total_ms", "Total (ms)"],
];

function shown(value: unknown): string {
  if (Array.isArray(value)) return String(value.length);
  if (value !== null && typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** How the passages behind one answer were found. Only shown in the advanced view. */
export function RetrievalDetails({ messageId }: { messageId: string }) {
  const [loaded, setLoaded] = useState<Retrieval | null>(null);
  const [error, setError] = useState<string | null>(null);

  function changeOpen(open: boolean) {
    if (!open || loaded) return;
    setError(null);
    api<Retrieval>(`/chats/messages/${messageId}/retrieval`)
      .then(setLoaded)
      .catch((failure: unknown) => setError(messageOf(failure)));
  }

  const details = loaded?.retrieval ?? {};
  return (
    <Collapsible onOpenChange={changeOpen} className="text-xs">
      <CollapsibleTrigger className="group flex items-center gap-1 rounded-md text-muted-foreground hover:text-foreground">
        <ChevronRight className="size-3 transition-transform group-data-panel-open:rotate-90" aria-hidden />
        Retrieval details
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 flex flex-col gap-2 rounded-lg border p-3">
        {error && <p className="text-destructive">{error}</p>}
        {!loaded && !error && <p className="text-muted-foreground">Loading…</p>}
        {loaded && (
          <>
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
              {LABELS.filter(([key]) => details[key] != null).map(([key, label]) => (
                <div key={key} className="contents">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="break-words tabular-nums">{shown(details[key])}</dd>
                </div>
              ))}
              {loaded.trace_id && (
                <div className="contents">
                  <dt className="text-muted-foreground">Trace</dt>
                  <dd className="font-mono break-all">{loaded.trace_id}</dd>
                </div>
              )}
            </dl>
            <details>
              <summary className="cursor-pointer text-muted-foreground">Everything recorded</summary>
              <pre className="mt-1 max-h-72 overflow-auto rounded-md bg-muted p-2 font-mono">
                {JSON.stringify(details, null, 2)}
              </pre>
            </details>
          </>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
