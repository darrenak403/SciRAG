"use client";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/app-shell/page-header";
import { Checkbox } from "@/components/ui/checkbox";
import { setAdvancedMode, useAdvancedMode } from "@/lib/advanced";
import { api, messageOf } from "@/lib/api-client";
import type { RagConfig } from "@/lib/types";

const LABELS: [key: string, label: string][] = [
  ["chunk_max_tokens", "Chunk size (tokens)"],
  ["search_candidates", "Candidates per search (dense, BM25)"],
  ["search_fusion", "Fusion"],
  ["rerank_enabled", "Rerank"],
  ["rerank_candidates", "Candidates reranked"],
  ["context_chunks", "Chunks in context"],
  ["context_max_tokens", "Context budget (tokens)"],
  ["multi_paper_max_papers", "Papers per comparison or synthesis"],
  ["multi_paper_chunks", "Chunks per paper"],
  ["multi_paper_parallel_calls", "Parallel evidence calls"],
  ["evidence_min_relevance", "Evidence threshold (0–10)"],
];

function RagSettings() {
  const [config, setConfig] = useState<RagConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<RagConfig>("/settings/rag")
      .then(setConfig)
      .catch((failure: unknown) => setError(messageOf(failure)));
  }, []);

  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="text-base font-medium">Retrieval configuration</h2>
        <p className="text-sm text-muted-foreground">
          What this server runs with. It is set where the server is deployed and can&apos;t be changed here.
        </p>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {config && (
        <dl className="divide-y rounded-lg border text-sm">
          {LABELS.filter(([key]) => key in config).map(([key, label]) => (
            <div key={key} className="flex items-baseline justify-between gap-4 px-3 py-2">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="font-mono tabular-nums">{String(config[key])}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

export default function AdvancedSettingsPage() {
  const advanced = useAdvancedMode();
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Link href="/settings" aria-label="Back to settings" className="text-muted-foreground hover:text-foreground">
              <ChevronLeft className="size-4" />
            </Link>
            Advanced
          </span>
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 p-4 pb-24">
          <section className="flex flex-col gap-3">
            <label className="flex cursor-pointer items-start gap-3">
              <Checkbox className="mt-0.5" checked={advanced} onCheckedChange={(checked) => setAdvancedMode(checked)} />
              <span>
                <span className="block text-sm font-medium">Show technical details</span>
                <span className="block text-sm text-muted-foreground">
                  Adds how each paper was processed and the passages it was split into to the paper page, and how
                  the sources of each answer were found under the answer. Kept in this browser only.
                </span>
              </span>
            </label>
          </section>
          {advanced && <RagSettings />}
        </div>
      </div>
    </div>
  );
}
