"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import { AddPaperDialog } from "@/components/add-paper/add-paper-dialog";
import { ApiError, messageOf } from "@/lib/api-client";
import { track } from "@/lib/processing-store";
import { refusal, uploadPaper } from "@/lib/upload";

export type FileItem = {
  key: string;
  file: File;
  state: "selected" | "refused" | "waiting" | "uploading" | "uploaded" | "duplicate" | "failed";
  // Fraction of the file sent, as the browser reports it.
  progress: number;
  message?: string;
  // The paper this file became, or the one already in the library for a duplicate.
  paperId?: string;
  paperTitle?: string;
};

type AddPaper = {
  open: () => void;
  items: FileItem[];
  // True from "Add n papers" until the dialog is cleared for a new batch.
  started: boolean;
  addFiles: (files: Iterable<File>) => void;
  removeItem: (key: string) => void;
  start: () => void;
  reset: () => void;
};

const AddPaperContext = createContext<AddPaper | null>(null);

export function useAddPaper(): AddPaper {
  const value = useContext(AddPaperContext);
  if (!value) throw new Error("useAddPaper needs an AddPaperProvider above it");
  return value;
}

let nextKey = 0;

/**
 * Owns the upload batch. It lives above the pages, so closing the dialog or moving to
 * another page does not stop an upload that is under way.
 */
export function AddPaperProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const [items, setItems] = useState<FileItem[]>([]);
  const [started, setStarted] = useState(false);
  const uploading = useRef(false);

  const update = useCallback((key: string, changes: Partial<FileItem>) => {
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...changes } : item)));
  }, []);

  const addFiles = useCallback((files: Iterable<File>) => {
    const added = Array.from(files, (file): FileItem => {
      const reason = refusal(file);
      return {
        key: `file-${nextKey++}`,
        file,
        state: reason ? "refused" : "selected",
        progress: 0,
        message: reason ?? undefined,
      };
    });
    setItems((current) => [...current, ...added]);
  }, []);

  const removeItem = useCallback((key: string) => {
    setItems((current) => current.filter((item) => item.key !== key));
  }, []);

  const reset = useCallback(() => {
    if (uploading.current) return;
    setItems([]);
    setStarted(false);
  }, []);

  // One file at a time: each gets an honest percentage and a slow line is not shared out.
  const start = useCallback(async () => {
    if (uploading.current) return;
    uploading.current = true;
    setStarted(true);
    const queue = items.filter((item) => item.state === "selected");
    setItems((current) =>
      current
        .filter((item) => item.state !== "refused")
        .map((item) => (item.state === "selected" ? { ...item, state: "waiting" } : item)),
    );
    for (const item of queue) {
      update(item.key, { state: "uploading", progress: 0 });
      try {
        const paper = await uploadPaper(item.file, (progress) => update(item.key, { progress }));
        track(paper);
        update(item.key, { state: "uploaded", progress: 1, paperId: paper.id });
      } catch (error) {
        if (error instanceof ApiError && error.code === "duplicate_paper") {
          const existing = error.body as { paper_id: string; title: string };
          update(item.key, { state: "duplicate", paperId: existing.paper_id, paperTitle: existing.title });
        } else {
          // This file only; the ones after it still go.
          update(item.key, { state: "failed", message: messageOf(error) });
        }
      }
    }
    uploading.current = false;
  }, [items, update]);

  const value = useMemo<AddPaper>(
    () => ({ open: () => setOpen(true), items, started, addFiles, removeItem, start, reset }),
    [items, started, addFiles, removeItem, start, reset],
  );

  return (
    <AddPaperContext.Provider value={value}>
      {children}
      <AddPaperDialog open={isOpen} onOpenChange={setOpen} />
    </AddPaperContext.Provider>
  );
}
