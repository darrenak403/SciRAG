"use client";

import { Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { PdfHighlightLayer } from "@/components/reader/pdf-highlight-layer";
import { Button } from "@/components/ui/button";
import { API_BASE } from "@/lib/api-client";
import type { Box } from "@/lib/types";

import "@/lib/map-upsert-polyfill";
import "react-pdf/dist/Page/TextLayer.css";

// Has to be set in the module that renders the pages. The legacy build carries its own
// polyfills, so the worker also runs in browsers that are a release or two behind.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/legacy/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

// Height over width of a page before its real size is known: US Letter.
const DEFAULT_RATIO = 11 / 8.5;
const GAP = 12;
const ZOOMS = [0.75, 1, 1.25, 1.5, 2];

export type PdfTarget = {
  page: number;
  // The passage to mark. Without boxes the viewer only goes to the page.
  boxes?: Box[];
  // Changes whenever the viewer should go there again, even to the same place.
  key: string | number;
};

export default function PdfViewer({ paperId, target }: { paperId: string; target?: PdfTarget | null }) {
  const scroller = useRef<HTMLDivElement>(null);
  const pageNodes = useRef(new Map<number, HTMLDivElement>());
  const [pageCount, setPageCount] = useState(0);
  const [width, setWidth] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [ratios, setRatios] = useState<Record<number, number>>({});
  const [visible, setVisible] = useState<Set<number>>(new Set([1]));
  const [current, setCurrent] = useState(1);
  const [failed, setFailed] = useState(false);

  const file = useMemo(() => `${API_BASE}/papers/${paperId}/file`, [paperId]);
  const pageWidth = Math.max(0, Math.floor((width - 2 * GAP) * zoom));
  // The pages are in the document only once the width is known.
  const laidOut = pageCount > 0 && pageWidth > 0;

  useLayoutEffect(() => {
    const node = scroller.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // Only pages in or near view are drawn; a long paper would otherwise take seconds and a lot of memory.
  useEffect(() => {
    const root = scroller.current;
    if (!root || !laidOut) return;
    const observer = new IntersectionObserver(
      (entries) => {
        setVisible((before) => {
          const next = new Set(before);
          for (const entry of entries) {
            const page = Number((entry.target as HTMLElement).dataset.page);
            if (entry.isIntersecting) next.add(page);
            else next.delete(page);
          }
          return next;
        });
      },
      { root, rootMargin: "100% 0px" },
    );
    for (const node of pageNodes.current.values()) observer.observe(node);
    return () => observer.disconnect();
  }, [laidOut, pageCount]);

  const goTo = useCallback((page: number, boxes?: Box[]) => {
    const root = scroller.current;
    const node = pageNodes.current.get(page);
    if (!root || !node) return;
    const top = boxes?.length ? Math.min(...boxes.map((box) => box.bbox[1])) : null;
    const bottom = boxes?.length ? Math.max(...boxes.map((box) => box.bbox[3])) : null;
    // A marked passage goes to the middle of the view; a bare page to the top.
    const offset =
      top !== null && bottom !== null
        ? node.offsetTop + ((top + bottom) / 2) * node.offsetHeight - root.clientHeight / 2
        : node.offsetTop - GAP;
    root.scrollTo({ top: Math.max(0, offset) });
  }, []);

  // After the pages have a size: before that every offset is zero. Pages start at an
  // estimated height, so the place moves as their real sizes arrive; the viewer keeps
  // going back to it until the reader scrolls away.
  const arrived = useRef<{ key: PdfTarget["key"] | null; moved: boolean }>({ key: null, moved: false });
  useEffect(() => {
    if (!target || !laidOut) return;
    if (arrived.current.key !== target.key) arrived.current = { key: target.key, moved: false };
    if (arrived.current.moved) return;
    const onPage = target.boxes?.filter((box) => box.page === target.page);
    goTo(target.page, onPage);
    // The target's key, not its identity, says when to go again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.key, laidOut, goTo, ratios, pageWidth]);
  const readerMoved = () => {
    arrived.current.moved = true;
  };

  function trackCurrent() {
    const root = scroller.current;
    if (!root) return;
    const middle = root.scrollTop + root.clientHeight / 2;
    for (const [page, node] of pageNodes.current) {
      if (node.offsetTop <= middle && middle < node.offsetTop + node.offsetHeight + GAP) {
        setCurrent(page);
        return;
      }
    }
  }

  const zoomIndex = ZOOMS.indexOf(zoom);

  return (
    <div className="flex h-full min-h-0 flex-col bg-muted/40">
      <div className="flex h-9 shrink-0 items-center justify-between gap-2 border-b bg-background px-2 text-xs text-muted-foreground">
        <span className="tabular-nums" aria-live="off">
          {pageCount > 0 ? `Page ${current} of ${pageCount}` : " "}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Zoom out"
            disabled={zoomIndex <= 0}
            onClick={() => setZoom(ZOOMS[zoomIndex - 1])}
          >
            <Minus />
          </Button>
          <span className="w-10 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Zoom in"
            disabled={zoomIndex >= ZOOMS.length - 1}
            onClick={() => setZoom(ZOOMS[zoomIndex + 1])}
          >
            <Plus />
          </Button>
        </div>
      </div>

      <div
        ref={scroller}
        onScroll={trackCurrent}
        onWheel={readerMoved}
        onTouchMove={readerMoved}
        onPointerDown={readerMoved}
        onKeyDown={readerMoved}
        className="relative min-h-0 flex-1 overflow-auto"
      >
        {failed ? (
          <p className="p-6 text-center text-sm text-muted-foreground">The PDF couldn&apos;t be loaded.</p>
        ) : (
          <Document
            file={file}
            onLoadSuccess={(document) => setPageCount(document.numPages)}
            onLoadError={() => setFailed(true)}
            loading={<p className="p-6 text-center text-sm text-muted-foreground">Loading PDF…</p>}
            error={null}
            className="flex w-max min-w-full flex-col items-center"
          >
            {pageWidth > 0 &&
              Array.from({ length: pageCount }, (_, index) => {
                const page = index + 1;
                const marks = target?.boxes?.filter((box) => box.page === page) ?? [];
                return (
                  <div
                    key={page}
                    data-page={page}
                    ref={(node) => {
                      if (node) pageNodes.current.set(page, node);
                      else pageNodes.current.delete(page);
                    }}
                    className="relative shrink-0 bg-white shadow-sm"
                    style={{
                      width: pageWidth,
                      height: Math.round(pageWidth * (ratios[page] ?? ratios[1] ?? DEFAULT_RATIO)),
                      margin: `${GAP}px ${GAP}px 0`,
                    }}
                  >
                    {visible.has(page) && (
                      <Page
                        pageNumber={page}
                        width={pageWidth}
                        renderAnnotationLayer={false}
                        loading={null}
                        onLoadSuccess={({ originalWidth, originalHeight }) => {
                          const ratio = originalHeight / originalWidth;
                          setRatios((known) => (known[page] === ratio ? known : { ...known, [page]: ratio }));
                        }}
                      />
                    )}
                    {marks.length > 0 && <PdfHighlightLayer boxes={marks} />}
                  </div>
                );
              })}
            <div style={{ height: GAP }} />
          </Document>
        )}
      </div>
    </div>
  );
}
