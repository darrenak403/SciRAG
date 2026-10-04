"use client";

import { useSyncExternalStore } from "react";

import { api } from "@/lib/api-client";
import type { Chat } from "@/lib/types";

// The research sessions used last. The sidebar and the Ask page show the same list.

let chats: Chat[] | null = null;
const listeners = new Set<() => void>();

export async function refreshRecentResearch() {
  try {
    chats = await api<Chat[]>("/chats?limit=20");
    for (const listener of listeners) listener();
  } catch {
    // Left as it was; the next refresh may work.
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1 && chats === null) void refreshRecentResearch();
  return () => {
    listeners.delete(listener);
  };
}

/** null while the first load is under way. */
export function useRecentResearch(): Chat[] | null {
  return useSyncExternalStore(
    subscribe,
    () => chats,
    () => null,
  );
}

const QUESTION_KEY = "scientrag:first-question:";

/**
 * Opens a new research session over these papers and returns its address.
 * A question given here is asked as soon as the session opens.
 */
export async function startResearch(paperIds: string[], question?: string): Promise<string> {
  const chat = await api<Chat>("/chats", { method: "POST", json: { paper_ids: paperIds } });
  if (question?.trim()) sessionStorage.setItem(QUESTION_KEY + chat.id, question.trim());
  void refreshRecentResearch();
  return `/research/${chat.id}`;
}

/** The question typed before the session existed. Returned once. */
export function takeFirstQuestion(chatId: string): string | null {
  const question = sessionStorage.getItem(QUESTION_KEY + chatId);
  if (question) sessionStorage.removeItem(QUESTION_KEY + chatId);
  return question;
}
