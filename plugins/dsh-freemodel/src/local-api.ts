/**
 * The plugin's local HTTP surface, mounted under `/freemodel/api` when the
 * host's web server is present.
 *
 * Every route is loopback-only: the state of the picker is local data, and a
 * write can spend a free request. Writes (`POST /refresh`, `POST /test`) also
 * require a secret in `x-freemodel-secret` (or `Authorization: Bearer ...`),
 * so a page the user happens to visit cannot trigger them through the local
 * web server. The on-disk secret is never returned by any route and never
 * logged. The status document does carry a separate process-local
 * {@link LocalApiDeps.clientKey} so the loopback settings card can call the
 * write routes; it is rotated on restart and is not accepted from non-loopback
 * peers.
 *
 * Routes:
 * - `GET  /freemodel/api/status` — current status report (and the card's write token).
 * - `POST /freemodel/api/refresh` — refresh every active channel now.
 * - `POST /freemodel/api/test` — body `{ channel, model }`, probe one model.
 */
import { randomBytes, timingSafeEqual } from "node:crypto";
import { chmodSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { dirname } from "node:path";
import { REFRESH_PATH, SECRET_HEADER, STATUS_PATH, TEST_PATH } from "./api-paths.ts";
import { CHANNEL_IDS, type ChannelId } from "./spec.ts";

export { API_PREFIX, SECRET_HEADER } from "./api-paths.ts";
/** Environment variable that overrides the generated secret. */
export const SECRET_ENV = "FREEMODEL_API_SECRET";
/** Minimum accepted secret length (a generated one is 64 hex characters). */
export const MIN_SECRET_LENGTH = 16;
/** Refuse bodies larger than this; the only bodies are two short fields. */
const MAX_BODY_BYTES = 64 * 1024;

export interface LocalApiStatus {
  /** Any JSON-serialisable status report; it must never contain a key. */
  status: unknown;
}

/** One manual probe result as the API returns it. */
export interface ManualTestResponse {
  channel: ChannelId;
  model: string;
  result: unknown;
}

export interface LocalApiDeps {
  /** Build the status report (the CLI's `status --json` shape). */
  status: () => Promise<unknown> | unknown;
  /** Refresh catalogues and probes now. */
  refresh: () => Promise<void>;
  /** Probe one model of one channel and persist the result. */
  testModel: (channel: ChannelId, model: string) => Promise<ManualTestResponse>;
  /** Write secret; accept a value or a getter so a reload can rotate it. */
  secret: string | (() => string);
  /**
   * A second, process-local token handed to the settings card through the
   * loopback `GET /status` document. It authorizes the same writes as
   * {@link secret} but is not the secret on disk: a page can lose it on reload
   * without invalidating the CLI/API secret, and the secret itself is never
   * returned by any route.
   */
  clientKey?: string | (() => string);
  /** Peer admission, default {@link isLoopbackAddress}; injectable for tests. */
  isLoopback?: (req: IncomingMessage) => boolean;
  logger?: { warn(message: string, ...args: unknown[]): void };
}

type Json = Record<string, unknown>;

function valueOf(value: string | (() => string)): string {
  return typeof value === "function" ? value() : value;
}

function secretOf(deps: LocalApiDeps): string {
  return valueOf(deps.secret);
}

function clientKeyOf(deps: LocalApiDeps): string | undefined {
  return deps.clientKey === undefined ? undefined : valueOf(deps.clientKey);
}

/** IPv4 127/8, IPv6 `::1`, and the IPv4-mapped forms Node reports for them. */
export function isLoopbackAddress(address: string | undefined): boolean {
  if (address === undefined || address === "") return false;
  const lower = address.toLowerCase();
  const mapped = lower.startsWith("::ffff:") ? lower.slice("::ffff:".length) : lower;
  if (mapped === "::1" || mapped === "0:0:0:0:0:0:0:1") return true;
  // Some platforms report the IPv4-mapped IPv6 form as two hex groups.
  if (mapped === "7f00:1") return true;
  return /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(mapped);
}

/** Constant-time comparison; a missing or differently sized value fails. */
export function secretMatches(expected: string, presented: string | undefined): boolean {
  if (presented === undefined || expected === "") return false;
  const a = Buffer.from(expected, "utf8");
  const b = Buffer.from(presented, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

/** The secret a request presents, from the dedicated header or a bearer token. */
export function presentedSecret(req: Pick<IncomingMessage, "headers">): string | undefined {
  const header = req.headers[SECRET_HEADER];
  if (typeof header === "string" && header !== "") return header;
  const authorization = req.headers.authorization;
  if (typeof authorization === "string" && authorization.startsWith("Bearer ")) {
    const token = authorization.slice("Bearer ".length);
    return token === "" ? undefined : token;
  }
  return undefined;
}

/** A fresh 256-bit secret as 64 hex characters. */
export function generateSecret(): string {
  return randomBytes(32).toString("hex");
}

/**
 * Read the secret from `FREEMODEL_API_SECRET`, else from a 0600 file, else
 * create that file with a random secret. A too-short environment value is an
 * error rather than a silently weak fence.
 * @param path - secret file path (normally beside the state file).
 * @param env - environment to read.
 * @param entropy - random source, injectable for tests.
 */
export function loadOrCreateSecret(path: string, env: NodeJS.ProcessEnv = process.env, entropy: (size: number) => Buffer = randomBytes): string {
  const fromEnv = env[SECRET_ENV];
  if (fromEnv !== undefined && fromEnv !== "") {
    if (fromEnv.length < MIN_SECRET_LENGTH) {
      throw new Error(`${SECRET_ENV} must be at least ${MIN_SECRET_LENGTH} characters`);
    }
    return fromEnv;
  }
  try {
    const existing = readFileSync(path, "utf8").trim();
    if (existing.length >= MIN_SECRET_LENGTH) return existing;
  } catch {
    // absent or unreadable: create a new one
  }
  const secret = entropy(32).toString("hex");
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  writeFileSync(path, `${secret}\n`, { mode: 0o600 });
  try {
    chmodSync(path, 0o600);
  } catch {
    // best effort on platforms without POSIX modes
  }
  return secret;
}

function sendJson(res: ServerResponse, status: number, body: Json): void {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(data),
  });
  res.end(data);
}

function errorBody(code: string, message: string): Json {
  return { ok: false, error: { code, message } };
}

class BodyError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk as string);
    size += buffer.length;
    if (size > MAX_BODY_BYTES) throw new BodyError(413, "body-too-large", "request body too large");
    chunks.push(buffer);
  }
  if (size === 0) return undefined;
  const text = Buffer.concat(chunks).toString("utf8");
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new BodyError(400, "invalid-json", "body is not valid JSON");
  }
}

