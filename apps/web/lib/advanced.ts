"use client";

import { useSyncExternalStore } from "react";

// Whether the technical details are shown: how a paper was processed, the passages
// it was cut into, how the passages behind an answer were found. Kept in this
// browser only. It changes what is shown, never what the account may read.

const KEY = "scientrag:advanced";
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "on";
  } catch {
    return false;
  }
}

export function useAdvancedMode(): boolean {
  return useSyncExternalStore(subscribe, read, () => false);
}

export function setAdvancedMode(on: boolean) {
  try {
    if (on) localStorage.setItem(KEY, "on");
    else localStorage.removeItem(KEY);
  } catch {
    // Storage is unavailable: the setting cannot be kept.
  }
  for (const listener of listeners) listener();
}
