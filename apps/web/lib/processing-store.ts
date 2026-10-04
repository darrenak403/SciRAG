"use client";

import { useSyncExternalStore } from "react";

import { api, ApiError } from "@/lib/api-client";
import { isInProgress } from "@/lib/paper-status";
import type { Paper, PaperPage } from "@/lib/types";

// The papers being prepared, and the ones that finished since the reader last looked.
// The widget, the library and the Add papers dialog all read from here, so there is one
// polling loop however many of them are on screen.

const POLL_MS = 3000;
const EMPTY: Paper[] = [];

let papers: Paper[] = EMPTY;
let timer: ReturnType<typeof setTimeout> | null = null;
let polling = false;
// The last poll failed, so what is in progress is not known: ask again even with nothing listed.
let unsure = false;
const listeners = new Set<() => void>();

function publish(next: Paper[]) {
  papers = next;
  for (const listener of listeners) listener();
}

async function latest(id: string): Promise<Paper | null> {
  try {
    return await api<Paper>(`/papers/${id}`);
  } catch (error) {
    // Deleted while it was being prepared.
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

async function poll() {
  if (polling) return;
  polling = true;
  try {
    const page = await api<PaperPage>("/papers?status=UPLOADED&status=PROCESSING&page_size=100");
    const running = new Map(page.items.map((paper) => [paper.id, paper]));
    // These left the list: finished, failed or deleted. Ask which.
    const left = papers.filter((paper) => isInProgress(paper) && !running.has(paper.id));
    const settled = new Map(await Promise.all(left.map(async (paper) => [paper.id, await latest(paper.id)] as const)));
    // Built from the list as it is now, with no waiting in between: a paper that was
    // tracked or dismissed while the answers were on their way is kept as it is.
    const next: Paper[] = [];
    for (const paper of papers) {
      const now = running.get(paper.id);
      if (now) {
        next.push(now);
        running.delete(paper.id);
      } else if (settled.has(paper.id)) {
        const after = settled.get(paper.id);
        if (after) next.push(after);
      } else {
        next.push(paper);
      }
    }
    // In progress but not known here: started before the page was loaded, or in another tab.
    next.push(...running.values());
    unsure = false;
    publish(next);
  } catch {
    // Offline or signed out. Keep what is shown and try again on the next tick.
    unsure = true;
  } finally {
    polling = false;
    schedule();
  }
}

function schedule() {
  if (timer) clearTimeout(timer);
  timer = null;
  if (listeners.size > 0 && (unsure || papers.some(isInProgress))) {
    timer = setTimeout(poll, POLL_MS);
  }
}

/** Starts watching a paper that was just uploaded or sent for processing again. */
export function track(paper: Paper) {
  publish([...papers.filter((known) => known.id !== paper.id), paper]);
  schedule();
}

/** Looks now for papers that were sent for processing by something other than an upload. */
export function refreshProcessing() {
  void poll();
}

/** Forgets papers that are no longer being prepared, once the reader has seen them. */
export function dismissFinished() {
  publish(papers.filter(isInProgress));
}

export function forget(id: string) {
  publish(papers.filter((paper) => paper.id !== id));
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  // The first reader on the page: find what is already being prepared.
  if (listeners.size === 1) void poll();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer) {
      clearTimeout(timer);
      timer = null;
    }
  };
}

export function useProcessing(): Paper[] {
  return useSyncExternalStore(
    subscribe,
    () => papers,
    () => EMPTY,
  );
}
