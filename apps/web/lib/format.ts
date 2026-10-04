export function fileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "Wang et al." for three or more authors, the names themselves for fewer. */
export function authorLine(authors: string[]): string {
  if (authors.length === 0) return "";
  if (authors.length <= 2) return authors.join(" and ");
  const family = authors[0].trim().split(/\s+/).at(-1);
  return `${family} et al.`;
}

export function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

const DAY = 24 * 60 * 60 * 1000;

export function relativeDay(iso: string): string {
  const then = new Date(iso);
  const days = Math.floor((Date.now() - then.getTime()) / DAY);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
