/**
 * Secret redaction for every text the plugin stores or logs (state file,
 * status, log lines): the exact key values in use, the key shapes from
 * spec/providers.json `keyPatterns`, and the generic shapes the Python
 * package masks (bearer tokens, Authorization headers, sk-/gsk_ keys).
 */
import { providersSpec } from "./spec.ts";

/** Values shorter than this are not replaced: it would mangle ordinary text. */
export const MIN_SECRET_LENGTH = 6;

const GENERIC: ReadonlyArray<readonly [RegExp, string]> = [
  [/(api\.telegram\.org\/bot)[^/\s"']+/g, "$1<redacted>"],
  [/(bearer\s+)[^\s"',;]+/gi, "$1<redacted>"],
  [/(authorization["']?\s*[:=]\s*["']?)(?!bearer\b)[^\s"',;]+/gi, "$1<redacted>"],
  [/\b(sk-or-)[A-Za-z0-9._-]{4,}/g, "$1<redacted>"],
  [/\b(sk-(?:ws|sp)-)[A-Za-z0-9._-]{4,}/g, "$1<redacted>"],
  [/\b(sk-)[A-Za-z0-9._-]{8,}/g, "$1<redacted>"],
  [/\b(gsk_)[A-Za-z0-9_-]{8,}/g, "$1<redacted>"],
];

interface KeyPattern {
  prefix: string;
  regex: string;
}

function specPatterns(): Array<readonly [RegExp, string]> {
  const out: Array<readonly [RegExp, string]> = [];
  for (const entry of Object.values(providersSpec.providers)) {
    for (const p of (entry.keyPatterns as KeyPattern[] | undefined) ?? []) {
      out.push([new RegExp(p.regex, "g"), `${p.prefix}<redacted>`]);
    }
  }
  return out;
}

const PATTERNS = [...specPatterns(), ...GENERIC];

/**
 * Mask the given secret values and every key-shaped string in `text`.
 * @param text - text that may reach a file or a log.
 * @param secrets - exact values to remove (the keys used by this operation).
 */
export function redact(text: string, secrets: Iterable<string | undefined> = []): string {
  const values = [...new Set([...secrets].filter((s): s is string => s !== undefined && s.length >= MIN_SECRET_LENGTH))].sort(
    (a, b) => b.length - a.length,
  );
  let out = text;
  for (const value of values) out = out.split(value).join("<redacted>");
  for (const [pattern, replacement] of PATTERNS) out = out.replace(pattern, replacement);
  return out;
}
