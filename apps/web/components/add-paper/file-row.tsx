"use client";

import { AlertTriangle, Check, Circle, FileText, Loader2, X } from "lucide-react";
import Link from "next/link";

import type { FileItem } from "@/components/add-paper/add-paper-provider";
import { PaperFailure } from "@/components/library/paper-failure";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { fileSize } from "@/lib/format";
import { displayStatus, PHASES } from "@/lib/paper-status";
import type { Paper } from "@/lib/types";
import { cn } from "@/lib/utils";

function Phases({ paper }: { paper: Paper }) {
  const { phase } = displayStatus(paper);
  return (
    <ol className="mt-1.5 flex flex-col gap-1 text-xs">
      <li className="flex items-center gap-1.5 text-muted-foreground">
        <Check className="size-3 text-success" aria-hidden /> Upload complete
      </li>
      {PHASES.map((label, index) => (
        <li
          key={label}
          className={cn("flex items-center gap-1.5", index === phase ? "text-foreground" : "text-muted-foreground")}
        >
          {index < phase ? (
            <Check className="size-3 text-success" aria-hidden />
          ) : index === phase ? (
            <Loader2 className="size-3 animate-spin" aria-hidden />
          ) : (
            <Circle className="size-3" aria-hidden />
          )}
          {label}
        </li>
      ))}
    </ol>
  );
}

export function FileRow({
  item,
  paper,
  onRemove,
  onReplace,
  onNavigate,
}: {
  item: FileItem;
  // The paper the file became, as the server sees it now.
  paper?: Paper;
  onRemove: () => void;
  onReplace: () => void;
  onNavigate: () => void;
}) {
  const settled = paper && (paper.status === "READY" || paper.status === "FAILED");
  return (
    <li className="flex gap-3 px-3 py-2.5">
      <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="truncate text-sm font-medium">
            {settled || item.state === "duplicate" ? (paper?.title ?? item.paperTitle ?? item.file.name) : item.file.name}
          </p>
          <span className="shrink-0 text-xs text-muted-foreground">{fileSize(item.file.size)}</span>
        </div>

        {item.state === "refused" && (
          <p className="mt-1 flex items-center gap-1.5 text-xs text-warning">
            <AlertTriangle className="size-3" aria-hidden /> {item.message}
          </p>
        )}
        {item.state === "waiting" && <p className="mt-1 text-xs text-muted-foreground">Waiting</p>}
        {item.state === "uploading" && (
          <div className="mt-1.5 flex items-center gap-2">
            <Progress value={item.progress * 100} className="h-1.5 flex-1" aria-label="Upload progress" />
            <span className="w-24 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
              Uploading… {Math.round(item.progress * 100)}%
            </span>
          </div>
        )}
        {item.state === "failed" && (
          <p className="mt-1 flex items-center gap-1.5 text-xs text-warning">
            <AlertTriangle className="size-3 shrink-0" aria-hidden /> {item.message}
          </p>
        )}
        {item.state === "duplicate" && item.paperId && (
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className="text-muted-foreground">This paper is already in your library.</span>
            <Link
              href={`/library/${item.paperId}`}
              onClick={onNavigate}
              className="font-medium underline-offset-4 hover:underline"
            >
              Open existing paper
            </Link>
          </div>
        )}
        {item.state === "uploaded" && paper?.status === "READY" && (
          <div className="mt-1 text-xs">
            <p className="flex items-center gap-1.5 text-muted-foreground">
              <Check className="size-3 text-success" aria-hidden /> Paper ready
              {paper.page_count ? ` · ${paper.page_count} pages` : ""}
            </p>
            {paper.warnings.map((warning) => (
              <p key={warning} className="mt-0.5 flex items-start gap-1.5 text-muted-foreground">
                <AlertTriangle className="mt-0.5 size-3 shrink-0 text-warning" aria-hidden />
                {warning} The paper is still searchable.
              </p>
            ))}
          </div>
        )}
        {item.state === "uploaded" && paper?.status === "FAILED" && (
          <div className="mt-1.5">
            <PaperFailure paper={paper} onReplace={onReplace} />
          </div>
        )}
        {item.state === "uploaded" && paper && !settled && <Phases paper={paper} />}
      </div>

      {(item.state === "selected" || item.state === "refused") && (
        <Button variant="ghost" size="icon-xs" onClick={onRemove} aria-label={`Remove ${item.file.name}`}>
          <X />
        </Button>
      )}
    </li>
  );
}
