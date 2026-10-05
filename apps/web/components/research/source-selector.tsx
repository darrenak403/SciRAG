"use client";

import { BookOpen } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { NativeSelect } from "@/components/ui/native-select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { authorLine, plural } from "@/lib/format";
import type { Collection, Paper } from "@/lib/types";

/** The list of papers with a checkbox each, and one for all of them. */
export function SourceChecklist({
  papers,
  selected,
  onChange,
}: {
  papers: Paper[];
  selected: Set<string>;
  onChange: (selected: Set<string>) => void;
}) {
  const all = papers.length > 0 && papers.every((paper) => selected.has(paper.id));

  function toggle(id: string, checked: boolean) {
    const next = new Set(selected);
    if (checked) next.add(id);
    else next.delete(id);
    onChange(next);
  }

  if (papers.length === 0) {
    return <p className="px-1 py-2 text-sm text-muted-foreground">No papers are ready yet.</p>;
  }
  return (
    <ul className="flex flex-col">
      <li>
        <label className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1.5 text-sm font-medium hover:bg-muted">
          <Checkbox
            checked={all}
            indeterminate={!all && selected.size > 0}
            onCheckedChange={(checked) => onChange(new Set(checked ? papers.map((paper) => paper.id) : []))}
          />
          All papers
        </label>
      </li>
      {papers.map((paper) => (
        <li key={paper.id}>
          <label className="flex cursor-pointer items-start gap-2 rounded-md px-1 py-1.5 text-sm hover:bg-muted">
            <Checkbox
              className="mt-0.5"
              checked={selected.has(paper.id)}
              onCheckedChange={(checked) => toggle(paper.id, checked)}
            />
            <span className="min-w-0">
              <span className="line-clamp-2">{paper.title}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {[authorLine(paper.authors), paper.year].filter(Boolean).join(" · ")}
              </span>
            </span>
          </label>
        </li>
      ))}
    </ul>
  );
}

/**
 * Asks a whole collection instead of papers picked one by one. Nothing is shown
 * to an account that has no collection.
 */
export function CollectionSelect({
  collections,
  value,
  onChange,
}: {
  collections: Collection[];
  // null: the papers are picked one by one.
  value: string | null;
  onChange: (collectionId: string | null) => void;
}) {
  if (collections.length === 0) return null;
  return (
    <NativeSelect
      aria-label="Ask a collection"
      className="w-full"
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value || null)}
    >
      <option value="">Papers I choose</option>
      {collections.map((collection) => (
        <option key={collection.id} value={collection.id}>
          {collection.name} ({collection.paper_ids.length})
        </option>
      ))}
    </NativeSelect>
  );
}

/**
 * The button on the composer that says what the next question is asked of — a
 * collection, or so many papers — and opens the list to change that.
 */
export function SourceSelector({
  papers,
  selected,
  onApply,
  collections = [],
  collectionId = null,
  onApplyCollection,
  disabled,
}: {
  papers: Paper[];
  selected: string[];
  onApply: (paperIds: string[]) => void | Promise<void>;
  collections?: Collection[];
  collectionId?: string | null;
  onApplyCollection?: (collectionId: string) => void | Promise<void>;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Set<string>>(new Set());
  const [draftCollection, setDraftCollection] = useState<string | null>(null);
  const inUse = collections.find((collection) => collection.id === collectionId);

  function changeOpen(next: boolean) {
    // The draft starts from what is in use each time the list opens.
    if (next) {
      setDraft(new Set(selected));
      setDraftCollection(collectionId);
    }
    setOpen(next);
  }

  function chooseCollection(id: string | null) {
    setDraftCollection(id);
    const held = collections.find((collection) => collection.id === id);
    if (held) setDraft(new Set(held.paper_ids));
  }

  return (
    <Popover open={open} onOpenChange={changeOpen}>
      <PopoverTrigger render={<Button variant="ghost" size="sm" disabled={disabled} className="max-w-56" />}>
        <BookOpen />
        <span className="truncate">{inUse ? inUse.name : plural(selected.length, "source")}</span>
      </PopoverTrigger>
      <PopoverContent align="start" side="top" className="flex w-80 flex-col gap-2">
        <p className="text-sm font-medium">Sources</p>
        {onApplyCollection && (
          <CollectionSelect collections={collections} value={draftCollection} onChange={chooseCollection} />
        )}
        <div className="max-h-64 overflow-y-auto">
          <SourceChecklist
            papers={papers}
            selected={draft}
            onChange={(next) => {
              // Picking papers by hand leaves the collection.
              setDraft(next);
              setDraftCollection(null);
            }}
          />
        </div>
        <Button
          size="sm"
          onClick={async () => {
            if (draftCollection && onApplyCollection) await onApplyCollection(draftCollection);
            // From the set, not the list: a paper in use that is not listed here stays in use.
            else await onApply([...draft]);
            setOpen(false);
          }}
        >
          Apply
        </Button>
      </PopoverContent>
    </Popover>
  );
}
