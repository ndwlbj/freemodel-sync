/** Data shapes shared by the channels, the prober, the ranker and the state file. Never hold a key. */
import type { FailureKind } from "../classify.ts";
import type { ChannelId } from "../spec.ts";

/** One free model from a channel's catalogue. */
export interface CatalogModel {
  provider: ChannelId;
  id: string;
  name: string;
  /** Context window in tokens; 0 when the catalogue does not say. */
  contextLength: number;
  /** Tool calling: true/false when the catalogue says, null when it does not (Groq). */
  tools: boolean | null;
  /** Accepted inputs as far as the catalogue says (text is always there). */
  input: Array<"text" | "image">;
  /** Largest completion the catalogue reports, if any. */
  maxTokens: number | null;
  /** `YYYY-MM-DD` when the free variant goes away, if announced. */
  expirationDate: string | null;
}

/** Outcome of one tiny probe request (field meanings as in Python's TestResult). */
export interface ProbeResult {
  /** `"<provider>|<model id>"`, as in the Python cache. */
  key: string;
  ok: boolean;
  ttftMs: number | null;
  totalMs: number | null;
  /** Redacted, at most 200 characters for HTTP errors. */
  error: string | null;
  statusCode: number | null;
  /** Unix seconds. */
  testedAt: number;
  failureKind: FailureKind | null;
  retryAfterS: number | null;
  rateLimitRemaining: number | null;
}

/** Free-request quota a channel reports for the key (OpenRouter's `/key`). */
export interface QuotaInfo {
  dailyFreeLimit: number | null;
  dailyFreeUsed: number | null;
  dailyFreeRemaining: number | null;
}

export function modelKey(model: Pick<CatalogModel, "provider" | "id">): string {
  return `${model.provider}|${model.id}`;
}

/** Thrown by discovery when the catalogue cannot be read; the message is safe to store. */
export class ChannelError extends Error {
  override name = "ChannelError";
}
