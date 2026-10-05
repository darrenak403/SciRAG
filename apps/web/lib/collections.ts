"use client";

import { useSyncExternalStore } from "react";

import { api } from "@/lib/api-client";
import type { Collection } from "@/lib/types";

// The account's collections. The sidebar pages, the source pickers and the
// "add to collection" dialogs all show the same list.

let collections: Collection[] | null = null;
const listeners = new Set<() => void>();

export async function refreshCollections() {
  try {
    collections = await api<Collection[]>("/collections");
    for (const listener of listeners) listener();
  } catch {
    // Left as it was; the next refresh may work.
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1 && collections === null) void refreshCollections();
  return () => {
    listeners.delete(listener);
  };
}

/** null while the first load is under way. */
export function useCollections(): Collection[] | null {
  return useSyncExternalStore(
    subscribe,
    () => collections,
    () => null,
  );
}

export async function createCollection(name: string, description: string, paperIds: string[] = []) {
  const created = await api<Collection>("/collections", {
    method: "POST",
    json: { name, description: description || null, paper_ids: paperIds },
  });
  void refreshCollections();
  return created;
}

export async function addToCollection(collectionId: string, paperIds: string[]) {
  for (const paperId of paperIds) {
    await api(`/collections/${collectionId}/papers/${paperId}`, { method: "PUT" });
  }
  void refreshCollections();
}
