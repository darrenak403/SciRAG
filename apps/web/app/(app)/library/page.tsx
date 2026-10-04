"use client";

import { Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { useAddPaper } from "@/components/add-paper/add-paper-provider";
import { useAskPapers } from "@/components/add-paper/ready-actions";
import { PageHeader } from "@/components/app-shell/page-header";
import {
  EMPTY_QUERY,
  type LibraryQuery,
  LibraryToolbar,
  SORTS,
  STATUS_FILTERS,
} from "@/components/library/library-toolbar";
import { MetadataDialog } from "@/components/library/metadata-form";
import { retryProcessing } from "@/components/library/paper-failure";
import { type PaperAction, PaperTable } from "@/components/library/paper-table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, messageOf } from "@/lib/api-client";
import { plural } from "@/lib/format";
import { forget, useProcessing } from "@/lib/processing-store";
import type { Paper, PaperPage } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;
const TYPING_PAUSE_MS = 300;

function searchOf(query: LibraryQuery, page: number): string {
  const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (query.q.trim()) params.set("q", query.q.trim());
  if (query.author.trim()) params.set("author", query.author.trim());
  if (/^\d{4}$/.test(query.year)) params.set("year", query.year);
  for (const status of STATUS_FILTERS[query.status].statuses) params.append("status", status);
  params.set("sort", SORTS[query.sort].sort);
  params.set("order", SORTS[query.sort].order);
  return params.toString();
}

export default function LibraryPage() {
  const { open: openAddPaper } = useAddPaper();
  const { ask } = useAskPapers();
  const processing = useProcessing();

  const [query, setQuery] = useState(EMPTY_QUERY);
  const [page, setPage] = useState(1);
  // What the server is asked for: the query once typing has paused.
  const [search, setSearch] = useState(() => searchOf(EMPTY_QUERY, 1));
  const [result, setResult] = useState<PaperPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Paper | null>(null);
  const [deleting, setDeleting] = useState<Paper | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchOf(query, page)), TYPING_PAUSE_MS);
    return () => clearTimeout(timer);
  }, [query, page]);

  const latest = useRef(0);
  const load = useCallback(async () => {
    const request = ++latest.current;
    try {
      const loaded = await api<PaperPage>(`/papers?${search}`);
      // An answer to an older search must not replace a newer one.
      if (request === latest.current) {
        setResult(loaded);
        setError(null);
      }
    } catch (failure) {
      if (request === latest.current) setError(messageOf(failure));
    }
  }, [search]);

  // Again whenever a paper is added, finishes or fails, so the list never shows a stale row.
  const settled = processing.map((paper) => `${paper.id}:${paper.status}`).join(",");
  useEffect(() => {
    void load();
  }, [load, settled]);

  function change(changes: Partial<LibraryQuery>) {
    setQuery((current) => ({ ...current, ...changes }));
    setPage(1);
  }

  const onAction = useCallback(
    (action: PaperAction, paper: Paper) => {
      if (action === "ask") void ask([paper.id]);
      else if (action === "edit") setEditing(paper);
      else if (action === "delete") setDeleting(paper);
      else void retryProcessing(paper.id);
    },
    [ask],
  );

  async function remove() {
    if (!deleting) return;
    try {
      await api(`/papers/${deleting.id}`, { method: "DELETE" });
      forget(deleting.id);
      toast.success("Paper deleted");
      setDeleting(null);
      await load();
    } catch (failure) {
      toast.error(messageOf(failure));
    }
  }

  // The store knows the step a paper is at more recently than the page that was loaded.
  const live = new Map(processing.map((paper) => [paper.id, paper]));
  const papers = result?.items.map((paper) => live.get(paper.id) ?? paper) ?? [];
  const pages = result ? Math.max(1, Math.ceil(result.total / PAGE_SIZE)) : 1;
  const filtered = search !== searchOf(EMPTY_QUERY, 1);

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Library">
        <Button size="sm" onClick={openAddPaper}>
          <Plus /> Add papers
        </Button>
      </PageHeader>

      {/* Room under the list while papers are prepared: the widget in the corner would cover the pager. */}
      <div className={cn("flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4", processing.length > 0 && "sm:pb-80")}>
        {result && result.total === 0 && !filtered ? (
          <div className="m-auto flex max-w-sm flex-col items-center gap-3 text-center">
            <h2 className="text-base font-medium">Your research library is empty</h2>
            <p className="text-sm text-muted-foreground">
              Add papers to start asking questions and comparing research.
            </p>
            <Button onClick={openAddPaper}>Add papers</Button>
          </div>
        ) : (
          <>
            <LibraryToolbar query={query} onChange={change} />
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}{" "}
                <button className="underline underline-offset-4" onClick={load}>
                  Try again
                </button>
              </p>
            )}
            {!result && !error && (
              <div className="flex flex-col gap-2" aria-busy="true">
                {Array.from({ length: 6 }, (_, index) => (
                  <Skeleton key={index} className="h-9" />
                ))}
              </div>
            )}
            {result && result.total === 0 && (
              <p className="py-12 text-center text-sm text-muted-foreground">No papers match your search.</p>
            )}
            {result && result.total > 0 && (
              <>
                <PaperTable papers={papers} onAction={onAction} />
                <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
                  <span>{plural(result.total, "paper")}</span>
                  {pages > 1 && (
                    <div className="flex items-center gap-2">
                      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                        Previous
                      </Button>
                      <span className="tabular-nums">
                        Page {page} of {pages}
                      </span>
                      <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                        Next
                      </Button>
                    </div>
                  )}
                </div>
              </>
            )}
          </>
        )}
      </div>

      <MetadataDialog paper={editing} onClose={() => setEditing(null)} onSaved={() => void load()} />

      <AlertDialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this paper?</AlertDialogTitle>
            <AlertDialogDescription>
              “{deleting?.title}” and its file will be removed from your library. This can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={remove}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
