"use client";

import { Paperclip } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAddPaper } from "@/components/add-paper/add-paper-provider";
import { useAskPapers } from "@/components/add-paper/ready-actions";
import { PageHeader } from "@/components/app-shell/page-header";
import { useSession } from "@/components/app-shell/session";
import { Composer } from "@/components/research/composer";
import { SourceSelector } from "@/components/research/source-selector";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { plural, relativeDay } from "@/lib/format";
import { providerProblem } from "@/lib/provider-errors";
import { useRecentResearch } from "@/lib/research";
import { useReadyPapers } from "@/lib/use-ready-papers";

const SUGGESTIONS = [
  { label: "Summarize a paper", question: "Summarize the key findings of this paper." },
  { label: "Compare selected papers", question: "Compare the methods used in these papers." },
  { label: "Find research gaps", question: "What research gaps or open problems do these papers point to?" },
  { label: "Review methodologies", question: "What methodologies do these papers use, and how do they differ?" },
];

const RECENT_SHOWN = 6;

export default function AskPage() {
  const { user } = useSession();
  const { open: openAddPaper } = useAddPaper();
  const { ask, busy } = useAskPapers();
  const papers = useReadyPapers();
  const recent = useRecentResearch();

  const [question, setQuestion] = useState("");
  // null: every ready paper, including ones that become ready while the page is open.
  const [chosen, setChosen] = useState<string[] | null>(null);
  const sources = chosen ?? papers?.map((paper) => paper.id) ?? [];
  const noProvider = providerProblem(user.active_connection_id ? null : "provider_not_configured");

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Ask" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-8 px-4 py-10 sm:py-16">
          <h2 className="text-center text-2xl font-semibold tracking-tight">What would you like to research?</h2>

          {noProvider && (
            <Alert>
              <AlertTitle>Set up your model provider to get started</AlertTitle>
              <AlertDescription>
                ScientRAG reads papers and answers questions with your own key.{" "}
                <Link href="/settings" className="font-medium underline underline-offset-4">
                  Open settings
                </Link>
              </AlertDescription>
            </Alert>
          )}

          <div className="flex flex-col gap-2">
            <Composer
              value={question}
              onChange={setQuestion}
              onSend={() => ask(sources, question)}
              disabled={busy || sources.length === 0}
              placeholder="Ask a question about your papers…"
              autoFocus
            >
              <Button type="button" variant="ghost" size="sm" onClick={openAddPaper}>
                <Paperclip /> Add papers
              </Button>
              <SourceSelector papers={papers ?? []} selected={sources} onApply={setChosen} />
            </Composer>
            {papers?.length === 0 && (
              <p className="text-center text-sm text-muted-foreground">
                Your library has no ready papers yet.{" "}
                <button className="font-medium text-foreground underline underline-offset-4" onClick={openAddPaper}>
                  Add papers
                </button>{" "}
                to start asking.
              </p>
            )}
            {papers && papers.length > 0 && sources.length === 0 && (
              <p className="text-center text-sm text-muted-foreground">Choose at least one source to ask.</p>
            )}
          </div>

          <section aria-label="Suggested actions" className="flex flex-wrap justify-center gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <Button
                key={suggestion.label}
                variant="outline"
                size="sm"
                onClick={() => setQuestion(suggestion.question)}
              >
                {suggestion.label}
              </Button>
            ))}
          </section>

          {recent && recent.length > 0 && (
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-medium text-muted-foreground">Recent research</h3>
              <ul className="divide-y rounded-lg border">
                {recent.slice(0, RECENT_SHOWN).map((chat) => (
                  <li key={chat.id}>
                    <Link
                      href={`/research/${chat.id}`}
                      className="flex items-baseline gap-3 px-3 py-2 text-sm hover:bg-muted"
                    >
                      <span className="min-w-0 flex-1 truncate">{chat.title ?? "Untitled research"}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {plural(chat.source_count, "paper")} · {relativeDay(chat.updated_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
