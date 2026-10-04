"use client";

import { useRef, useState } from "react";

import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

/** "Methodology · Page 6": where in the paper a passage sits. */
export function sourcePlace(source: Pick<Source, "section_path" | "page">): string {
  const section = source.section_path.at(-1);
  return section ? `${section} · Page ${source.page}` : `Page ${source.page}`;
}

/**
 * A source marker in an answer. Hovering shows the passage it stands for;
 * clicking opens that passage in the paper.
 */
export function CitationMarker({
  source,
  active,
  onOpen,
}: {
  source: Source;
  active: boolean;
  onOpen: (source: Source) => void;
}) {
  // Closed on a click: the passage opens beside the answer, and the card would cover the next markers.
  // It stays closed until the pointer has left the marker and come back.
  const [open, setOpen] = useState(false);
  const chosen = useRef(false);
  return (
    <HoverCard open={open} onOpenChange={(next) => setOpen(next && !chosen.current)}>
      <HoverCardTrigger
        render={
          <button
            type="button"
            onClick={() => {
              chosen.current = true;
              setOpen(false);
              onOpen(source);
            }}
            onPointerLeave={() => {
              chosen.current = false;
            }}
            aria-label={`Source ${source.marker.slice(1)}: ${source.paper_title}, page ${source.page}`}
            className={cn(
              "mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md px-1 align-baseline text-xs font-medium tabular-nums transition-colors outline-none focus-visible:ring-2 focus-visible:ring-citation/50",
              active
                ? "bg-citation text-citation-foreground"
                : "bg-citation/10 text-citation hover:bg-citation/20",
            )}
          />
        }
      >
        {source.marker.slice(1)}
      </HoverCardTrigger>
      <HoverCardContent className="flex w-80 flex-col gap-1.5">
        <p className="line-clamp-2 font-medium">{source.paper_title}</p>
        <p className="text-xs text-muted-foreground">{sourcePlace(source)}</p>
        <p className="line-clamp-4 text-xs text-muted-foreground">“{source.snippet}”</p>
        <p className="text-xs font-medium text-citation">View source →</p>
      </HoverCardContent>
    </HoverCard>
  );
}
