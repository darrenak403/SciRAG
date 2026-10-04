"use client";

import { ArrowDown } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function DropZone({
  onFiles,
  inputRef,
  compact = false,
}: {
  onFiles: (files: File[]) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  compact?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  // dragenter and dragleave also fire for every child the pointer crosses.
  const depth = useRef(0);

  return (
    <div
      onDragEnter={(event) => {
        event.preventDefault();
        depth.current += 1;
        setDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => {
        depth.current -= 1;
        if (depth.current <= 0) setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        depth.current = 0;
        setDragging(false);
        onFiles(Array.from(event.dataTransfer.files));
      }}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed text-center transition-colors",
        compact ? "px-4 py-5" : "px-4 py-12",
        dragging ? "border-citation bg-citation/5" : "border-border",
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        className="sr-only"
        aria-label="Choose PDF files"
        onChange={(event) => {
          onFiles(Array.from(event.target.files ?? []));
          // So choosing the same file again fires a change.
          event.target.value = "";
        }}
      />
      {dragging ? (
        <p className="py-3 text-sm font-medium">Release to add</p>
      ) : (
        <>
          {!compact && <ArrowDown className="size-5 text-muted-foreground" aria-hidden />}
          <p className="text-sm font-medium">Drop PDFs here</p>
          <Button variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
            Choose files
          </Button>
          <p className="text-xs text-muted-foreground">PDF · Multiple files supported</p>
        </>
      )}
    </div>
  );
}
