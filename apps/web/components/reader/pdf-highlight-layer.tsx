import type { Box } from "@/lib/types";

/**
 * Marks a passage on a page. The boxes are fractions of the page measured from its
 * top-left corner, so they are placed in percent and hold at any zoom.
 */
export function PdfHighlightLayer({ boxes }: { boxes: Box[] }) {
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden>
      {boxes.map(({ bbox: [left, top, right, bottom] }, index) => (
        <div
          key={index}
          className="absolute rounded-sm bg-citation/20 ring-1 ring-citation/60"
          style={{
            left: `${left * 100}%`,
            top: `${top * 100}%`,
            width: `${(right - left) * 100}%`,
            height: `${(bottom - top) * 100}%`,
          }}
        />
      ))}
    </div>
  );
}
