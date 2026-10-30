import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { defaultProviders, defaultRanking, defaultRefresh, type FreemodelConfig, type ManualEntryConfig, manualProbeOf } from "../src/channels.ts";
import { Config } from "../src/config.ts";
import {
  entryExpired,
  type LlmStreamChunkLike,
  manualEntriesOf,
  manualKey,
  type ManualLlm,
  manualProbeDecision,
  manualReport,
  probeManualEntry,
  validateManualEntry,
} from "../src/manual.ts";
import { FreemodelService } from "../src/service.ts";
import { loadState } from "../src/state.ts";

const NOW = new Date("2026-11-02T10:00:00Z");
const FAKE_KEY = ["sk", "notarealkey", "x".repeat(16)].join("-");

function entry(overrides: Partial<ManualEntryConfig> = {}): ManualEntryConfig {
  return {
    dshProvider: "dsh-zcode",
    model: "glm-5.3",
    label: "",
    quotaNote: "",
    expiresAt: "",
    probe: true,
    ...overrides,
  };
}

function llmOf(chunks: LlmStreamChunkLike[] | (() => AsyncIterable<LlmStreamChunkLike>)): ManualLlm & { calls: unknown[] } {
  const calls: unknown[] = [];
  return {
    calls,
    stream(options) {
      calls.push(options);
      if (typeof chunks === "function") return chunks();
      return (async function* () {
        for (const chunk of chunks) yield chunk;
      })();
    },
  };
}

describe("manual config", () => {
  it("defaults to no entries and no probing", () => {
    const config = Config({});
    expect(config.manual).toEqual([]);
    expect(manualProbeOf(config)).toEqual({ enabled: false });
    expect(manualEntriesOf(config)).toEqual([]);
  });

  it("normalizes an entry and defaults probe to false", () => {
    const config = Config({ manual: [{ dshProvider: "qoder-global", model: "qfmodel" }] });
    expect(config.manual).toEqual([
      { dshProvider: "qoder-global", model: "qfmodel", label: "", quotaNote: "", expiresAt: "", probe: false },
    ]);
    const enabled = Config({ manualProbe: { enabled: true } });
    expect(manualProbeOf(enabled)).toEqual({ enabled: true });
  });

  it("rejects token/pat/cookie/secret/key fields and key-shaped values", () => {
    for (const field of ["token", "pat", "cookie", "secret", "key", "password", "accessToken"]) {
      expect(() => Config({ manual: [{ dshProvider: "x", model: "m", [field]: "fake" }] })).toThrow(new RegExp(field, "i"));
    }
    expect(() => Config({ manual: [{ dshProvider: "x", model: "m", label: FAKE_KEY }] })).toThrow(/looks like an API key/);
    expect(() => validateManualEntry({ dshProvider: "x", model: "m", quotaNote: FAKE_KEY })).toThrow(/looks like an API key/);
  });

  it("rejects unknown fields rather than silently keeping them", () => {
    expect(() => Config({ manual: [{ dshProvider: "x", model: "m", account: "me" }] } as never)).toThrow(/unknown field/);
    expect(() => Config({ manualProbe: { enabled: true, extra: true } } as never)).toThrow(/unknown field/);
  });

  it("keeps the settings form fields visible", () => {
    const schema = Config as unknown as { dict?: Record<string, unknown> };
    expect(schema.dict?.manual).toBeDefined();
    expect(schema.dict?.manualProbe).toBeDefined();
  });
});

