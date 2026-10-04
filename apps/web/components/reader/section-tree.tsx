import type { Section } from "@/lib/types";

/** The paper's outline. Choosing a heading goes to its page. */
export function SectionTree({ sections, onOpen }: { sections: Section[]; onOpen: (section: Section) => void }) {
  if (sections.length === 0) {
    return <p className="text-sm text-muted-foreground">No section headings were found in this paper.</p>;
  }
  const top = Math.min(...sections.map((section) => section.level));
  return (
    <ul className="flex flex-col">
      {sections.map((section) => (
        <li key={section.id}>
          <button
            onClick={() => onOpen(section)}
            className="flex w-full items-baseline gap-2 rounded-md py-1 pr-1 text-left text-sm hover:bg-muted"
            style={{ paddingLeft: `${0.25 + (section.level - top) * 0.75}rem` }}
          >
            <span className="min-w-0 flex-1">{section.title}</span>
            <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{section.page}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
