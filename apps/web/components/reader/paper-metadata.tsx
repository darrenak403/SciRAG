import { AlertTriangle } from "lucide-react";

import type { PaperDetail } from "@/lib/types";

export function PaperMetadata({ paper }: { paper: PaperDetail }) {
  const facts = [paper.year, paper.page_count ? `${paper.page_count} pages` : null].filter(Boolean);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h2 className="text-base leading-snug font-semibold">{paper.title}</h2>
        {paper.authors.length > 0 && <p className="text-sm text-muted-foreground">{paper.authors.join(", ")}</p>}
        {facts.length > 0 && <p className="text-sm text-muted-foreground">{facts.join(" · ")}</p>}
        {paper.doi && (
          <a
            href={`https://doi.org/${encodeURI(paper.doi)}`}
            target="_blank"
            rel="noreferrer noopener"
            className="self-start text-sm text-muted-foreground underline underline-offset-4"
          >
            {paper.doi}
          </a>
        )}
      </div>
      {paper.status === "READY" &&
        paper.warnings.map((warning) => (
          <p key={warning} className="flex items-start gap-1.5 text-sm text-muted-foreground">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
            {warning} The paper is still searchable.
          </p>
        ))}
    </div>
  );
}
