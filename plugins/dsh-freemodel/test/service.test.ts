import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { channelOfRoute, createAdapter, FREE_BADGE, pickerName, toPiModel } from "../src/adapter.ts";
import { Config } from "../src/config.ts";
import { GroqChannel } from "../src/providers/groq.ts";
import { OpenRouterChannel } from "../src/providers/openrouter.ts";
import type { CatalogModel } from "../src/providers/types.ts";
import { FreemodelService, type KeyAccess } from "../src/service.ts";
import { fakeFetch, GROQ_KEY, json, OR_KEY, type Route, sse, token } from "./helpers/fake-fetch.ts";

const orModel = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  name: `OR ${id}`,
  context_length: 131072,
  pricing: { prompt: "0", completion: "0" },
  architecture: { input_modalities: ["text"], output_modalities: ["text"] },
  supported_parameters: ["tools"],
  top_provider: { max_completion_tokens: 4096 },
  ...extra,
});

/** OpenRouter: three free models; `bad:free` fails its probe with 404. */
const orRoute: Route = (url, init) => {
  if (url.endsWith("/models")) return json({ data: [orModel("good:free"), orModel("bad:free"), orModel("small:free", { context_length: 4096 })] });
  if (url.endsWith("/key")) return json({ data: { free_model_daily_requests: { limit: 1000, used: 0, remaining: 1000 } } });
  const body = JSON.parse(String(init?.body));
  if (body.model === "bad:free") return json({ error: { message: "No endpoints found" } }, 404);
  return sse([token("hi"), "[DONE]"]);
};
const groqRoute: Route = (url) =>
  url.endsWith("/models") ? json({ data: [{ id: "llama-x", context_window: 131072, active: true }] }) : sse([token("ok")]);

function keys(values: Record<string, string>): KeyAccess & { resolve: ReturnType<typeof vi.fn> } {
  return {
    configured: async (ref) => ref in values,
    resolve: vi.fn(async (ref: string) => values[ref]),
  };
}

function setup(configInput: Parameters<typeof Config>[0] = {}, values: Record<string, string> = { OPENROUTER_API_KEY: OR_KEY }) {
  const dir = mkdtempSync(join(tmpdir(), "fm-svc-"));
  const logger = { info: vi.fn(), warn: vi.fn() };
  const orFetch = fakeFetch(orRoute);
  const groqFetch = fakeFetch(groqRoute);
  const onChange = vi.fn();
  const service = new FreemodelService({
    config: Config(configInput),
    statePath: join(dir, "freemodel", "state.json"),
    keys: keys(values),
    logger,
    channels: { openrouter: new OpenRouterChannel(orFetch), groq: new GroqChannel(groqFetch) },
    onChange,
  });
  return { service, logger, orFetch, groqFetch, onChange, statePath: join(dir, "freemodel", "state.json") };
}

describe("active channels", () => {
  it("OpenRouter is active as soon as its key is saved; Groq waits for freePlanConfirmed", async () => {
    const { service } = setup({ providers: { groq: { enabled: true } } }, { OPENROUTER_API_KEY: OR_KEY, GROQ_API_KEY: GROQ_KEY });
    expect(await service.checkActive()).toBe(true);
    expect(service.activeRoutes()).toEqual(["freemodel-openrouter"]);
    expect(service.view("groq").blocked).toMatch(/freePlanConfirmed is off/);
    expect(await service.checkActive()).toBe(false);
  });

  it("a channel without a key says how to fix it", async () => {
    const { service } = setup({}, {});
    await service.checkActive();
    expect(service.activeRoutes()).toEqual([]);
    expect(service.view("openrouter").blocked).toBe("no key: save one for OPENROUTER_API_KEY in the settings page");
    expect(service.view("groq").blocked).toBe("disabled");
  });

  it("a failing key lookup counts as no key", async () => {
    const { service } = setup();
    (service as unknown as { options: { keys: KeyAccess } }).options.keys.configured = async () => {
      throw new Error("locked");
    };
    await service.checkActive();
    expect(service.isActive("openrouter")).toBe(false);
  });
});

