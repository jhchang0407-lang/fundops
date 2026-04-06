/**
 * Prose formatting utilities for AI-generated text.
 *
 * Defense-in-depth: backend does primary cleaning via ProseSpec,
 * frontend catches anything that slipped through and handles citation
 * rendering (inline markdown links → footnote-style [N] markers).
 */

// Conversational chatter patterns to strip (defense-in-depth)
const CHATTER_PATTERNS = [
  /^-?\s*You told me.*$/gm,
  /^-?\s*I will treat (?:those|these|them).*$/gm,
  /^-?\s*I (?:won't|will not) repeat.*$/gm,
  /^(?:If you want,? I can|Which would you prefer|Would you like me to|Let me know if).*$/gm,
  /^-?\s*(?:Produce|Run|Build|Create) a (?:12|24|short|scenario).*(?:model|watchlist|table).*$/gm,
  /^(?:Quick note on|Important note about).*(?:verified|numbers|data).*$/gm,
  /^(?:If you want|Want me to|I can also).*$/gm,
];

/**
 * Convert inline markdown links to footnote-style citations.
 * [label](url) → label [N] with collected references.
 * Also strips conversational chatter lines.
 */
export function formatResearchProse(text: string): { body: string; references: string[] } {
  if (!text) return { body: '', references: [] };

  // Strip conversational chatter
  let cleaned = text;
  for (const p of CHATTER_PATTERNS) {
    cleaned = cleaned.replace(p, '');
  }

  // Convert inline markdown links to footnote citations
  const refs: string[] = [];
  const linkRe = /\(?\[([^\]]*?)\]\((https?:\/\/[^)]+)\)\)?/g;
  const body = cleaned.replace(linkRe, (_match, label, url) => {
    const idx = refs.indexOf(url);
    const refNum = idx >= 0 ? idx + 1 : refs.push(url);
    if (!label || label === url || label.length < 5) return `[${refNum}]`;
    return `${label} [${refNum}]`;
  });

  const finalBody = body.replace(/\n{3,}/g, '\n\n').trim();
  return { body: finalBody, references: refs };
}

/**
 * Extract hostname from URL for display in references section.
 */
export function urlHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url.slice(0, 40);
  }
}
