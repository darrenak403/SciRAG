import { providerProblem } from "@/lib/provider-errors";
import type { Paper } from "@/lib/types";

// The three things a reader sees happening to a paper. The server works in seven steps.
export const PHASES = ["Reading document", "Extracting information", "Preparing for search"] as const;

const PHASE_OF_STEP: Record<string, number> = {
  parse: 0,
  metadata: 1,
  chunk: 1,
  summarize: 1,
  embed: 2,
  index: 2,
  validate: 2,
};

export type Tone = "neutral" | "progress" | "success" | "warning";

export type PaperDisplay = {
  label: string;
  tone: Tone;
  // Index into PHASES of the phase under way, -1 before the first one starts.
  phase: number;
};

type StatusFields = Pick<Paper, "status" | "processing_step">;

/** The one place that turns the server's status into words for the interface. */
export function displayStatus(paper: StatusFields): PaperDisplay {
  switch (paper.status) {
    case "UPLOADED":
      return { label: "Uploaded", tone: "neutral", phase: -1 };
    case "PROCESSING": {
      const phase = PHASE_OF_STEP[paper.processing_step ?? "parse"] ?? 0;
      return { label: PHASES[phase], tone: "progress", phase };
    }
    case "READY":
      return { label: "Ready", tone: "success", phase: PHASES.length };
    case "FAILED":
      return { label: "Needs attention", tone: "warning", phase: -1 };
  }
}

export function isInProgress(paper: Pick<Paper, "status">): boolean {
  return paper.status === "UPLOADED" || paper.status === "PROCESSING";
}

export type Recovery = "retry" | "replace" | "settings";

export type Failure = { title: string; hint: string; recovery: Recovery };

type FailureFields = Pick<Paper, "error_code" | "error">;

/** What went wrong with a paper, in the reader's terms, and the way out. */
export function failureOf(paper: FailureFields): Failure {
  const provider = providerProblem(paper.error_code, paper.error);
  if (provider) {
    return { title: provider.title, hint: provider.hint, recovery: provider.openSettings ? "settings" : "retry" };
  }
  switch (paper.error_code) {
    case "unreadable_pdf":
      return {
        title: "Couldn't read this PDF",
        hint: "The file appears to be damaged or password protected.",
        recovery: "replace",
      };
    case "scanned_pdf":
      return {
        title: "This PDF has no readable text",
        hint: "Scanned documents aren't supported yet. Try a version with selectable text.",
        recovery: "replace",
      };
    case "too_many_pages":
      return {
        title: "This PDF is too long",
        hint: paper.error ?? "The document has more pages than can be processed.",
        recovery: "replace",
      };
    case "parse_failed":
      return {
        title: "We couldn't fully understand this document",
        hint: "Your original PDF is safe.",
        recovery: "retry",
      };
    default:
      return {
        title: "Processing temporarily failed",
        hint: "Your original PDF is safe. Try again in a while.",
        recovery: "retry",
      };
  }
}
