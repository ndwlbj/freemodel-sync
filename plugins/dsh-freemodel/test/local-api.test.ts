import { chmodSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  API_PREFIX,
  createLocalApiHandler,
  generateSecret,
  isLoopbackAddress,
  loadOrCreateSecret,
  MIN_SECRET_LENGTH,
  SECRET_ENV,
  SECRET_HEADER,
  secretMatches,
} from "../src/local-api.ts";

const SECRET = "local-test-secret-0123456789";

function deps(overrides: Partial<Parameters<typeof createLocalApiHandler>[0]> = {}) {
  const status = vi.fn(async () => ({ plugin: "dsh-freemodel", channels: [] }));
  const refresh = vi.fn(async () => undefined);
  const testModel = vi.fn(async (channel: "openrouter" | "groq", model: string) => ({
    channel,
    model,
    result: { ok: true, ttftMs: 120, error: null },
  }));
  return { status, refresh, testModel, secret: SECRET, ...overrides };
}

async function serve(handler: ReturnType<typeof createLocalApiHandler>, fn: (base: string) => Promise<void>): Promise<void> {
  const server: Server = createServer((req, res) => {
    void handler(req, res);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as AddressInfo;
  try {
    await fn(`http://127.0.0.1:${address.port}`);
  } finally {
    await new Promise<void>((resolve, reject) => server.close((error) => (error === undefined ? resolve() : reject(error))));
  }
}

describe("local API", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("serves the status report over loopback without a secret", async () => {
    const d = deps();
    await serve(createLocalApiHandler(d), async (base) => {
      const response = await fetch(`${base}${API_PREFIX}/status`);
      expect(response.status).toBe(200);
      expect(response.headers.get("cache-control")).toBe("no-store");
      await expect(response.json()).resolves.toEqual({ ok: true, status: { plugin: "dsh-freemodel", channels: [] } });
    });
    expect(d.status).toHaveBeenCalledTimes(1);
    expect(d.refresh).not.toHaveBeenCalled();
    expect(d.testModel).not.toHaveBeenCalled();
  });

  it("hands the loopback card a process-local write token, never the on-disk secret", async () => {
    const clientKey = "card-write-token-0123456789";
    const d = deps({ clientKey });
    await serve(createLocalApiHandler(d), async (base) => {
      const status = await fetch(`${base}${API_PREFIX}/status`);
      const body = (await status.json()) as { ok: boolean; writeToken?: string; status: unknown };
      expect(body.ok).toBe(true);
      expect(body.writeToken).toBe(clientKey);
      expect(JSON.stringify(body)).not.toContain(SECRET);

      const tested = await fetch(`${base}${API_PREFIX}/test`, {
        method: "POST",
        headers: { [SECRET_HEADER]: clientKey, "content-type": "application/json" },
        body: JSON.stringify({ channel: "openrouter", model: "vendor/model:free" }),
      });
      expect(tested.status).toBe(200);
      expect(d.testModel).toHaveBeenCalledWith("openrouter", "vendor/model:free");
    });
  });

  it("rejects writes without the secret, with a wrong secret, and accepts the header or a bearer token", async () => {
    const d = deps();
    await serve(createLocalApiHandler(d), async (base) => {
      const url = `${base}${API_PREFIX}/refresh`;
      expect((await fetch(url, { method: "POST" })).status).toBe(401);
      expect((await fetch(url, { method: "POST", headers: { [SECRET_HEADER]: "wrong" } })).status).toBe(401);
      // A correctly sized but different secret is still rejected.
      expect((await fetch(url, { method: "POST", headers: { [SECRET_HEADER]: "x".repeat(SECRET.length) } })).status).toBe(401);
      expect(d.refresh).not.toHaveBeenCalled();

      const ok = await fetch(url, { method: "POST", headers: { [SECRET_HEADER]: SECRET } });
      expect(ok.status).toBe(200);
      expect(d.refresh).toHaveBeenCalledTimes(1);
      await expect(ok.json()).resolves.toEqual({ ok: true, status: { plugin: "dsh-freemodel", channels: [] } });

      const bearer = await fetch(url, { method: "POST", headers: { authorization: `Bearer ${SECRET}` } });
      expect(bearer.status).toBe(200);
      expect(d.refresh).toHaveBeenCalledTimes(2);
    });
  });

  it("tests exactly one channel/model named in the JSON body", async () => {
    const d = deps();
    await serve(createLocalApiHandler(d), async (base) => {
      const response = await fetch(`${base}${API_PREFIX}/test`, {
        method: "POST",
        headers: { [SECRET_HEADER]: SECRET, "content-type": "application/json" },
        body: JSON.stringify({ channel: "openrouter", model: "vendor/model:free" }),
      });
      expect(response.status).toBe(200);
      expect(d.testModel).toHaveBeenCalledWith("openrouter", "vendor/model:free");
      await expect(response.json()).resolves.toEqual({
        ok: true,
        channel: "openrouter",
        model: "vendor/model:free",
        result: { ok: true, ttftMs: 120, error: null },
      });
    });
  });

  it("rejects invalid bodies, channels, methods and unknown routes", async () => {
    const d = deps();
    await serve(createLocalApiHandler(d), async (base) => {
      const post = (body: string): Promise<Response> =>
        fetch(`${base}${API_PREFIX}/test`, {
          method: "POST",
          headers: { [SECRET_HEADER]: SECRET, "content-type": "application/json" },
          body,
        });
      expect((await post("{not json")).status).toBe(400);
      expect((await post("[]")).status).toBe(400);
      expect((await post(JSON.stringify({ channel: "deepseek", model: "x" }))).status).toBe(400);
      expect((await post(JSON.stringify({ channel: "groq", model: "" }))).status).toBe(400);
      expect(d.testModel).not.toHaveBeenCalled();

      expect((await fetch(`${base}${API_PREFIX}/status`, { method: "POST", headers: { [SECRET_HEADER]: SECRET } })).status).toBe(405);
      expect((await fetch(`${base}${API_PREFIX}/refresh`)).status).toBe(405);
      expect((await fetch(`${base}${API_PREFIX}/nope`)).status).toBe(404);
      expect((await fetch(`${base}/elsewhere`)).status).toBe(404);
    });
  });

  it("maps service refusals to 404/409 instead of a generic 500", async () => {
    const d = deps();
    const testModel = d.testModel as unknown as ReturnType<typeof vi.fn>;
    testModel.mockRejectedValueOnce(Object.assign(new Error("not in catalogue"), { code: "model-not-found" }));
    testModel.mockRejectedValueOnce(Object.assign(new Error("no key"), { code: "no-key" }));
    await serve(createLocalApiHandler(d), async (base) => {
      const call = (): Promise<Response> =>
        fetch(`${base}${API_PREFIX}/test`, {
          method: "POST",
          headers: { [SECRET_HEADER]: SECRET, "content-type": "application/json" },
          body: JSON.stringify({ channel: "openrouter", model: "missing" }),
        });
      const missing = await call();
      expect(missing.status).toBe(404);
      await expect(missing.json()).resolves.toMatchObject({ ok: false, error: { code: "model-not-found" } });
      const keyless = await call();
      expect(keyless.status).toBe(409);
      await expect(keyless.json()).resolves.toMatchObject({ ok: false, error: { code: "no-key" } });
    });
  });

  it("answers 403 when the peer is not loopback, even with the secret", async () => {
    const d = deps({ isLoopback: () => false });
    await serve(createLocalApiHandler(d), async (base) => {
      expect((await fetch(`${base}${API_PREFIX}/status`)).status).toBe(403);
      expect((await fetch(`${base}${API_PREFIX}/refresh`, { method: "POST", headers: { [SECRET_HEADER]: SECRET } })).status).toBe(403);
      expect((await fetch(`${base}${API_PREFIX}/test`, { method: "POST", headers: { [SECRET_HEADER]: SECRET } })).status).toBe(403);
    });
    expect(d.status).not.toHaveBeenCalled();
    expect(d.refresh).not.toHaveBeenCalled();
    expect(d.testModel).not.toHaveBeenCalled();
  });

  it("returns 503 when no write secret is configured", async () => {
    const d = deps({ secret: "" });
    await serve(createLocalApiHandler(d), async (base) => {
      expect((await fetch(`${base}${API_PREFIX}/refresh`, { method: "POST", headers: { [SECRET_HEADER]: SECRET } })).status).toBe(503);
    });
  });
});

describe("secret handling", () => {
  it("recognises loopback literals and their mapped forms", () => {
    for (const address of ["127.0.0.1", "127.8.9.10", "::1", "0:0:0:0:0:0:0:1", "::ffff:127.0.0.1", "::FFFF:127.0.0.1", "::ffff:7f00:1"]) {
      expect(isLoopbackAddress(address), address).toBe(true);
    }
    for (const address of ["8.8.8.8", "192.168.1.1", "::2", "fe80::1", "::ffff:8.8.8.8", "", undefined]) {
      expect(isLoopbackAddress(address), String(address)).toBe(false);
    }
  });

  it("compares in constant time and rejects missing or differently sized values", () => {
    expect(secretMatches(SECRET, SECRET)).toBe(true);
    expect(secretMatches(SECRET, undefined)).toBe(false);
    expect(secretMatches(SECRET, "")).toBe(false);
    expect(secretMatches(SECRET, `${SECRET}x`)).toBe(false);
    expect(secretMatches("", "")).toBe(false);
  });

  it("uses FREEMODEL_API_SECRET when it is long enough and refuses a short one", () => {
    const env = { [SECRET_ENV]: SECRET };
    expect(loadOrCreateSecret("/nonexistent/api-secret", env)).toBe(SECRET);
    expect(() => loadOrCreateSecret("/nonexistent/api-secret", { [SECRET_ENV]: "short" })).toThrow(/at least/);
  });

  it("creates a 0600 secret file once and reuses it", () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-secret-"));
    const path = join(dir, "nested", "api-secret");
    const created = loadOrCreateSecret(path, {});
    expect(created).toHaveLength(64);
    expect(created).toMatch(/^[0-9a-f]+$/);
    if (process.platform !== "win32") expect(statSync(path).mode & 0o777).toBe(0o600);
    expect(readFileSync(path, "utf8").trim()).toBe(created);
    expect(loadOrCreateSecret(path, {})).toBe(created);

    chmodSync(path, 0o644);
    writeFileSync(path, "too-short\n");
    const replaced = loadOrCreateSecret(path, {});
    expect(replaced).not.toBe("too-short");
    expect(replaced).toHaveLength(64);
  });

  it("generates 64 hex characters", () => {
    expect(generateSecret()).toMatch(/^[0-9a-f]{64}$/);
    expect(MIN_SECRET_LENGTH).toBeLessThanOrEqual(64);
  });
});