describe("manual probe decision", () => {
  it("requires both switches, a valid date and the daily cap", () => {
    expect(manualProbeDecision(entry(), [], false, NOW)).toEqual({ allowed: false, reason: "disabled" });
    expect(manualProbeDecision(entry({ probe: false }), [], true, NOW)).toEqual({ allowed: false, reason: "probe-off" });
    expect(manualProbeDecision(entry({ expiresAt: "2026-11-01" }), [], true, NOW)).toEqual({ allowed: false, reason: "expired" });
    expect(
      manualProbeDecision(
        entry(),
        [{ provider: "dsh-zcode", model: "glm-5.3", ok: true, failure_kind: null, error_code: null, tested_at: NOW.getTime() / 1000 }],
        true,
        NOW,
      ),
    ).toEqual({ allowed: false, reason: "daily-limit" });
    expect(entryExpired("2026-11-02", "2026-11-02")).toBe(false);
  });

  it("reports detected routes and expired/last-probe state for the card", () => {
    const config = Config({
      manual: [{ dshProvider: "dsh-zcode", model: "glm-5.3", probe: true, expiresAt: "2026-11-01" }],
      manualProbe: { enabled: true },
    });
    const report = manualReport(
      config,
      {
        [manualKey("dsh-zcode", "glm-5.3")]: {
          provider: "dsh-zcode",
          model: "glm-5.3",
          ok: false,
          failure_kind: "account",
          error_code: "11140",
          tested_at: NOW.getTime() / 1000,
        },
      },
      ["dsh-zcode"],
      NOW,
    );
    expect(report.enabled).toBe(true);
    expect(report.entries[0]).toMatchObject({ detected: true, expired: true, lastProbe: { error_code: "11140" } });
    expect(manualReport(config, {}, null, NOW).entries[0]?.detected).toBeNull();
    expect(manualReport(config, {}, [], NOW).entries[0]?.detected).toBe(false);
  });

  it("stops the platform for the day on account, but not on capacity", () => {
    const account = { provider: "workbuddy", model: "a", ok: false, failure_kind: "account" as const, error_code: "11140", tested_at: NOW.getTime() / 1000 };
    expect(manualProbeDecision(entry({ dshProvider: "workbuddy", model: "b" }), [account], true, NOW)).toEqual({
      allowed: false,
      reason: "platform-stopped",
    });
    const capacity = { ...account, model: "a", failure_kind: "capacity" as const, error_code: "model_busy" };
    expect(manualProbeDecision(entry({ dshProvider: "workbuddy", model: "b" }), [capacity], true, NOW)).toEqual({
      allowed: true,
      reason: null,
    });
  });
});

describe("probeManualEntry", () => {
  it("sends one minimal request through ctx.llm and stores exactly six fields", async () => {
    const llm = llmOf([{ type: "text-delta", text: "p" }, { type: "finish", reason: { kind: "stop" } }]);
    const record = await probeManualEntry(llm, entry(), NOW);
    expect(record).toEqual({
      provider: "dsh-zcode",
      model: "glm-5.3",
      ok: true,
      failure_kind: null,
      error_code: null,
      tested_at: NOW.getTime() / 1000,
    });
    expect(Object.keys(record!).sort()).toEqual(["error_code", "failure_kind", "model", "ok", "provider", "tested_at"]);
    expect(llm.calls).toHaveLength(1);
    expect(llm.calls[0]).toMatchObject({
      provider: "dsh-zcode",
      model: "glm-5.3",
      maxTokens: 1,
      messages: [{ role: "user", content: [{ type: "text", text: "ping" }] }],
    });
  });

  it("maps WorkBuddy 11140 to account and never stores the error text", async () => {
    const llm = llmOf([
      {
        type: "finish",
        reason: { kind: "error", failure: { code: "11140", status: 403, message: `account restricted for ${FAKE_KEY}` } },
      },
    ]);
    const record = await probeManualEntry(llm, entry({ dshProvider: "workbuddy", model: "hy3" }), NOW);
    expect(record?.failure_kind).toBe("account");
    expect(record?.error_code).toBe("11140");
    expect(JSON.stringify(record)).not.toContain("restricted");
    expect(JSON.stringify(record)).not.toContain("sk-");
  });

  it("maps queue/busy to capacity and a thrown transport error to a code-only failure", async () => {
    const capacity = await probeManualEntry(
      llmOf([{ type: "finish", reason: { kind: "error", failure: { code: "ModelBusy", status: 429, message: "queued" } } }]),
      entry({ dshProvider: "qoder-global", model: "dfmodel" }),
      NOW,
    );
    expect(capacity?.failure_kind).toBe("capacity");
    const thrown = await probeManualEntry(
      llmOf(() =>
        (async function* () {
          throw new Error(`network down for ${FAKE_KEY}`);
        })(),
      ),
      entry(),
      NOW,
    );
    expect(thrown?.ok).toBe(false);
    expect(thrown?.error_code).toBe("Error");
    expect(JSON.stringify(thrown)).not.toContain("network down");
  });

  it("treats NO_ADAPTER in error chunk as not run (returns null)", async () => {
    const chunk = await probeManualEntry(
      llmOf([{ type: "finish", reason: { kind: "error", failure: { code: "NO_ADAPTER", message: "no adapter" } } }]),
      entry(),
      NOW,
    );
    expect(chunk).toBeNull();
  });

  it("treats thrown NO_ADAPTER error as not run (returns null)", async () => {
    const thrown = await probeManualEntry(
      llmOf(() =>
        (async function* () {
          const err = new Error("no adapter registered for provider \"dsh-zcode\"");
          (err as { code?: string }).code = "NO_ADAPTER";
          throw err;
        })(),
      ),
      entry(),
      NOW,
    );
    expect(thrown).toBeNull();
  });
});

