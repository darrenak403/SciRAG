// Turns the source markers of an answer into links the renderer can make into buttons.

// [S1], and the grouped form models also write: [S1, S2]. The same as the server's rule.
const MARKERS = /\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\]/g;
const ID = /S\d+/g;
// Fenced blocks and inline code: what is inside is quoted text, not a citation.
const CODE = /```[\s\S]*?(?:```|$)|`[^`\n]*`/g;

export const CITATION_HREF = "#source-";

function link(prose: string): string {
  return prose.replace(MARKERS, (group) =>
    (group.match(ID) ?? []).map((marker) => `[${marker}](${CITATION_HREF}${marker})`).join(""),
  );
}

/** The answer as markdown in which every marker is a link to "#source-S1". Code is left as it is. */
export function linkCitations(text: string): string {
  let result = "";
  let position = 0;
  for (const code of text.matchAll(CODE)) {
    result += link(text.slice(position, code.index)) + code[0];
    position = code.index + code[0].length;
  }
  return result + link(text.slice(position));
}
