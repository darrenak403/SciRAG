"use client";

import { useSyncExternalStore } from "react";

import { api } from "@/lib/api-client";
import type { AskMode, Chat } from "@/lib/types";

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

const QUESTION_KEY = "scirag:first-question:";

// What a session asks: the papers named, or whatever a collection holds.
export type Scope = string[] | { collectionId: string };

/**
 * Opens a new research session over this scope and returns its address.
 * A question given here is asked as soon as the session opens.
 */
export async function startResearch(scope: Scope, question?: string, mode: AskMode = "auto"): Promise<string> {
  const json = Array.isArray(scope) ? { paper_ids: scope } : { collection_id: scope.collectionId };
  const chat = await api<Chat>("/chats", { method: "POST", json });
  if (question?.trim()) {
    sessionStorage.setItem(QUESTION_KEY + chat.id, JSON.stringify({ question: question.trim(), mode }));
  }
  void refreshRecentResearch();
  return `/research/${chat.id}`;
}

/** The question typed before the session existed, and the kind of answer asked for. Returned once. */
export function takeFirstQuestion(chatId: string): { question: string; mode: AskMode } | null {
  const stored = sessionStorage.getItem(QUESTION_KEY + chatId);
  if (!stored) return null;
  sessionStorage.removeItem(QUESTION_KEY + chatId);
  try {
    return JSON.parse(stored);
  } catch {
    return null;
  }
}
