"use client";

import { Plus } from "lucide-react";

import { useAddPaper } from "@/components/add-paper/add-paper-provider";
import { CollectionSelect, SourceChecklist } from "@/components/research/source-selector";
import { Button } from "@/components/ui/button";
import { plural } from "@/lib/format";
import type { Collection, Paper } from "@/lib/types";

/** The papers this session draws on. Ticking one changes what the next question is asked of. */
export function SourcePanel({
  papers,
  selected,
  onChange,
  collections,
  collectionId,
  onCollection,
}: {
  papers: Paper[];
  selected: string[];
  onChange: (paperIds: string[]) => void;
  collections: Collection[];
  // The collection the session asks, when it asks one.
  collectionId: string | null;
  onCollection: (collectionId: string) => void;
}) {
  const { open: openAddPaper } = useAddPaper();
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-baseline justify-between border-b px-3 py-2.5">
        <h2 className="text-sm font-medium">Sources</h2>
        <span className="text-xs text-muted-foreground">{plural(selected.length, "paper")} in use</span>
      </div>
      {collections.length > 0 && (
        <div className="shrink-0 px-2 pt-2">
          <CollectionSelect
            collections={collections}
            value={collectionId}
            // Back to "papers I choose": the same papers, now named one by one.
            onChange={(id) => (id ? onCollection(id) : onChange(selected))}
          />
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        <SourceChecklist
          papers={papers}
          selected={new Set(selected)}
          // From the set, not the list: a paper in use that is not listed here stays in use.
          onChange={(next) => onChange([...next])}
        />
      </div>
      <div className="shrink-0 border-t p-2">
        <Button variant="ghost" size="sm" className="w-full justify-start" onClick={openAddPaper}>
          <Plus /> Add papers
        </Button>
      </div>
    </div>
  );
}