/** HTTP status for a refusal raised by the service (manual probes). */
function refusal(error: unknown): { status: number; code: string } | null {
  const code = (error as { code?: unknown } | null)?.code;
  if (typeof code !== "string") return null;
  if (code === "model-not-found") return { status: 404, code };
  if (
    code === "channel-disabled" ||
    code === "free-plan-unconfirmed" ||
    code === "token-plan-unconfirmed" ||
    code === "free-quota-guard-unconfirmed" ||
    code === "models-empty" ||
    code === "no-key"
  ) {
    return { status: 409, code };
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isChannelId(value: unknown): value is ChannelId {
  return typeof value === "string" && (CHANNEL_IDS as readonly string[]).includes(value);
}

function methodOf(req: IncomingMessage): string {
  return (req.method ?? "GET").toUpperCase();
}

/**
 * Build the route handler.
 * @param deps - status/refresh/test callbacks and the write secret.
 * @returns an async handler owning the full response.
 */
export function createLocalApiHandler(deps: LocalApiDeps): (req: IncomingMessage, res: ServerResponse) => Promise<void> {
  return async (req, res) => {
    const peerAllowed = deps.isLoopback ?? ((request: IncomingMessage) => isLoopbackAddress(request.socket.remoteAddress));
    if (!peerAllowed(req)) {
      sendJson(res, 403, errorBody("forbidden", "the freemodel API is available on loopback only"));
      return;
    }

    const url = new URL(req.url ?? "/", "http://localhost");
    const path = url.pathname;
    if (path !== STATUS_PATH && path !== REFRESH_PATH && path !== TEST_PATH) {
      sendJson(res, 404, errorBody("not-found", `unknown freemodel API route: ${path}`));
      return;
    }

    const method = methodOf(req);
    const writing = path !== STATUS_PATH;
    if (writing) {
      if (method !== "POST") {
        res.setHeader("allow", "POST");
        sendJson(res, 405, errorBody("method-not-allowed", "use POST for this route"));
        return;
      }
      const expected = secretOf(deps);
      const clientKey = clientKeyOf(deps);
      if (expected === "" && (clientKey === undefined || clientKey === "")) {
        sendJson(res, 503, errorBody("secret-unavailable", "the freemodel API secret is not configured"));
        return;
      }
      const presented = presentedSecret(req);
      const accepted =
        (expected !== "" && secretMatches(expected, presented)) ||
        (clientKey !== undefined && clientKey !== "" && secretMatches(clientKey, presented));
      if (!accepted) {
        sendJson(res, 401, errorBody("unauthorized", `a valid ${SECRET_HEADER} header is required`));
        return;
      }
    } else if (method !== "GET") {
      res.setHeader("allow", "GET");
      sendJson(res, 405, errorBody("method-not-allowed", "use GET for this route"));
      return;
    }

    try {
      if (path === STATUS_PATH) {
        const clientKey = clientKeyOf(deps);
        sendJson(res, 200, {
          ok: true,
          status: await deps.status(),
          ...(clientKey === undefined || clientKey === "" ? {} : { writeToken: clientKey }),
        });
        return;
      }
      if (path === REFRESH_PATH) {
        await deps.refresh();
        sendJson(res, 200, { ok: true, status: await deps.status() });
        return;
      }
      const body = await readJson(req);
      if (!isRecord(body)) {
        sendJson(res, 400, errorBody("invalid-body", "expected a JSON object with channel and model"));
        return;
      }
      const channel = body.channel;
      const model = body.model;
      if (!isChannelId(channel)) {
        sendJson(res, 400, errorBody("invalid-channel", `channel must be one of: ${CHANNEL_IDS.join(", ")}`));
        return;
      }
      if (typeof model !== "string" || model.trim() === "" || model.length > 256) {
        sendJson(res, 400, errorBody("invalid-model", "model must be a non-empty model id (at most 256 characters)"));
        return;
      }
      const tested = await deps.testModel(channel, model.trim());
      sendJson(res, 200, { ok: true, channel: tested.channel, model: tested.model, result: tested.result });
    } catch (error) {
      if (error instanceof BodyError) {
        sendJson(res, error.status, errorBody(error.code, error.message));
        return;
      }
      const refused = refusal(error);
      if (refused !== null) {
        const message = error instanceof Error ? error.message : String(error);
        sendJson(res, refused.status, errorBody(refused.code, message));
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      deps.logger?.warn(`dsh-freemodel: local API ${path} failed: ${message}`);
      sendJson(res, 500, errorBody("internal-error", message));
    }
  };
}