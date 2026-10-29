/**
 * Shared base for channels with an OpenAI-compatible API: bearer auth and
 * the streaming probe (`POST {baseURL}/chat/completions` with `stream: true`)
 * that measures time to first token and classifies failures. A line-by-line
 * port of `freemodel_sync.providers.openai_compat.OpenAICompatProvider.test`.
 */
import { type Classifier, classifierFor, classifyStreamError, errorObjectOf, type FailureKind } from "../classify.ts";
import { type ChannelId, providerSpec } from "../spec.ts";
import { asFloat, asInt, type HeaderSource, headerOf, isRecord } from "../util.ts";
import type { CatalogModel, ProbeResult, QuotaInfo } from "./types.ts";
import { modelKey } from "./types.ts";

/** Completion budget of a probe; some upstreams reject very small values. */
export const DEFAULT_PROBE_MAX_TOKENS = 16;
/** Longest wait honoured from Retry-After / X-RateLimit-Reset. */
export const MAX_RETRY_AFTER_S = 24 * 3600;
/** A probe may take `timeout * 2` in total before its first token. */
const PROBE_DEADLINE_FACTOR = 2;

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface ProbeOptions {
  /** Per-read timeout in seconds (default 30). */
  timeoutS?: number;
  maxTokens?: number;
  signal?: AbortSignal;
}

interface ProbeSpec {
  path: string;
  maxTokensParam: string;
  defaultMaxTokens: number;
  prompt: string;
}

/** Default rate-limit hints: Retry-After in seconds (capped at 24 h), no remaining count. */
export function retryAfterHint(headers: HeaderSource): [number | null, number | null] {
  const raw = headerOf(headers, "retry-after");
  if (!raw) return [null, null];
  const value = asFloat(raw);
  if (value === null) return [null, null];
  return [Math.min(Math.max(0, value), MAX_RETRY_AFTER_S), null];
}

const now = (): number => performance.now();

export abstract class OpenAICompatChannel {
  abstract readonly id: ChannelId;
  readonly fetch: FetchLike;

