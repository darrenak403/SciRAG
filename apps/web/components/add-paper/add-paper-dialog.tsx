"use client";

import Link from "next/link";
import { useRef } from "react";

import { useAddPaper } from "@/components/add-paper/add-paper-provider";
import { DropZone } from "@/components/add-paper/drop-zone";
import { FileRow } from "@/components/add-paper/file-row";
import { ReadyActions } from "@/components/add-paper/ready-actions";
import { useSession } from "@/components/app-shell/session";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { plural } from "@/lib/format";
import { useProcessing } from "@/lib/processing-store";
import { providerProblem } from "@/lib/provider-errors";
import type { Paper } from "@/lib/types";

export function AddPaperDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { user } = useSession();
  const { items, started, addFiles, removeItem, start, reset } = useAddPaper();
  const processing = useProcessing();
  const input = useRef<HTMLInputElement>(null);

  const byId = new Map(processing.map((paper) => [paper.id, paper]));
  const uploaded = items.flatMap((item): Paper[] => {
    const paper = item.state === "uploaded" && item.paperId ? byId.get(item.paperId) : undefined;
    return paper ? [paper] : [];
  });
  const sending = items.some((item) => item.state === "waiting" || item.state === "uploading");
  const toAdd = items.filter((item) => item.state === "selected").length;
  const noProvider = providerProblem(user.active_connection_id ? null : "provider_not_configured");

  function close() {
    onOpenChange(false);
  }

  function changeOpen(next: boolean) {
    onOpenChange(next);
    // A finished batch is cleared when the dialog closes; one still uploading is kept.
    if (!next && started && !sending) reset();
  }

  // Starts a new batch with the file picker open. The papers of this one stay in the widget.
  function replace() {
    reset();
    input.current?.click();
  }

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Add papers</DialogTitle>
          <DialogDescription>
            {!started
              ? items.length === 0
                ? "Add scientific papers to your library."
                : `${plural(items.length, "file")} selected`
              : sending
                ? `Uploading ${plural(items.length, "paper")}`
                : "Upload complete"}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
          {noProvider && (
            <Alert>
              <AlertTitle>{noProvider.title}</AlertTitle>
              <AlertDescription>
                Papers can be uploaded now, but they can&apos;t be prepared for questions until you add your own
                key.{" "}
                <Link href="/settings" onClick={close} className="font-medium underline underline-offset-4">
                  Open settings
                </Link>
              </AlertDescription>
            </Alert>
          )}
          {/* Always mounted: the file input inside it is what "Try another file" opens. */}
          <div hidden={started}>
            <DropZone onFiles={addFiles} inputRef={input} compact={items.length > 0} />
          </div>
          {items.length > 0 && (
            <ul className="divide-y rounded-lg border">
              {items.map((item) => (
                <FileRow
                  key={item.key}
                  item={item}
                  paper={item.paperId ? byId.get(item.paperId) : undefined}
                  onRemove={() => removeItem(item.key)}
                  onReplace={replace}
                  onNavigate={close}
                />
              ))}
            </ul>
          )}
          {started && !sending && <ReadyActions papers={uploaded} onNavigate={close} />}
        </div>

        <DialogFooter>
          {!started ? (
            <>
              <Button variant="outline" onClick={() => changeOpen(false)}>
                Cancel
              </Button>
              <Button onClick={start} disabled={toAdd === 0}>
                {toAdd === 0 ? "Add papers" : `Add ${plural(toAdd, "paper")}`}
              </Button>
            </>
          ) : (
            <>
              {!sending && (
                <Button variant="outline" onClick={reset}>
                  Add more papers
                </Button>
              )}
              <Button variant={uploaded.length > 0 ? "outline" : "default"} onClick={() => changeOpen(false)}>
                Done
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
