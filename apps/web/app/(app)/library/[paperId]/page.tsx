"use client";

import { ChevronLeft, Info, Loader2, Pencil } from "lucide-react";
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";

import { useAddPaper } from "@/components/add-paper/add-paper-provider";
import { useAskPapers } from "@/components/add-paper/ready-actions";
import { PageHeader } from "@/components/app-shell/page-header";
import { AddToCollectionDialog } from "@/components/collections/collection-dialogs";
import { MetadataDialog } from "@/components/library/metadata-form";
import { PaperFailure } from "@/components/library/paper-failure";
import { PaperStatusBadge } from "@/components/library/paper-status-badge";
import { ProcessingDetails } from "@/components/library/processing-details";
import { ChunkList } from "@/components/reader/chunk-list";
import { PaperMetadata } from "@/components/reader/paper-metadata";
import { type PdfTarget, PdfViewer } from "@/components/reader/pdf-viewer-lazy";
import { SectionTree } from "@/components/reader/section-tree";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAdvancedMode } from "@/lib/advanced";
import { api, messageOf } from "@/lib/api-client";
import { isInProgress } from "@/lib/paper-status";
import { track, useProcessing } from "@/lib/processing-store";
import type { PaperDetail, Section } from "@/lib/types";

export default function PaperReaderPage({ params }: PageProps<"/library/[paperId]">) {
  const { paperId } = use(params);
  const { open: openAddPaper } = useAddPaper();
  const { ask, busy } = useAskPapers();

  const [paper, setPaper] = useState<PaperDetail | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<PdfTarget | null>(null);
  const [editing, setEditing] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const advanced = useAdvancedMode();

  // The store's copy says when a paper being prepared moves on or finishes.
  const live = useProcessing().find((known) => known.id === paperId);
  const status = live?.status ?? paper?.status;

  const load = useCallback(async () => {
    try {
      const loaded = await api<PaperDetail>(`/papers/${paperId}`);
      setPaper(loaded);
      if (isInProgress(loaded)) track(loaded);
      setSections(loaded.status === "READY" ? await api<Section[]>(`/papers/${paperId}/sections`) : []);
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, [paperId]);

  useEffect(() => {
    void load();
  }, [load, status]);

  if (error) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader title="Paper" />
        <div className="m-auto flex flex-col items-center gap-3 text-center">
          <p className="text-sm text-muted-foreground">{error}</p>
          <Link href="/library" className="text-sm font-medium underline underline-offset-4">
            Back to library
          </Link>
        </div>
      </div>
    );
  }
  if (!paper) {
    return (
      <div className="flex h-full flex-col" aria-busy="true">
        <PageHeader title="Paper" />
      </div>
    );
  }

  const shown = { ...paper, ...live };
  const details = (
    <div className="flex flex-col gap-6 p-4">
      <PaperMetadata paper={shown} />

      {shown.status === "FAILED" && (
        <PaperFailure paper={shown} onReplace={openAddPaper} onRetried={() => void load()} />
      )}
      {isInProgress(shown) && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
          This paper is being prepared. You can read it now and ask about it once it is ready.
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button disabled={shown.status !== "READY" || shown.needs_reindex || busy} onClick={() => ask([paper.id])}>
          Ask this paper
        </Button>
        <Button variant="outline" onClick={() => setEditing(true)}>
          <Pencil /> Edit information
        </Button>
        <Button variant="outline" onClick={() => setCollecting(true)}>
          Add to collection
        </Button>
      </div>
      {shown.needs_reindex && (
        <p className="text-sm text-muted-foreground">
          This paper was prepared with another model than the one you use now. Prepare your papers again in{" "}
          <Link href="/settings" className="font-medium text-foreground underline underline-offset-4">
            Settings
          </Link>{" "}
          to ask about it.
        </p>
      )}

      {paper.summary && (
        <section className="flex flex-col gap-1.5">
          <h3 className="text-sm font-medium">Summary</h3>
          <p className="text-sm leading-relaxed whitespace-pre-line text-muted-foreground">{paper.summary}</p>
        </section>
      )}

      {shown.status === "READY" && (
        <section className="flex flex-col gap-1.5">
          <h3 className="text-sm font-medium">Sections</h3>
          <SectionTree
            sections={sections}
            onOpen={(section) => {
              setTarget({ page: section.page, key: `${section.id}:${Date.now()}` });
              setInfoOpen(false);
            }}
          />
        </section>
      )}
    </div>
  );
  // The technical view adds how the paper was processed and what it was split into.
  const information = !advanced ? (
    details
  ) : (
    <Tabs defaultValue="details" className="gap-0">
      <TabsList className="mx-4 mt-4">
        <TabsTrigger value="details">Details</TabsTrigger>
        <TabsTrigger value="processing">Processing</TabsTrigger>
        <TabsTrigger value="chunks">Chunks</TabsTrigger>
      </TabsList>
      <TabsContent value="details">{details}</TabsContent>
      <TabsContent value="processing" className="p-4">
        <ProcessingDetails paperId={paper.id} status={`${shown.status}:${shown.processing_step}`} />
      </TabsContent>
      <TabsContent value="chunks" className="p-4">
        <ChunkList
          paperId={paper.id}
          onOpen={(chunk) => {
            setTarget({ page: chunk.page_start, boxes: chunk.bboxes, key: `${chunk.id}:${Date.now()}` });
            setInfoOpen(false);
          }}
        />
      </TabsContent>
    </Tabs>
  );

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Link href="/library" aria-label="Back to library" className="text-muted-foreground hover:text-foreground">
              <ChevronLeft className="size-4" />
            </Link>
            <span className="truncate">{shown.title}</span>
          </span>
        }
      >
        <PaperStatusBadge paper={shown} className="hidden text-muted-foreground sm:inline-flex" />
        <Button variant="outline" size="sm" className="lg:hidden" onClick={() => setInfoOpen(true)}>
          <Info /> Details
        </Button>
      </PageHeader>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          <PdfViewer paperId={paper.id} target={target} />
        </div>
        <aside className="hidden w-96 shrink-0 overflow-y-auto border-l lg:block">{information}</aside>
      </div>

      {/* Below the desktop width the information column becomes a sheet over the PDF. */}
      <Sheet open={infoOpen} onOpenChange={setInfoOpen}>
        <SheetContent className="overflow-y-auto lg:hidden">
          <SheetHeader>
            <SheetTitle>Paper details</SheetTitle>
          </SheetHeader>
          {information}
        </SheetContent>
      </Sheet>

      <AddToCollectionDialog paperIds={collecting ? [paper.id] : null} onClose={() => setCollecting(false)} />
      <MetadataDialog
        paper={editing ? shown : null}
        onClose={() => setEditing(false)}
        onSaved={(saved) => setPaper({ ...paper, ...saved })}
      />
    </div>
  );
}
