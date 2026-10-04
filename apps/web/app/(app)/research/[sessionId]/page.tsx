"use client";

import { BookOpen, Quote } from "lucide-react";
import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell/page-header";
import { ChatPanel } from "@/components/research/chat-panel";
import { Composer } from "@/components/research/composer";
import { EvidencePanel } from "@/components/research/evidence-panel";
import { SourcePanel } from "@/components/research/source-panel";
import { SourceSelector } from "@/components/research/source-selector";
import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api, messageOf } from "@/lib/api-client";
import { type ChatMessage, useResearchChat } from "@/lib/chat-runtime";
import { takeFirstQuestion } from "@/lib/research";
import type { Chat, Source } from "@/lib/types";
import { useMediaQuery } from "@/lib/use-media-query";
import { useReadyPapers } from "@/lib/use-ready-papers";

export default function ResearchPage({ params }: PageProps<"/research/[sessionId]">) {
  const { sessionId } = use(params);
  const papers = useReadyPapers();
  const { messages, loadError, streaming, send, stop } = useResearchChat(sessionId);
  // Three columns need the room; below this width Sources and Evidence open over the chat.
  const wide = useMediaQuery("(min-width: 1024px)");

  const [chat, setChat] = useState<Chat | null>(null);
  const [missing, setMissing] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  // The answer whose sources the evidence panel lists, and the passage open in the PDF.
  const [selected, setSelected] = useState<ChatMessage | null>(null);
  const [active, setActive] = useState<Source | null>(null);
  const [sheet, setSheet] = useState<"sources" | "evidence" | null>(null);

  useEffect(() => {
    api<Chat>(`/chats/${sessionId}`)
      .then(setChat)
      .catch((error: unknown) => setMissing(messageOf(error)));
  }, [sessionId]);

  // A question typed on the Ask page is asked as soon as the session is on screen.
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current || messages === null) return;
    asked.current = true;
    const first = takeFirstQuestion(sessionId);
    if (first) void send(first);
  }, [messages, sessionId, send]);

  // Changes are shown at once and saved one after another, so two quick choices
  // cannot overtake each other and the next one starts from what is on screen.
  const saving = useRef<Promise<void>>(Promise.resolve());
  const applySources = useCallback(
    (paperIds: string[]) => {
      setChat((current) => current && { ...current, paper_ids: paperIds, source_count: paperIds.length });
      saving.current = saving.current.then(async () => {
        try {
          await api<Chat>(`/chats/${sessionId}`, { method: "PATCH", json: { paper_ids: paperIds } });
        } catch (error) {
          toast.error(messageOf(error));
          // Show what the server really holds.
          await api<Chat>(`/chats/${sessionId}`)
            .then(setChat)
            .catch(() => {});
        }
      });
      return saving.current;
    },
    [sessionId],
  );

  const openSource = useCallback((source: Source, message: ChatMessage) => {
    setSelected(message);
    setActive(source);
    setSheet("evidence");
  }, []);

  const showSources = useCallback((message: ChatMessage) => {
    setSelected(message);
    setActive(null);
    setSheet("evidence");
  }, []);

  function ask(text: string) {
    setQuestion("");
    void send(text);
  }

  if (missing || loadError) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader title="Research" />
        <div className="m-auto flex flex-col items-center gap-3 text-center">
          <p className="text-sm text-muted-foreground">{missing ?? loadError}</p>
          <Link href="/" className="text-sm font-medium underline underline-offset-4">
            Start a new question
          </Link>
        </div>
      </div>
    );
  }

  const inUse = chat?.paper_ids ?? [];
  // The newest finished answer, until the reader picks another.
  const shownAnswer =
    (selected && messages?.find((message) => message.id === selected.id)) ??
    messages?.findLast((message) => message.role === "assistant" && message.sources.length > 0) ??
    null;

  const sources = <SourcePanel papers={papers ?? []} selected={inUse} onChange={applySources} />;
  const evidence = (
    <EvidencePanel
      sources={shownAnswer?.sources ?? []}
      active={active}
      onOpen={(source) => setActive(source)}
      onBack={() => setActive(null)}
    />
  );
  const conversation = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1">
        {messages && (
          <ChatPanel
            messages={messages}
            streaming={streaming}
            selectedMessage={shownAnswer?.id ?? null}
            activeChunk={active?.chunk_id ?? null}
            onOpenSource={openSource}
            onShowSources={showSources}
            onAsk={ask}
          />
        )}
      </div>
      <div className="mx-auto w-full max-w-3xl shrink-0 px-4 pb-4">
        <Composer
          value={question}
          onChange={setQuestion}
          onSend={() => ask(question)}
          onStop={stop}
          streaming={streaming}
          // Until the history is in, a question typed here could race the one carried over from Ask.
          disabled={inUse.length === 0 || messages === null}
          placeholder="Ask about the selected papers…"
          autoFocus
        >
          <SourceSelector papers={papers ?? []} selected={inUse} onApply={applySources} />
        </Composer>
        {chat && inUse.length === 0 && (
          <p className="pt-1.5 text-center text-xs text-muted-foreground">Choose at least one source to ask.</p>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex h-full flex-col">
      <PageHeader title={chat?.title ?? "New research"}>
        {!wide && (
          <>
            <Button variant="outline" size="sm" onClick={() => setSheet("sources")}>
              <BookOpen /> Sources
            </Button>
            <Button variant="outline" size="sm" onClick={() => setSheet("evidence")}>
              <Quote /> Evidence
            </Button>
          </>
        )}
      </PageHeader>

      <div className="min-h-0 flex-1">
        {wide ? (
          <ResizablePanelGroup orientation="horizontal">
            <ResizablePanel defaultSize="20%" minSize="14%" maxSize="30%">
              {sources}
            </ResizablePanel>
            <ResizableHandle />
            <ResizablePanel defaultSize="45%" minSize="30%">
              {conversation}
            </ResizablePanel>
            <ResizableHandle />
            <ResizablePanel defaultSize="35%" minSize="20%">
              {evidence}
            </ResizablePanel>
          </ResizablePanelGroup>
        ) : (
          conversation
        )}
      </div>

      {!wide && (
        <>
          <Sheet open={sheet === "sources"} onOpenChange={(open) => !open && setSheet(null)}>
            <SheetContent side="left" className="gap-0">
              <SheetHeader className="sr-only">
                <SheetTitle>Sources</SheetTitle>
                <SheetDescription>The papers this session draws on.</SheetDescription>
              </SheetHeader>
              {sources}
            </SheetContent>
          </Sheet>
          <Sheet open={sheet === "evidence"} onOpenChange={(open) => !open && setSheet(null)}>
            <SheetContent side="right" className="w-full gap-0 sm:max-w-xl" showCloseButton={false}>
              <SheetHeader className="sr-only">
                <SheetTitle>Evidence</SheetTitle>
                <SheetDescription>The passages the answer is based on.</SheetDescription>
              </SheetHeader>
              <div className="min-h-0 flex-1">{evidence}</div>
              <Button variant="outline" className="m-2" onClick={() => setSheet(null)}>
                Back to chat
              </Button>
            </SheetContent>
          </Sheet>
        </>
      )}
    </div>
  );
}
