"use client";

import { ChevronLeft, Plus, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { useAddPaper } from "@/components/add-paper/add-paper-provider";
import { useAskPapers } from "@/components/add-paper/ready-actions";
import { PageHeader } from "@/components/app-shell/page-header";
import { CollectionFormDialog } from "@/components/collections/collection-dialogs";
import { CollectionHeader, PLACEHOLDERS } from "@/components/collections/collection-header";
import { CollectionPaperList, PickPapersDialog } from "@/components/collections/collection-paper-list";
import { Composer } from "@/components/research/composer";
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
import { api, messageOf } from "@/lib/api-client";
import { refreshCollections } from "@/lib/collections";
import { relativeDay } from "@/lib/format";
import type { AnswerMode, Chat, Collection, Paper, PaperPage } from "@/lib/types";

// The server's largest page. A larger library shows its newest papers in the picker.
const MOST = 100;
const RECENT_SHOWN = 8;

export default function CollectionPage({ params }: PageProps<"/collections/[collectionId]">) {
  const { collectionId } = use(params);
  const router = useRouter();
  const { open: openAddPaper } = useAddPaper();
  const { ask, busy } = useAskPapers();

  const [collection, setCollection] = useState<Collection | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  // The library, for the papers that can still be added.
  const [library, setLibrary] = useState<Paper[]>([]);
  const [recent, setRecent] = useState<Chat[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<AnswerMode>("factual");
  const [question, setQuestion] = useState("");
  const [dialog, setDialog] = useState<"rename" | "delete" | "pick" | null>(null);

  const load = useCallback(async () => {
    try {
      const [loaded, inside, all, chats] = await Promise.all([
        api<Collection>(`/collections/${collectionId}`),
        api<PaperPage>(`/papers?collection_id=${collectionId}&page_size=${MOST}`),
        api<PaperPage>(`/papers?page_size=${MOST}`),
        api<Chat[]>(`/chats?collection_id=${collectionId}&limit=${RECENT_SHOWN}`),
      ]);
      setCollection(loaded);
      setPapers(inside.items);
      setLibrary(all.items);
      setRecent(chats);
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, [collectionId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function remove(paper: Paper) {
    try {
      await api(`/collections/${collectionId}/papers/${paper.id}`, { method: "DELETE" });
      void refreshCollections();
      await load();
    } catch (failure) {
      toast.error(messageOf(failure));
    }
  }

  async function destroy() {
    try {
      await api(`/collections/${collectionId}`, { method: "DELETE" });
      void refreshCollections();
      toast.success("Collection deleted");
      router.push("/collections");
    } catch (failure) {
      toast.error(messageOf(failure));
    }
  }

  if (error) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader title="Collection" />
        <div className="m-auto flex flex-col items-center gap-3 text-center">
          <p className="text-sm text-muted-foreground">{error}</p>
          <Link href="/collections" className="text-sm font-medium underline underline-offset-4">
            Back to collections
          </Link>
        </div>
      </div>
    );
  }
  if (!collection) {
    return (
      <div className="flex h-full flex-col" aria-busy="true">
        <PageHeader title="Collection" />
      </div>
    );
  }

  const held = new Set(collection.paper_ids);
  const ready = papers.filter((paper) => paper.status === "READY" && !paper.needs_reindex).length;
  // Comparing and reviewing need two papers; with fewer the question is a plain one.
  const asked: AnswerMode = ready < 2 ? "factual" : mode;

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Link
              href="/collections"
              aria-label="Back to collections"
              className="text-muted-foreground hover:text-foreground"
            >
              <ChevronLeft className="size-4" />
            </Link>
            <span className="truncate">{collection.name}</span>
          </span>
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-8">
          <CollectionHeader
            collection={collection}
            ready={ready}
            mode={asked}
            onMode={setMode}
            onRename={() => setDialog("rename")}
            onDelete={() => setDialog("delete")}
          />

          {collection.paper_ids.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed px-4 py-10 text-center">
              <p className="text-sm text-muted-foreground">No papers in this collection yet.</p>
              <div className="flex flex-wrap justify-center gap-2">
                <Button onClick={() => setDialog("pick")}>Add papers</Button>
                <Button variant="outline" onClick={openAddPaper}>
                  <Upload /> Upload new papers
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-1.5">
                <Composer
                  value={question}
                  onChange={setQuestion}
                  onSend={() => ask({ collectionId }, question, asked)}
                  disabled={busy || ready === 0}
                  placeholder={PLACEHOLDERS[asked]}
                />
                {ready === 0 && (
                  <p className="text-center text-xs text-muted-foreground">
                    None of these papers is ready to be asked yet.
                  </p>
                )}
              </div>

              <section className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-medium text-muted-foreground">Papers</h3>
                  <Button variant="ghost" size="sm" onClick={() => setDialog("pick")}>
                    <Plus /> Add papers
                  </Button>
                </div>
                <CollectionPaperList papers={papers} onRemove={remove} />
              </section>

              {recent.length > 0 && (
                <section className="flex flex-col gap-2">
                  <h3 className="text-sm font-medium text-muted-foreground">Recent questions</h3>
                  <ul className="divide-y rounded-lg border">
                    {recent.map((chat) => (
                      <li key={chat.id}>
                        <Link
                          href={`/research/${chat.id}`}
                          className="flex items-baseline gap-3 px-3 py-2 text-sm hover:bg-muted"
                        >
                          <span className="min-w-0 flex-1 truncate">{chat.title ?? "Untitled research"}</span>
                          <span className="shrink-0 text-xs text-muted-foreground">{relativeDay(chat.updated_at)}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>
      </div>

      <CollectionFormDialog
        open={dialog === "rename"}
        collection={collection}
        onClose={() => setDialog(null)}
        onSaved={setCollection}
      />
      <PickPapersDialog
        open={dialog === "pick"}
        collectionId={collectionId}
        candidates={library.filter((paper) => !held.has(paper.id))}
        onClose={() => setDialog(null)}
        onAdded={() => void load()}
      />
      <AlertDialog open={dialog === "delete"} onOpenChange={(open) => !open && setDialog(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this collection?</AlertDialogTitle>
            <AlertDialogDescription>
              “{collection.name}” will be removed. Its papers stay in your library.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={destroy}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
