"use client";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { PdfViewer } from "@/components/reader/pdf-viewer-lazy";
import { sourcePlace } from "@/components/research/citation-marker";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import type { Passage, Source } from "@/lib/types";

function EvidenceCard({ source, onOpen }: { source: Source; onOpen: () => void }) {
  return (
    <li className="flex flex-col gap-1.5 rounded-lg border p-3">
      <div className="flex items-start gap-2">
        <span className="inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-md bg-citation/10 px-1 text-xs font-medium text-citation tabular-nums">
          {source.marker.slice(1)}
        </span>
        <div className="min-w-0">
          <p className="line-clamp-2 text-sm font-medium">{source.paper_title}</p>
          <p className="text-xs text-muted-foreground">{sourcePlace(source)}</p>
        </div>
      </div>
      <p className="line-clamp-5 text-sm text-muted-foreground">“{source.snippet}”</p>
      <Button variant="outline" size="sm" className="self-start" onClick={onOpen}>
        Open in PDF
      </Button>
    </li>
  );
}

/** The passage in its paper: the right page, with the passage marked. */
function EvidencePdf({ source, onBack }: { source: Source; onBack: () => void }) {
  // Where a passage sits, once known. "missing" when it can no longer be found.
  const [found, setFound] = useState<{ chunk: string; passage: Passage | "missing" } | null>(null);
  // What was found for an earlier marker says nothing about this one.
  const passage = found?.chunk === source.chunk_id ? found.passage : null;

  useEffect(() => {
    let cancelled = false;
    const chunk = source.chunk_id;
    api<Passage>(`/chunks/${chunk}`)
      .then((passage) => !cancelled && setFound({ chunk, passage }))
      .catch(() => !cancelled && setFound({ chunk, passage: "missing" }));
    return () => {
      cancelled = true;
    };
  }, [source.chunk_id]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-start gap-1 border-b p-2">
        <Button variant="ghost" size="icon-sm" onClick={onBack} aria-label="Back to sources">
          <ChevronLeft />
        </Button>
        <div className="min-w-0 flex-1">
          <Link
            href={`/library/${source.paper_id}`}
            className="line-clamp-1 text-sm font-medium hover:underline"
            title="Open paper"
          >
            {source.paper_title}
          </Link>
          <p className="text-xs text-muted-foreground">{sourcePlace(source)}</p>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        {passage === "missing" ? (
          <div className="flex flex-col gap-2 p-4 text-sm">
            <p className="text-muted-foreground">
              This passage can&apos;t be shown in the paper any more. The paper may have been removed or prepared
              again since the answer was written.
            </p>
            <p>“{source.snippet}”</p>
          </div>
        ) : (
          // Shown at the cited page right away; the marks follow when the passage has loaded.
          <PdfViewer
            paperId={source.paper_id}
            target={
              passage
                ? { page: passage.page_start, boxes: passage.bboxes, key: passage.id }
                : { page: source.page, key: `${source.chunk_id}:page` }
            }
          />
        )}
      </div>
    </div>
  );
}

/**
 * What an answer rests on. Two views: the cited passages as cards, and one passage
 * in its PDF. Choosing a marker in the answer goes straight to the second.
 */
export function EvidencePanel({
  sources,
  active,
  onOpen,
  onBack,
}: {
  sources: Source[];
  active: Source | null;
  onOpen: (source: Source) => void;
  onBack: () => void;
}) {
  // Keyed by paper: another passage of the same paper moves the view, without loading the PDF again.
  if (active) return <EvidencePdf key={active.paper_id} source={active} onBack={onBack} />;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <h2 className="shrink-0 border-b px-3 py-2.5 text-sm font-medium">Evidence</h2>
      {sources.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">
          The passages an answer is based on appear here. Choose a source marker in an answer to see it in the
          paper.
        </p>
      ) : (
        <ul className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3">
          {sources.map((source) => (
            <EvidenceCard key={source.chunk_id} source={source} onOpen={() => onOpen(source)} />
          ))}
        </ul>
      )}
    </div>
  );
}
