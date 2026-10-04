"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, messageOf } from "@/lib/api-client";
import type { Paper } from "@/lib/types";

/** Corrects what was read from the PDF when it was read wrong. */
export function MetadataDialog({
  paper,
  onClose,
  onSaved,
}: {
  // null keeps the dialog closed.
  paper: Paper | null;
  onClose: () => void;
  onSaved: (paper: Paper) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!paper) return;
    const form = new FormData(event.currentTarget);
    const year = String(form.get("year") ?? "").trim();
    setBusy(true);
    try {
      const saved = await api<Paper>(`/papers/${paper.id}`, {
        method: "PATCH",
        json: {
          title: String(form.get("title") ?? "").trim(),
          authors: String(form.get("authors") ?? "")
            .split("\n")
            .map((name) => name.trim())
            .filter(Boolean),
          year: year ? Number(year) : null,
          doi: String(form.get("doi") ?? "").trim() || null,
        },
      });
      onSaved(saved);
      onClose();
    } catch (error) {
      toast.error(messageOf(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={paper !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Paper information</DialogTitle>
          <DialogDescription>Correct anything that was read wrong from the PDF.</DialogDescription>
        </DialogHeader>
        {paper && (
          // Keyed so the fields start from the paper being edited, not the one before it.
          <form key={paper.id} onSubmit={save} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="paper-title">Title</Label>
              <Input id="paper-title" name="title" defaultValue={paper.title} required maxLength={1000} />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="paper-authors">Authors</Label>
              <Textarea id="paper-authors" name="authors" defaultValue={paper.authors.join("\n")} rows={4} />
              <p className="text-xs text-muted-foreground">One name per line, in the order they appear.</p>
            </div>
            <div className="grid grid-cols-[7rem_1fr] gap-3">
              <div className="flex flex-col gap-2">
                <Label htmlFor="paper-year">Year</Label>
                <Input
                  id="paper-year"
                  name="year"
                  type="number"
                  min={1000}
                  max={2100}
                  defaultValue={paper.year ?? ""}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="paper-doi">DOI</Label>
                <Input id="paper-doi" name="doi" defaultValue={paper.doi ?? ""} maxLength={255} />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? "Saving…" : "Save"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
