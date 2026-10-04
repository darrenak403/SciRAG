"use client";

import { Loader2, RotateCcw } from "lucide-react";
import Link from "next/link";
import { createContext, memo, useContext, useEffect, useRef } from "react";
import Markdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

import { CitationMarker } from "@/components/research/citation-marker";
import { Button, buttonVariants } from "@/components/ui/button";
import type { ChatMessage } from "@/lib/chat-runtime";
import { answerMarkdown, CITATION_HREF } from "@/lib/answer-markdown";
import { plural } from "@/lib/format";
import { providerProblem } from "@/lib/provider-errors";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

import "katex/dist/katex.min.css";

const STARTERS = ["Summarize key findings", "Compare methodologies", "Find limitations"];

type AnswerProps = {
  message: ChatMessage;
  activeChunk: string | null;
  onOpenSource: (source: Source, message: ChatMessage) => void;
};

const AnswerContext = createContext<AnswerProps | null>(null);

/** A link in an answer: a source marker, or an ordinary link that opens in a new tab. */
function AnswerLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  const answer = useContext(AnswerContext);
  if (answer && href?.startsWith(CITATION_HREF)) {
    const marker = href.slice(CITATION_HREF.length);
    const source = answer.message.sources.find((known) => known.marker === marker);
    // A marker for a passage that was not given to the model: shown as plain text.
    if (!source) return <>{children}</>;
    return (
      <CitationMarker
        source={source}
        active={answer.activeChunk === source.chunk_id}
        onOpen={(opened) => answer.onOpenSource(opened, answer.message)}
      />
    );
  }
  return (
    <a href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  );
}

// One fixed set: a new one on every render would build every marker anew, closing its
// card and losing its state each time a piece of the answer arrives.
const COMPONENTS: Components = { a: AnswerLink };
// Formulas are typeset; one the typesetter cannot read is shown as written, not as an error.
const MATH = [remarkMath];
const TYPESET = [[rehypeKatex, { errorColor: "currentColor" }]] satisfies React.ComponentProps<typeof Markdown>["rehypePlugins"];

// Memoised: while one answer streams in, the earlier ones are not parsed again.
const Answer = memo(function Answer(props: AnswerProps) {
  return (
    // react-markdown renders no raw HTML: what a model writes cannot become markup.
    <div className="answer text-sm leading-relaxed">
      <AnswerContext.Provider value={props}>
        {/* No images: a picture address written by the model would be fetched, and could carry text out. */}
        <Markdown
          components={COMPONENTS}
          disallowedElements={["img"]}
          remarkPlugins={MATH}
          rehypePlugins={TYPESET}
        >
          {answerMarkdown(props.message.content)}
        </Markdown>
      </AnswerContext.Provider>
    </div>
  );
});

function Failure({ message, onRetry }: { message: ChatMessage; onRetry: () => void }) {
  const provider = providerProblem(message.error?.code, message.error?.message);
  return (
    <div role="alert" className="flex flex-col gap-2 rounded-lg border px-3 py-2 text-sm">
      <div>
        <p className="font-medium">{provider?.title ?? "The answer couldn't be completed"}</p>
        <p className="text-muted-foreground">{provider?.hint ?? message.error?.message}</p>
      </div>
      <div className="flex gap-2">
        {provider?.openSettings && (
          <Link href="/settings" className={buttonVariants({ size: "sm", variant: "outline" })}>
            Open settings
          </Link>
        )}
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RotateCcw /> Try again
        </Button>
      </div>
    </div>
  );
}

export function ChatPanel({
  messages,
  streaming,
  selectedMessage,
  activeChunk,
  onOpenSource,
  onShowSources,
  onAsk,
}: {
  messages: ChatMessage[];
  streaming: boolean;
  // The answer whose sources the evidence panel is showing.
  selectedMessage: string | null;
  activeChunk: string | null;
  onOpenSource: (source: Source, message: ChatMessage) => void;
  onShowSources: (message: ChatMessage) => void;
  onAsk: (question: string) => void;
}) {
  const end = useRef<HTMLDivElement>(null);
  const last = messages.at(-1);

  // Follow the answer as it is written, and jump to the newest message when one is added.
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length, last?.content, last?.state]);

  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
        <h2 className="text-base font-medium">Ask anything about your selected papers</h2>
        <div className="flex flex-wrap justify-center gap-2">
          {STARTERS.map((starter) => (
            <Button key={starter} variant="outline" size="sm" onClick={() => onAsk(`${starter}.`)}>
              {starter}
            </Button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto" aria-live="polite">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
        {messages.map((message, index) => {
          if (message.role === "user") {
            return (
              <div key={message.id} className="max-w-[85%] self-end rounded-xl bg-muted px-3 py-2 text-sm whitespace-pre-wrap">
                {message.content}
              </div>
            );
          }
          const question = messages[index - 1]?.content ?? "";
          const waiting = message.state === "streaming" && message.content === "";
          return (
            <article key={message.id} className="flex flex-col gap-2">
              {waiting ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" aria-hidden />
                  {message.sources.length > 0 ? "Writing the answer…" : "Searching your papers…"}
                </p>
              ) : (
                <Answer message={message} activeChunk={activeChunk} onOpenSource={onOpenSource} />
              )}
              {message.state === "failed" && <Failure message={message} onRetry={() => onAsk(question)} />}
              {message.state === "stopped" && (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  Stopped.
                  <Button size="sm" variant="ghost" disabled={streaming} onClick={() => onAsk(question)}>
                    <RotateCcw /> Ask again
                  </Button>
                </p>
              )}
              {message.state === "done" && message.sources.length > 0 && (
                <button
                  onClick={() => onShowSources(message)}
                  aria-pressed={selectedMessage === message.id}
                  className={cn(
                    "self-start rounded-md text-xs underline-offset-4 hover:underline",
                    selectedMessage === message.id ? "font-medium text-citation" : "text-muted-foreground",
                  )}
                >
                  {plural(message.sources.length, "source")}
                </button>
              )}
            </article>
          );
        })}
        <div ref={end} />
      </div>
    </div>
  );
}
