"use client";

import { BookOpen } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { authorLine, plural } from "@/lib/format";
import type { Paper } from "@/lib/types";

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
 * The button on the composer that says how many papers the next question is asked of,
 * and opens the list to change that.
 */
export function SourceSelector({
  papers,
  selected,
  onApply,
  disabled,
}: {
  papers: Paper[];
  selected: string[];
  onApply: (paperIds: string[]) => void | Promise<void>;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Set<string>>(new Set());

  function changeOpen(next: boolean) {
    // The draft starts from what is in use each time the list opens.
    if (next) setDraft(new Set(selected));
    setOpen(next);
  }

  return (
    <Popover open={open} onOpenChange={changeOpen}>
      <PopoverTrigger render={<Button variant="ghost" size="sm" disabled={disabled} />}>
        <BookOpen />
        {plural(selected.length, "source")}
      </PopoverTrigger>
      <PopoverContent align="start" side="top" className="flex w-80 flex-col gap-2">
        <p className="text-sm font-medium">Sources</p>
        <div className="max-h-64 overflow-y-auto">
          <SourceChecklist papers={papers} selected={draft} onChange={setDraft} />
        </div>
        <Button
          size="sm"
          onClick={async () => {
            // From the set, not the list: a paper in use that is not listed here stays in use.
            await onApply([...draft]);
            setOpen(false);
          }}
        >
          Apply
        </Button>
      </PopoverContent>
    </Popover>
  );
}
