// Prepares a model's answer for the markdown renderer: source markers become links the
// renderer makes into buttons, and formulas get the delimiters it understands.

// [S1], and the grouped form models also write: [S1, S2]. The same as the server's rule.
const MARKERS = /\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\]/g;
const ID = /S\d+/g;
// Fenced blocks and inline code: what is inside is quoted text, not a citation.
const CODE = /```[\s\S]*?(?:```|$)|`[^`\n]*`/g;

export const CITATION_HREF = "#source-";

// Models write formulas as \( … \) and \[ … \]. Markdown takes those backslashes for
// escapes and drops them, so they are rewritten to the dollar form before it sees them.
const INLINE_MATH = /\\\(([\s\S]+?)\\\)/g;
const DISPLAY_MATH = /\\\[([\s\S]+?)\\\]/g;

function prepare(prose: string): string {
  return prose
    // Kept on one line, in place: inside a list item a block of its own would end the list.
    // Two dollars still set it as a displayed formula.
    .replace(DISPLAY_MATH, (_, formula: string) => `$$${formula.trim().replace(/\s*\n\s*/g, " ")}$$`)
    .replace(INLINE_MATH, (_, formula: string) => `$${formula.trim()}$`)
    .replace(MARKERS, (group) =>
      (group.match(ID) ?? []).map((marker) => `[${marker}](${CITATION_HREF}${marker})`).join(""),
    );
}

/**
 * The answer as markdown in which every marker is a link to "#source-S1" and every
 * formula is between dollar signs. Code is left as it is.
 */
export function answerMarkdown(text: string): string {
  let result = "";
  let position = 0;
  for (const code of text.matchAll(CODE)) {
    result += prepare(text.slice(position, code.index)) + code[0];
    position = code.index + code[0].length;
  }
  return result + prepare(text.slice(position));
}