describe("refresh", () => {
  it("reads the catalogue, probes, lists only models that passed, and explains the hidden ones", async () => {
    const { service, orFetch, statePath, onChange } = setup();
    await service.refresh();
    expect(onChange).toHaveBeenCalled();
    const view = service.view("openrouter");
    expect(view.listed.map((r) => r.model.id)).toEqual(["good:free"]);
    expect(view.hidden).toEqual([{ id: "bad:free", reason: "failed: No endpoints found" }]);
    expect(view.probesToday).toBe(2);
    expect(view.lastRound?.probes).toBe(2);
    // small:free is under minContext and never probed.
    const probed = orFetch.calls.filter((c) => c.url.endsWith("/chat/completions")).map((c) => JSON.parse(String(c.init?.body)).model);
    expect(probed.sort()).toEqual(["bad:free", "good:free"]);
    const saved = readFileSync(statePath, "utf8");
    expect(saved).not.toContain(OR_KEY);
    expect(JSON.parse(saved).channels.openrouter.catalog.models).toHaveLength(3);
    service.dispose();
  });

  it("does not probe again while results are fresh", async () => {
    const { service, orFetch } = setup();
    await service.refresh();
    const before = orFetch.calls.length;
    await service.refresh();
    expect(orFetch.calls.length).toBe(before);
    service.dispose();
  });

  it("keeps the old catalogue when a re-read fails, and records a key-free error", async () => {
    const { service, orFetch, logger } = setup();
    await service.refresh();
    const failing = new OpenRouterChannel(fakeFetch(() => json({}, 502)));
    (service.channels as Record<string, unknown>).openrouter = failing;
    await service.refresh({ catalog: true });
    const view = service.view("openrouter");
    expect(view.catalogError).toBe("OpenRouter model discovery failed: HTTP 502");
    expect(view.listed.map((r) => r.model.id)).toEqual(["good:free"]);
    expect(logger.warn.mock.calls.flat().join(" ")).not.toContain(OR_KEY);
    expect(orFetch.calls.length).toBeGreaterThan(0);
    service.dispose();
  });

  it("uses dailyProbeLimit instead of the /key quota when set", async () => {
    const { service, orFetch } = setup({ refresh: { dailyProbeLimit: 11, reserveRequests: 10 } });
    await service.refresh();
    expect(orFetch.calls.some((c) => c.url.endsWith("/key"))).toBe(false);
    expect(service.view("openrouter").probesToday).toBe(1);
    service.dispose();
  });

  it("probes Groq only once its free plan is confirmed", async () => {
    const values = { GROQ_API_KEY: GROQ_KEY };
    const off = setup({ providers: { openrouter: { enabled: false }, groq: { enabled: true } } }, values);
    await off.service.refresh();
    expect(off.groqFetch.calls).toHaveLength(0);
    const on = setup({ providers: { openrouter: { enabled: false }, groq: { enabled: true, freePlanConfirmed: true } } }, values);
    await on.service.refresh();
    expect(on.service.listed("groq").map((r) => r.model.id)).toEqual(["llama-x"]);
    expect(new Headers(on.groqFetch.calls[0]?.init?.headers).get("authorization")).toBe(`Bearer ${GROQ_KEY}`);
    off.service.dispose();
    on.service.dispose();
  });

  it("start() lists from the cached state at once, then refreshes in the background", async () => {
    const first = setup();
    await first.service.refresh();
    first.service.dispose();
    const second = new FreemodelService({
      config: Config({ refresh: { onStartup: false } }),
      statePath: first.statePath,
      keys: keys({ OPENROUTER_API_KEY: OR_KEY }),
      logger: { info: vi.fn(), warn: vi.fn() },
      channels: { openrouter: new OpenRouterChannel(fakeFetch(orRoute)) },
    });
    await second.start();
    expect(second.listed("openrouter").map((r) => r.model.id)).toEqual(["good:free"]);
    second.dispose();
  });

  it("schedules the next refresh no sooner than the shortest due time", async () => {
    const { service } = setup();
    await service.refresh();
    const ms = service.nextDueMs() as number;
    expect(ms).toBeGreaterThan(5 * 3600 * 1000);
    expect(ms).toBeLessThanOrEqual(6 * 3600 * 1000);
    service.dispose();
  });
});

describe("discovery for the settings page", () => {
  it("serves the cached catalogue, else asks the channel; Groq only when confirmed", async () => {
    const { service, orFetch } = setup();
    expect((await service.discoverFor("openrouter", undefined)).map((m) => m.id)).toEqual(["good:free", "bad:free"]);
    expect(orFetch.calls).toHaveLength(1);
    expect(await service.discoverFor("groq", GROQ_KEY)).toEqual([]);
  });
});

describe("adapter", () => {
  const listedModel: CatalogModel = {
    provider: "groq",
    id: "llama-x",
    name: "llama-x",
    contextLength: 131072,
    tools: null,
    input: ["text"],
    maxTokens: null,
    expirationDate: null,
  };

  it("labels models with the free badge instead of their own (free) suffix", () => {
    expect(pickerName("NVIDIA: Nemotron 3.5 Lightning (free)")).toBe(`NVIDIA: Nemotron 3.5 Lightning · ${FREE_BADGE}`);
    expect(pickerName("llama-x")).toBe(`llama-x · ${FREE_BADGE}`);
  });

  it("maps routes to channels", () => {
    expect(channelOfRoute("freemodel-openrouter")).toBe("openrouter");
    expect(channelOfRoute("freemodel-groq")).toBe("groq");
    expect(channelOfRoute("deepseek")).toBeUndefined();
  });

  it("builds text-only pi-ai models with the right max-tokens field and a free badge", () => {
    const groq = toPiModel("groq", { model: listedModel, score: 1, test: null, reasons: [] });
    expect(groq).toMatchObject({
      id: "llama-x",
      name: `llama-x · ${FREE_BADGE}`,
      provider: "freemodel-groq",
      baseUrl: "https://api.groq.com/openai/v1",
      input: ["text"],
      contextWindow: 131072,
      maxTokens: 8192,
      compat: { maxTokensField: "max_completion_tokens" },
    });
    const or = toPiModel("openrouter", { model: { ...listedModel, provider: "openrouter", maxTokens: 4096 }, score: 1, test: null, reasons: [] });
    expect(or).toMatchObject({ maxTokens: 4096, compat: { maxTokensField: "max_tokens" }, headers: { "X-Title": "dsh-freemodel" } });
  });

  it("lists exactly the passing models per route, and follows invalidation", async () => {
    const { service } = setup();
    await service.checkActive();
    const { adapter, invalidate } = createAdapter(service);
    expect(await adapter.listModels("freemodel-openrouter")).toEqual([]);
    await service.refresh();
    invalidate();
    const models = await adapter.listModels("freemodel-openrouter");
    expect(models.map((m) => [m.id, m.name])).toEqual([["good:free", `OR good:free · ${FREE_BADGE}`]]);
    expect(models[0]?.description).toMatch(/^OpenRouter free · TTFT \d+ ms · tools$/);
    const resolved = await adapter.resolveModel("freemodel-openrouter", "good:free");
    expect(resolved).toMatchObject({ provider: "freemodel-openrouter", id: "good:free" });
    service.dispose();
  });
});
