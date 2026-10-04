"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import { useProcessing } from "@/lib/processing-store";
import type { Paper, PaperPage } from "@/lib/types";

// The server's largest page. A library with more ready papers than this shows the newest ones.
const MOST = 100;

/** The papers that can be asked about. null while loading. Reloads when a paper becomes ready. */
export function useReadyPapers(): Paper[] | null {
  const [papers, setPapers] = useState<Paper[] | null>(null);
  const ready = useProcessing()
    .filter((paper) => paper.status === "READY")
    .map((paper) => paper.id)
    .join(",");

  const load = useCallback(async () => {
    try {
      const page = await api<PaperPage>(`/papers?status=READY&page_size=${MOST}`);
      // One indexed with another model than the account uses now is left out of search.
      setPapers(page.items.filter((paper) => !paper.needs_reindex));
    } catch {
      setPapers((current) => current ?? []);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, ready]);

  return papers;
}
