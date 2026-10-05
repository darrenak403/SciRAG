"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { PaperStatusBadge } from "@/components/library/paper-status-badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { messageOf } from "@/lib/api-client";
import { addToCollection } from "@/lib/collections";
import { authorLine, plural } from "@/lib/format";
import type { Paper } from "@/lib/types";

function byline(paper: Paper): string {
  return [authorLine(paper.authors), paper.year].filter(Boolean).join(" · ");
}

/** The papers of a collection, each with a way to take it out again. */
export function CollectionPaperList({ papers, onRemove }: { papers: Paper[]; onRemove: (paper: Paper) => void }) {
  return (
    <ul className="divide-y rounded-lg border">
      {papers.map((paper) => (
        <li key={paper.id} className="flex items-center gap-3 px-3 py-2">
          <div className="min-w-0 flex-1">
            <Link href={`/library/${paper.id}`} className="line-clamp-1 text-sm font-medium hover:underline">
              {paper.title}
            </Link>
            <p className="truncate text-xs text-muted-foreground">{byline(paper)}</p>
          </div>
          {paper.status !== "READY" && <PaperStatusBadge paper={paper} className="text-xs text-muted-foreground" />}
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => onRemove(paper)}
            aria-label={`Remove ${paper.title} from this collection`}
          >
            <X />
          </Button>
        </li>
      ))}
    </ul>
  );
}

/** Picks papers of the library that the collection does not hold yet. */
export function PickPapersDialog({
  open,
  collectionId,
  candidates,
  onClose,
  onAdded,
}: {
  open: boolean;
  collectionId: string;
  // The library's papers that are not in the collection.
  candidates: Paper[];
  onClose: () => void;
  onAdded: () => void;
}) {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  function toggle(id: string, checked: boolean) {
    const next = new Set(picked);
    if (checked) next.add(id);
    else next.delete(id);
    setPicked(next);
  }

  async function add() {
    setBusy(true);
    try {
      await addToCollection(collectionId, [...picked]);
      setPicked(new Set());
      onAdded();
      onClose();
    } catch (error) {
      toast.error(messageOf(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add papers from your library</DialogTitle>
          <DialogDescription>Papers stay in your library; the collection only groups them.</DialogDescription>
        </DialogHeader>
        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">Every paper in your library is already in this collection.</p>
        ) : (
          <ul className="flex min-h-0 flex-col overflow-y-auto">
            {candidates.map((paper) => (
              <li key={paper.id}>
                <label className="flex cursor-pointer items-start gap-2 rounded-md px-1 py-1.5 text-sm hover:bg-muted">
                  <Checkbox
                    className="mt-0.5"
                    checked={picked.has(paper.id)}
                    onCheckedChange={(checked) => toggle(paper.id, checked)}
                  />
                  <span className="min-w-0">
                    <span className="line-clamp-2">{paper.title}</span>
                    <span className="block truncate text-xs text-muted-foreground">{byline(paper)}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={add} disabled={busy || picked.size === 0}>
            {picked.size === 0 ? "Add papers" : `Add ${plural(picked.size, "paper")}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
