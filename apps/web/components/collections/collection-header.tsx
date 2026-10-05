"use client";

import { MoreHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { plural } from "@/lib/format";
import type { AnswerMode, Collection } from "@/lib/types";

// What a collection is for: each one asks for its own kind of answer.
const ACTIONS: { mode: AnswerMode; label: string; hint: string }[] = [
  { mode: "factual", label: "Ask", hint: "A question answered from the passages that fit it best." },
  { mode: "comparison", label: "Compare", hint: "A table with a row for every paper." },
  { mode: "synthesis", label: "Synthesize", hint: "A review across the papers: agreement, disagreement, gaps." },
];

export const PLACEHOLDERS: Record<AnswerMode, string> = {
  factual: "Ask a question about this collection…",
  comparison: "What should the papers be compared on?",
  synthesis: "What should be reviewed across the papers?",
};

/** The name of a collection and the three things to do with it. */
export function CollectionHeader({
  collection,
  ready,
  mode,
  onMode,
  onRename,
  onDelete,
}: {
  collection: Collection;
  // How many of its papers can be asked now.
  ready: number;
  mode: AnswerMode;
  onMode: (mode: AnswerMode) => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-semibold tracking-tight">{collection.name}</h2>
          {collection.description && <p className="text-sm text-muted-foreground">{collection.description}</p>}
          <p className="pt-1 text-sm text-muted-foreground">{plural(collection.paper_ids.length, "paper")}</p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" aria-label="Collection actions" />}>
            <MoreHorizontal />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-40">
            <DropdownMenuItem onClick={onRename}>Rename</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={onDelete}>
              Delete collection
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Kind of answer">
          {ACTIONS.map((action) => (
            <Button
              key={action.mode}
              variant={mode === action.mode ? "default" : "outline"}
              aria-pressed={mode === action.mode}
              // Setting papers side by side takes at least two of them.
              disabled={action.mode !== "factual" && ready < 2}
              onClick={() => onMode(action.mode)}
            >
              {action.label}
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">{ACTIONS.find((action) => action.mode === mode)?.hint}</p>
      </div>
    </div>
  );
}
