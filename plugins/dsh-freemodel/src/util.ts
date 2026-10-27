/**
 * Small value helpers that mirror the Python package's parsing exactly, so
 * both implementations read the same catalogue and header values the same way
 * (the golden cases in spec/conformance/ check this).
 */

const FLOAT_RE = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;
const SPECIAL_RE = /^([+-]?)(inf|infinity|nan)$/i;
const INT_RE = /^[+-]?\d+$/;

/**
 * Python's `float(value)` as the Python side uses it (`_as_float`): numbers,
 * numeric strings (surrounding whitespace allowed, also `inf`/`nan`) and
 * booleans; anything else gives `null`.
 */
export function asFloat(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return value;
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (FLOAT_RE.test(text)) return Number(text);
  const special = SPECIAL_RE.exec(text);
  if (special !== null) {
    if (special[2]!.toLowerCase() === "nan") return Number.NaN;
    return special[1] === "-" ? -Infinity : Infinity;
  }
  return null;
}

/**
 * Python's `_as_int`: an integer, also from integral decimal strings such as
 * `"0.0"`; booleans and non-integral values give `null`.
 */
export function asInt(value: unknown): number | null {
  if (value === null || value === undefined || typeof value === "boolean") return null;
  if (typeof value === "number") return Number.isFinite(value) ? Math.trunc(value) : null;
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (INT_RE.test(text)) return Number.parseInt(text, 10);
  const number = asFloat(text);
  return number !== null && Number.isInteger(number) ? number : null;
}

/** Python truthiness of a JSON value. */
export function truthy(value: unknown): boolean {
  if (value === null || value === undefined || value === false || value === 0 || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Python's `fnmatch.fnmatchcase(name, pattern)`: `*`, `?`, `[seq]`, `[!seq]`,
 * matched against the whole string, case-sensitively.
 */
export function fnmatchcase(name: string, pattern: string): boolean {
  return globRegExp(pattern).test(name);
}

const globCache = new Map<string, RegExp>();

function escapeRegExp(text: string): string {
  return text.replace(/[\\^$.*+?()[\]{}|/-]/g, "\\$&");
}

function globRegExp(pattern: string): RegExp {
  const cached = globCache.get(pattern);
  if (cached !== undefined) return cached;
  let out = "";
  let i = 0;
  const n = pattern.length;
  while (i < n) {
    const c = pattern[i]!;
    i += 1;
    if (c === "*") {
      out += "[\\s\\S]*";
    } else if (c === "?") {
      out += "[\\s\\S]";
    } else if (c === "[") {
      let j = i;
      if (j < n && pattern[j] === "!") j += 1;
      if (j < n && pattern[j] === "]") j += 1;
      while (j < n && pattern[j] !== "]") j += 1;
      if (j >= n) {
        out += "\\[";
      } else {
        let body = pattern.slice(i, j);
        i = j + 1;
        let negate = false;
        if (body.startsWith("!")) {
          negate = true;
          body = body.slice(1);
        }
        // Keep ranges (a-z); escape everything else that is special inside a class.
        const cls = body.replace(/[\\\]^[]/g, "\\$&");
        out += negate ? `[^${cls}]` : `[${cls}]`;
      }
    } else {
      out += escapeRegExp(c);
    }
  }
  const re = new RegExp(`^${out}$`);
  globCache.set(pattern, re);
  return re;
}

/** Case-insensitive header lookup over a Fetch `Headers` or a plain object. */
export type HeaderSource = Headers | Readonly<Record<string, string | undefined>>;

export function headerOf(headers: HeaderSource, name: string): string | null {
  if (typeof (headers as Headers).get === "function") return (headers as Headers).get(name);
  const wanted = name.toLowerCase();
  for (const [key, value] of Object.entries(headers as Record<string, string | undefined>)) {
    if (key.toLowerCase() === wanted && value !== undefined) return value;
  }
  return null;
}

/** Whole days from `today` to `date` (both `YYYY-MM-DD`), like Python's `(date - today).days`. */
export function daysBetween(today: string, date: string): number {
  return Math.round((dayNumber(date) - dayNumber(today)) / 86_400_000);
}

function dayNumber(iso: string): number {
  const [y, m, d] = iso.split("-").map((p) => Number.parseInt(p, 10));
  return Date.UTC(y!, m! - 1, d!);
}

/** Today's date (`YYYY-MM-DD`) in UTC, the day boundary free-request limits use. */
export function utcToday(now: number = Date.now()): string {
  return new Date(now).toISOString().slice(0, 10);
}