describe("FreemodelService manual probing", () => {
  function service(entries: ManualEntryConfig[], llm: ManualLlm, statePath: string, nowMs: number): FreemodelService {
    const config: FreemodelConfig = {
      providers: defaultProviders(),
      ranking: defaultRanking(),
      refresh: defaultRefresh(),
      manual: entries,
      manualProbe: { enabled: true },
    };
    return new FreemodelService({
      config,
      statePath,
      logger: { info: () => undefined, warn: () => undefined },
      keys: { configured: async () => false, resolve: async () => undefined },
      llm,
      now: () => nowMs,
    });
  }

  it("probes at most once per model per day and stores the six-field record", async () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-manual-"));
    const path = join(dir, "state.json");
    const nowMs = NOW.getTime();
    const stream = vi.fn(async function* () {
      yield { type: "finish", reason: { kind: "stop" } } as LlmStreamChunkLike;
    });
    const svc = service([entry()], { stream }, path, nowMs);
    await svc.refresh({ probe: true });
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(1);
    const stored = loadState(path).manual.probes[manualKey("dsh-zcode", "glm-5.3")];
    expect(stored).toEqual({
      provider: "dsh-zcode",
      model: "glm-5.3",
      ok: true,
      failure_kind: null,
      error_code: null,
      tested_at: nowMs / 1000,
    });
    svc.dispose();
  });

  it("an account failure stops the platform for the day; capacity does not", async () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-manual-"));
    const accountPath = join(dir, "account.json");
    const nowMs = NOW.getTime();
    const accountStream = vi.fn(async function* () {
      yield {
        type: "finish",
        reason: { kind: "error", failure: { code: "11140", status: 403, message: "restricted" } },
      } as LlmStreamChunkLike;
    });
    const accountSvc = service(
      [entry({ dshProvider: "workbuddy", model: "a" }), entry({ dshProvider: "workbuddy", model: "b" })],
      { stream: accountStream },
      accountPath,
      nowMs,
    );
    await accountSvc.refresh({ probe: true });
    expect(accountStream).toHaveBeenCalledTimes(1);
    accountSvc.dispose();

    const capacityPath = join(dir, "capacity.json");
    const capacityStream = vi.fn(async function* () {
      yield {
        type: "finish",
        reason: { kind: "error", failure: { code: "ModelBusy", status: 429, message: "queued" } },
      } as LlmStreamChunkLike;
    });
    const capacitySvc = service(
      [entry({ dshProvider: "qoder-global", model: "a" }), entry({ dshProvider: "qoder-global", model: "b" })],
      { stream: capacityStream },
      capacityPath,
      nowMs,
    );
    await capacitySvc.refresh({ probe: true });
    expect(capacityStream).toHaveBeenCalledTimes(2);
    capacitySvc.dispose();
  });

  it("NO_ADAPTER as chunk -> no record, no cap used, a later successful probe still runs once that day and then is capped", async () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-manual-noadapter-chunk-"));
    const path = join(dir, "state.json");
    const nowMs = NOW.getTime();
    let shouldFail = true;
    const stream = vi.fn(async function* () {
      if (shouldFail) {
        yield {
          type: "finish",
          reason: { kind: "error", failure: { code: "NO_ADAPTER", message: "no adapter" } },
        } as LlmStreamChunkLike;
      } else {
        yield { type: "finish", reason: { kind: "stop" } } as LlmStreamChunkLike;
      }
    });
    const svc = service([entry()], { stream }, path, nowMs);
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(1);
    expect(loadState(path).manual.probes[manualKey("dsh-zcode", "glm-5.3")]).toBeUndefined();

    // Later successful probe still runs once that day
    shouldFail = false;
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(2);
    expect(loadState(path).manual.probes[manualKey("dsh-zcode", "glm-5.3")]?.ok).toBe(true);

    // And then is capped for the rest of the day
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(2);
    svc.dispose();
  });

  it("NO_ADAPTER thrown -> same: no record, no cap used, later probe succeeds and is capped", async () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-manual-noadapter-thrown-"));
    const path = join(dir, "state.json");
    const nowMs = NOW.getTime();
    let shouldFail = true;
    const stream = vi.fn(async function* () {
      if (shouldFail) {
        const err = new Error("no adapter registered for provider \"dsh-zcode\"");
        (err as { code?: string }).code = "NO_ADAPTER";
        throw err;
      } else {
        yield { type: "finish", reason: { kind: "stop" } } as LlmStreamChunkLike;
      }
    });
    const svc = service([entry()], { stream }, path, nowMs);
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(1);
    expect(loadState(path).manual.probes[manualKey("dsh-zcode", "glm-5.3")]).toBeUndefined();

    // Later successful probe runs
    shouldFail = false;
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(2);
    expect(loadState(path).manual.probes[manualKey("dsh-zcode", "glm-5.3")]?.ok).toBe(true);

    // And is capped
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(2);
    svc.dispose();
  });

  it("a normal model failure is still recorded and counts toward the daily cap", async () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-manual-model-fail-"));
    const path = join(dir, "state.json");
    const nowMs = NOW.getTime();
    const stream = vi.fn(async function* () {
      yield {
        type: "finish",
        reason: { kind: "error", failure: { code: "invalid_model_id", status: 404, message: "model not found" } },
      } as LlmStreamChunkLike;
    });
    const svc = service([entry()], { stream }, path, nowMs);
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(1);
    const stored = loadState(path).manual.probes[manualKey("dsh-zcode", "glm-5.3")];
    expect(stored).toBeDefined();
    expect(stored?.ok).toBe(false);
    expect(stored?.failure_kind).toBe("model");
    expect(stored?.error_code).toBe("invalid_model_id");

    // Daily limit consumed: subsequent refresh does not probe again today
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(1);
    svc.dispose();
  });

  it("avoids hammering when not-run: unforced refresh within probeHours skips the entry", async () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-manual-no-hammer-"));
    const path = join(dir, "state.json");
    let currentMs = NOW.getTime();
    const stream = vi.fn(async function* () {
      yield {
        type: "finish",
        reason: { kind: "error", failure: { code: "NO_ADAPTER", message: "no adapter" } },
      } as LlmStreamChunkLike;
    });
    const svc = new FreemodelService({
      config: {
        providers: defaultProviders(),
        ranking: defaultRanking(),
        refresh: defaultRefresh(),
        manual: [entry()],
        manualProbe: { enabled: true },
      },
      statePath: path,
      logger: { info: () => undefined, warn: () => undefined },
      keys: { configured: async () => false, resolve: async () => undefined },
      llm: { stream },
      now: () => currentMs,
    });
    // Initial run encounters NO_ADAPTER
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(1);

    // Unforced refresh within probeHours (e.g. 5 minutes later) does NOT probe
    currentMs += 300 * 1000;
    await svc.refresh();
    expect(stream).toHaveBeenCalledTimes(1);

    // After probeHours (default 12 hours, e.g. 13 hours later), unforced refresh retries
    currentMs += 13 * 3600 * 1000;
    await svc.refresh();
    expect(stream).toHaveBeenCalledTimes(2);
    svc.dispose();
  });

  it("recheckManualRoutes clears attempt and triggers refresh when route is newly registered", async () => {
    const dir = mkdtempSync(join(tmpdir(), "fm-manual-recheck-"));
    const path = join(dir, "state.json");
    const nowMs = NOW.getTime();
    let shouldFail = true;
    const stream = vi.fn(async function* () {
      if (shouldFail) {
        yield {
          type: "finish",
          reason: { kind: "error", failure: { code: "NO_ADAPTER" } },
        } as LlmStreamChunkLike;
      } else {
        yield { type: "finish", reason: { kind: "stop" } } as LlmStreamChunkLike;
      }
    });
    const svc = service([entry({ dshProvider: "workbuddy", model: "hy3" })], { stream }, path, nowMs);
    await svc.refresh({ probe: true });
    expect(stream).toHaveBeenCalledTimes(1);

    // Recheck with an unrelated route: does not probe
    svc.recheckManualRoutes(["other-route"]);
    expect(stream).toHaveBeenCalledTimes(1);

    // Route is now registered: recheck triggers refresh
    shouldFail = false;
    svc.recheckManualRoutes(["workbuddy"]);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(stream).toHaveBeenCalledTimes(2);
    expect(loadState(path).manual.probes[manualKey("workbuddy", "hy3")]?.ok).toBe(true);
    svc.dispose();
  });
});