  constructor(fetchImpl?: FetchLike) {
    this.fetch = fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  get baseURL(): string {
    return providerSpec(this.id).baseURL;
  }

  protected get probeSpec(): ProbeSpec {
    return providerSpec(this.id).probe as ProbeSpec;
  }

  get maxTokensParam(): string {
    return this.probeSpec.maxTokensParam;
  }

  /** Non-200 status -> failure kind (the channel's `errorMap`). */
  get classify(): Classifier {
    return classifierFor(this.id);
  }

  classifyStreamError(code: number | null, error: unknown): FailureKind {
    return classifyStreamError(code, error, this.classify);
  }

  rateLimitHints(headers: HeaderSource): [number | null, number | null] {
    return retryAfterHint(headers);
  }

  authHeaders(apiKey: string): Record<string, string> {
    return { Authorization: `Bearer ${apiKey}` };
  }

  /**
   * The channel's free models; throws `ChannelError` when the catalogue cannot be read.
   * `allowlist` is only used by channels with an optional configured model list.
   */
  abstract discover(
    apiKey: string | undefined,
    signal?: AbortSignal,
    allowlist?: readonly string[],
    modelQuotas?: Readonly<Record<string, number>>,
  ): Promise<CatalogModel[]>;

  /** Free-request quota for the key, when the channel reports one. */
  async quota(_apiKey: string, _signal?: AbortSignal): Promise<QuotaInfo | null> {
    return null;
  }

  /**
   * Send one tiny streaming chat completion and measure TTFT and latency.
   * Never throws; every failure is classified (see Python's `test()`).
   */
  async probe(model: CatalogModel, apiKey: string | undefined, options: ProbeOptions = {}): Promise<ProbeResult> {
    const key = modelKey(model);
    const base = {
      key,
      ttftMs: null,
      totalMs: null,
      statusCode: null,
      retryAfterS: null,
      rateLimitRemaining: null,
    };
    if (!apiKey) {
      return { ...base, ok: false, error: "missing api key", failureKind: "account", testedAt: Date.now() / 1000 };
    }
    const timeoutS = options.timeoutS ?? 30;
    const maxTokens = Math.max(1, Math.trunc(options.maxTokens ?? this.probeSpec.defaultMaxTokens ?? DEFAULT_PROBE_MAX_TOKENS));
    const payload = {
      model: model.id,
      messages: [{ role: "user", content: this.probeSpec.prompt }],
      [this.maxTokensParam]: maxTokens,
      stream: true,
    };

    const start = now();
    let statusCode: number | null = null;
    let ttftMs: number | null = null;
    let tokenSeen = false;
    let sawFinish = false;
    let doneAfterFinish = false;
    let error: string | null = null;
    let failureKind: FailureKind | null = null;
    let retryAfterS: number | null = null;
    let remaining: number | null = null;

    const controller = new AbortController();
    const onAbort = (): void => controller.abort(options.signal?.reason);
    options.signal?.addEventListener("abort", onAbort, { once: true });
    // Per-read idle timer (httpx's `timeout`) and the no-first-token deadline.
    let idle: NodeJS.Timeout | undefined;
    let timedOut: "idle" | "deadline" | undefined;
    const arm = (): void => {
      clearTimeout(idle);
      idle = setTimeout(() => {
        timedOut = "idle";
        controller.abort();
      }, timeoutS * 1000);
    };
    const deadlineMs = timeoutS * PROBE_DEADLINE_FACTOR * 1000;
    const deadline = setTimeout(() => {
      if (!tokenSeen) {
        timedOut = "deadline";
        controller.abort();
      }
    }, deadlineMs);
    const noTokenMessage = `no token within ${trimNumber(timeoutS * PROBE_DEADLINE_FACTOR)}s`;

    try {
      arm();
      const response = await this.fetch(`${this.baseURL}${this.probeSpec.path}`, {
        method: "POST",
        headers: { ...this.authHeaders(apiKey), "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      statusCode = response.status;
      [retryAfterS, remaining] = this.rateLimitHints(response.headers);
      if (statusCode !== 200) {
        let body = "";
        try {
          body = await response.text();
        } catch {
          body = "";
        }
        const errorObj = errorObjectOf(body);
        const message = errorObj.message;
        const text = (message ? String(message) : body.trim()).slice(0, 200) || `HTTP ${statusCode}`;
        return {
          key,
          ok: false,
          ttftMs: null,
          totalMs: now() - start,
          error: text,
          statusCode,
          testedAt: Date.now() / 1000,
          failureKind: this.classify(statusCode, errorObj),
          retryAfterS,
          rateLimitRemaining: remaining,
        };
      }
      outer: for await (const line of sseLines(response, arm)) {
        if (!tokenSeen && now() - start > deadlineMs) {
          error = noTokenMessage;
          failureKind = "transient";
          break;
        }
        const stripped = line.trim();
        if (!stripped.startsWith("data:")) continue;
        const data = stripped.slice(5).trim();
        if (data === "[DONE]") {
          if (sawFinish) doneAfterFinish = true;
          continue;
        }
        let chunk: unknown;
        try {
          chunk = JSON.parse(data);
        } catch {
          continue;
        }
        if (!isRecord(chunk)) continue;
        const err = chunk.error;
        if (isPyTruthy(err)) {
          if (isRecord(err)) {
            error = String(err.message || err.code || JSON.stringify(err));
            failureKind = this.classifyStreamError(asInt(err.code), err);
          } else {
            error = String(err);
            failureKind = this.classifyStreamError(null, {});
          }
          break;
        }
        const choices = chunk.choices;
        if (!Array.isArray(choices) || choices.length === 0) continue;
        const choice = isRecord(choices[0]) ? choices[0] : {};
        const delta = choice.delta;
        if (isRecord(delta)) {
          const content = delta.content || delta.reasoning;
          if (content) {
            tokenSeen = true;
            if (ttftMs === null) ttftMs = now() - start;
          }
        }
        const finish = choice.finish_reason;
        if (finish !== null && finish !== undefined) {
          sawFinish = true;
          if (finish === "error") {
            error = "stream ended with finish_reason 'error'";
            failureKind = "transient";
            break outer;
          }
          if (finish === "content_filter") {
            error = "stream ended with finish_reason 'content_filter'";
            failureKind = "model";
            break outer;
          }
        }
      }
    } catch (caught) {
      if (timedOut === "deadline") {
        error = noTokenMessage;
      } else if (timedOut === "idle") {
        error = `ReadTimeout: no data within ${trimNumber(timeoutS)}s`;
      } else {
        const e = caught as { name?: string; message?: string };
        error = `${e?.name ?? "Error"}: ${e?.message ?? String(caught)}`;
      }
      failureKind = "transient";
    } finally {
      clearTimeout(idle);
      clearTimeout(deadline);
      options.signal?.removeEventListener("abort", onAbort);
      controller.abort();
    }

    const totalMs = now() - start;
    const ok = statusCode === 200 && error === null && (tokenSeen || doneAfterFinish);
    if (!ok && failureKind === null) {
      failureKind = "model";
      if (error === null) error = "empty response";
    }
    return {
      key,
      ok,
      ttftMs,
      totalMs,
      error,
      statusCode,
      testedAt: Date.now() / 1000,
      failureKind: ok ? null : failureKind,
      retryAfterS,
      rateLimitRemaining: remaining,
    };
  }

  /** GET a JSON document; throws with a short, key-free message. */
  protected async getJson(path: string, headers: Record<string, string>, signal?: AbortSignal): Promise<unknown> {
    const init: RequestInit = { headers: { Accept: "application/json", ...headers } };
    if (signal !== undefined) init.signal = signal;
    const response = await this.fetch(`${this.baseURL}${path}`, init);
    if (!response.ok) throw new HttpStatusError(response.status);
    return (await response.json()) as unknown;
  }
}

export class HttpStatusError extends Error {
  override name = "HttpStatusError";
  constructor(readonly status: number) {
    super(`HTTP ${status}`);
  }
}

function isPyTruthy(value: unknown): boolean {
  if (value === null || value === undefined || value === false || value === 0 || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (isRecord(value)) return Object.keys(value).length > 0;
  return true;
}

function trimNumber(n: number): string {
  return Number.isInteger(n) ? String(n) : String(Number(n.toPrecision(6)));
}

/** Split a streaming body into lines (`\n`, `\r\n` or `\r`), re-arming the idle timer on every read. */
async function* sseLines(response: Response, onRead: () => void): AsyncGenerator<string> {
  if (response.body === null) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      onRead();
      buffer += decoder.decode(value, { stream: true });
      let match: RegExpExecArray | null;
      const re = /\r\n|\n|\r(?!$)/g;
      let last = 0;
      while ((match = re.exec(buffer)) !== null) {
        yield buffer.slice(last, match.index);
        last = match.index + match[0].length;
      }
      buffer = buffer.slice(last);
    }
    buffer += decoder.decode();
    if (buffer.length > 0) {
      for (const line of buffer.split(/\r\n|\n|\r/)) yield line;
    }
  } finally {
    reader.releaseLock?.();
  }
}
