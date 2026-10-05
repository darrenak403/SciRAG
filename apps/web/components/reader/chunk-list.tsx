"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, messageOf } from "@/lib/api-client";
import type { Chunk, ChunkPage } from "@/lib/types";

const PAGE_SIZE = 50;

/** The passages a paper was split into, as they are searched. Choosing one marks it in the PDF. */
export function ChunkList({ paperId, onOpen }: { paperId: string; onOpen: (chunk: Chunk) => void }) {
  const [page, setPage] = useState(1);
  const [loaded, setLoaded] = useState<ChunkPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<ChunkPage>(`/papers/${paperId}/chunks?page=${page}&page_size=${PAGE_SIZE}`)
      .then((result) => !cancelled && setLoaded(result))
      .catch((failure: unknown) => !cancelled && setError(messageOf(failure)));
    return () => {
      cancelled = true;
    };
  }, [paperId, page]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!loaded) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (loaded.total === 0) return <p className="text-sm text-muted-foreground">This paper has no chunks.</p>;

  const pages = Math.ceil(loaded.total / PAGE_SIZE);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">{loaded.total} chunks</p>
      <ul className="flex flex-col gap-1.5">
        {loaded.items.map((chunk) => (
          <li key={chunk.id}>
            <button
              onClick={() => onOpen(chunk)}
              className="flex w-full flex-col gap-1 rounded-lg border p-2 text-left hover:bg-muted"
            >
              <span className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted-foreground tabular-nums">
                <span className="font-medium text-foreground">#{chunk.chunk_index}</span>
                <span>{chunk.kind}</span>
                <span>
                  p. {chunk.page_start}
                  {chunk.page_end !== chunk.page_start && `–${chunk.page_end}`}
                </span>
                <span>{chunk.token_count} tokens</span>
              </span>
              {chunk.section_path.length > 0 && (
                <span className="truncate text-xs text-muted-foreground">{chunk.section_path.join(" › ")}</span>
              )}
              <span className="line-clamp-4 text-xs">{chunk.text}</span>
            </button>
          </li>
        ))}
      </ul>
      {pages > 1 && (
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <Button variant="outline" size="xs" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </Button>
          <span className="tabular-nums">
            {page} / {pages}
          </span>
          <Button variant="outline" size="xs" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
