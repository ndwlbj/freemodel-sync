/**
 * Browser-side client for the plugin's loopback HTTP surface.
 *
 * `GET /freemodel/api/status` is free to read but only from loopback. The
 * write routes need the token that status hands to this same-origin card; the
 * token is kept in memory only (never localStorage), and the on-disk API
 * secret is never part of any response.
 */
import { SECRET_HEADER, STATUS_PATH, TEST_PATH } from "../api-paths.ts";
import {
  type ChannelId,
  isChannelId,
  isRecord,
  type ManualTestView,
  type ProbeResultView,
  type StatusEnvelope,
  type StatusReport,
  type TestEnvelope,
} from "./types.ts";

export interface ResponseLike {
  readonly ok: boolean;
  readonly status: number;
  json(): Promise<unknown>;
}

export interface RequestInitLike {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
}

export type FetchLike = (input: string, init?: RequestInitLike) => Promise<ResponseLike>;

/** A failed call with a machine-readable code and a message safe to display. */
export class LocalApiError extends Error {
  override name = "LocalApiError";
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function defaultFetch(): FetchLike {
  const candidate = (globalThis as { fetch?: unknown }).fetch;
  if (typeof candidate !== "function") {
    throw new LocalApiError("no-fetch", "this browser has no fetch(); the freemodel card cannot read the local API");
  }
  return candidate.bind(globalThis) as FetchLike;
}

function errorFrom(body: unknown, status: number): LocalApiError {
  if (isRecord(body) && isRecord(body.error)) {
    const code = typeof body.error.code === "string" ? body.error.code : "http-error";
    const message = typeof body.error.message === "string" ? body.error.message : `request failed with HTTP ${status}`;
    return new LocalApiError(code, message, status);
  }
  return new LocalApiError("http-error", `request failed with HTTP ${status}`, status);
}

function statusOf(body: unknown): StatusReport {
  if (!isRecord(body) || body.ok !== true || !isRecord(body.status)) {
    throw new LocalApiError("bad-status", "the freemodel status route returned an unexpected document");
  }
  return body.status as unknown as StatusReport;
}

function probeResultOf(value: unknown): ProbeResultView {
  if (!isRecord(value)) throw new LocalApiError("bad-result", "the probe result was not an object");
  return {
    ok: value.ok === true,
    ttftMs: typeof value.ttftMs === "number" ? value.ttftMs : null,
    error: typeof value.error === "string" ? value.error : null,
    ...(typeof value.statusCode === "number" || value.statusCode === null ? { statusCode: value.statusCode } : {}),
    ...(typeof value.failureKind === "string" || value.failureKind === null ? { failureKind: value.failureKind } : {}),
    ...(typeof value.testedAt === "number" ? { testedAt: value.testedAt } : {}),
  };
}

export class FreemodelApiClient {
  #writeToken: string | undefined;

  constructor(
    private readonly fetchImpl: FetchLike = defaultFetch(),
    private readonly paths: { status: string; test: string } = { status: STATUS_PATH, test: TEST_PATH },
  ) {}

  /** Whether a write token is currently held (it is never exposed). */
  hasWriteToken(): boolean {
    return this.#writeToken !== undefined;
  }

  private async request(path: string, init?: RequestInitLike): Promise<unknown> {
    let response: ResponseLike;
    try {
      response = await this.fetchImpl(path, init);
    } catch (error) {
      throw new LocalApiError("network-error", error instanceof Error ? error.message : String(error));
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    if (!response.ok) throw errorFrom(body, response.status);
    return body;
  }

  /**
   * Read the status document and remember the card's write token.
   * @returns the status report.
   */
  async load(): Promise<StatusReport> {
    const body = (await this.request(this.paths.status)) as unknown;
    if (isRecord(body) && typeof body.writeToken === "string" && body.writeToken !== "") {
      this.#writeToken = body.writeToken;
    }
    return statusOf(body);
  }

  /**
   * Probe one model on demand.
   * @param channel - channel id from the status document.
   * @param model - exact catalogue model id.
   */
  async test(channel: ChannelId, model: string): Promise<ManualTestView> {
    if (!isChannelId(channel)) throw new LocalApiError("invalid-channel", `unknown channel: ${String(channel)}`);
    if (model.trim() === "") throw new LocalApiError("invalid-model", "model id is empty");
    if (this.#writeToken === undefined) await this.load();
    if (this.#writeToken === undefined) {
      throw new LocalApiError(
        "missing-write-token",
        "the local API did not hand this page a write token; reload the settings page",
      );
    }
    const body = (await this.request(this.paths.test, {
      method: "POST",
      headers: { [SECRET_HEADER]: this.#writeToken, "content-type": "application/json" },
      body: JSON.stringify({ channel, model }),
    })) as unknown;
    if (!isRecord(body) || body.ok !== true || !isChannelId(body.channel) || typeof body.model !== "string") {
      throw new LocalApiError("bad-test-response", "the freemodel test route returned an unexpected document");
    }
    return {
      channel: body.channel,
      model: body.model,
      result: probeResultOf(body.result),
    };
  }
}

/** Type guard used by tests and callers that parse an envelope themselves. */
export function isStatusEnvelope(value: unknown): value is StatusEnvelope {
  return isRecord(value) && value.ok === true && isRecord(value.status);
}

/** Type guard for the manual-test envelope. */
export function isTestEnvelope(value: unknown): value is TestEnvelope {
  return isRecord(value) && value.ok === true && isChannelId(value.channel) && typeof value.model === "string";
}