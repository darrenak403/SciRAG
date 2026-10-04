"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api-client";
import { refreshRecentResearch } from "@/lib/research";
import { postEvents } from "@/lib/sse";
import type { Message, Source } from "@/lib/types";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  // The passages the answer may point at: all that were found while it is being
  // written, only the cited ones once it is finished.
  sources: Source[];
  state: "done" | "streaming" | "stopped" | "failed";
  error?: { code: string | null; message: string };
};

type DoneEvent = { message_id: string; text: string; citations: string[] };
type ErrorEvent = { code: string; message: string };

let localId = 0;
const draftId = () => `draft-${localId++}`;

/**
 * The conversation of one research session: what was said before, and the answer
 * being written now. The server keeps a question only together with its finished
 * answer, so a stopped or failed exchange exists here alone and can be asked again.
 */
export function useResearchChat(chatId: string) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const running = useRef<AbortController | null>(null);
  const [streaming, setStreaming] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<Message[]>(`/chats/${chatId}/messages`)
      .then((saved) => {
        if (cancelled) return;
        // Do not wipe an exchange that started while the history was loading.
        const known = new Set(saved.map((message) => message.id));
        setMessages((current) => [
          ...saved.map(
            (message): ChatMessage => ({
              id: message.id,
              role: message.role,
              content: message.content,
              sources: message.citations,
              state: "done",
            }),
          ),
          // Without what the history already holds: an answer may have finished in the meantime.
          ...(current ?? []).filter((message) => !known.has(message.id)),
        ]);
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : "Couldn't load this session.");
      });
    return () => {
      cancelled = true;
      running.current?.abort();
    };
  }, [chatId]);

  const send = useCallback(
    async (question: string) => {
      if (running.current) return;
      const controller = new AbortController();
      running.current = controller;
      setStreaming(true);

      const answerId = draftId();
      const patch = (changes: Partial<ChatMessage> | ((message: ChatMessage) => Partial<ChatMessage>)) =>
        setMessages((current) =>
          (current ?? []).map((message) =>
            message.id === answerId
              ? { ...message, ...(typeof changes === "function" ? changes(message) : changes) }
              : message,
          ),
        );

      setMessages((current) => [
        // An exchange that never completed is replaced by the new one, not stacked under it.
        ...(current ?? []).filter((message, index, all) => {
          const pair = message.role === "user" ? all[index + 1] : message;
          return !pair || pair.state === "done";
        }),
        { id: draftId(), role: "user", content: question, sources: [], state: "done" },
        { id: answerId, role: "assistant", content: "", sources: [], state: "streaming" },
      ]);

      let finished = false;
      try {
        for await (const { event, data } of postEvents(
          `/chats/${chatId}/messages`,
          { content: question },
          controller.signal,
        )) {
          if (event === "sources") {
            patch({ sources: data as Source[] });
          } else if (event === "delta") {
            const { text } = data as { text: string };
            patch((message) => ({ content: message.content + text }));
          } else if (event === "done") {
            const done = data as DoneEvent;
            finished = true;
            // The checked text replaces what was streamed: markers that named no passage are gone.
            patch((message) => ({
              id: done.message_id,
              content: done.text,
              sources: message.sources.filter((source) => done.citations.includes(source.marker)),
              state: "done",
            }));
          } else if (event === "error") {
            const failure = data as ErrorEvent;
            finished = true;
            patch({ state: "failed", error: { code: failure.code, message: failure.message } });
          }
        }
        if (!finished) {
          patch({
            state: "failed",
            error: { code: "network", message: "The connection was lost before the answer finished." },
          });
        }
      } catch (error) {
        if (controller.signal.aborted) {
          patch({ state: "stopped" });
        } else {
          patch({
            state: "failed",
            error: {
              code: error instanceof ApiError ? error.code : null,
              message: error instanceof Error ? error.message : "Something went wrong.",
            },
          });
        }
      } finally {
        running.current = null;
        setStreaming(false);
        // The first answer names the session.
        if (finished) void refreshRecentResearch();
      }
    },
    [chatId],
  );

  const stop = useCallback(() => running.current?.abort(), []);

  return { messages, loadError, streaming, send, stop };
}
