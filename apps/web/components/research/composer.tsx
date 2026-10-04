"use client";

import { ArrowUp, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The question box. Enter sends; Shift+Enter starts a new line. */
export function Composer({
  value,
  onChange,
  onSend,
  onStop,
  streaming = false,
  disabled = false,
  placeholder,
  autoFocus,
  children,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  // Given while an answer is being written: the send button becomes a stop button.
  onStop?: () => void;
  streaming?: boolean;
  disabled?: boolean;
  placeholder: string;
  autoFocus?: boolean;
  // What sits under the text: the source selector and the like.
  children?: React.ReactNode;
  className?: string;
}) {
  const canSend = value.trim().length > 0 && !disabled && !streaming;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSend();
      }}
      className={cn(
        "flex flex-col gap-1 rounded-xl border bg-background p-2 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50",
        className,
      )}
    >
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            if (canSend) onSend();
          }
        }}
        placeholder={placeholder}
        aria-label={placeholder}
        autoFocus={autoFocus}
        rows={2}
        maxLength={4000}
        className="field-sizing-content max-h-48 min-h-12 w-full resize-none bg-transparent px-2 py-1 text-sm outline-none placeholder:text-muted-foreground"
      />
      <div className="flex items-center gap-1">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">{children}</div>
        {streaming && onStop ? (
          <Button type="button" size="icon" variant="outline" onClick={onStop} aria-label="Stop generating">
            <Square className="fill-current" />
          </Button>
        ) : (
          <Button type="submit" size="icon" disabled={!canSend} aria-label="Send question">
            <ArrowUp />
          </Button>
        )}
      </div>
    </form>
  );
}
