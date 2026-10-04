"use client";

import dynamic from "next/dynamic";

// pdf.js needs the browser: it is left out of the server render and loaded when first shown.
export const PdfViewer = dynamic(() => import("@/components/reader/pdf-viewer"), {
  ssr: false,
  loading: () => <p className="p-6 text-center text-sm text-muted-foreground">Loading PDF…</p>,
});

export type { PdfTarget } from "@/components/reader/pdf-viewer";
