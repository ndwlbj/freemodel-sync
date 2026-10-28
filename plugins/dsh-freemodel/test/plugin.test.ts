import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as plugin from "../src/index.ts";
import { API_PREFIX } from "../src/local-api.ts";
import { OR_KEY } from "./helpers/fake-fetch.ts";

function fakeLlm() {
  const adapterHandle = Object.assign(vi.fn(), { replace: vi.fn() });
  const directoryHandle = Object.assign(vi.fn(), { replace: vi.fn() });
  const releaseDiscovery = vi.fn();
  const llm = {
    registerAdapter: vi.fn((_routes: string[], _adapter: unknown) => adapterHandle),
    registerConfigurableProviders: vi.fn((_entries: unknown[]) => directoryHandle),
    registerModelDiscovery: vi.fn((_ns: string, _fn: unknown) => releaseDiscovery),
  };
  return { llm, adapterHandle, directoryHandle, releaseDiscovery };
}

function fakeCtx(credentials?: unknown, optional: { commands?: unknown; webServer?: unknown } = {}) {
  const info = vi.fn();
  const warn = vi.fn();
  const disposers: Array<() => void> = [];
  const fake = fakeLlm();
  const scoped = (services: Record<string, unknown>) => ({
    ...services,
    effect: (fn: () => () => void) => disposers.unshift(fn()),
  });
  const ctx = {
    get: vi.fn(() => undefined),
    logger: { info, warn },
    llm: fake.llm,
    emit: vi.fn(),
    effect: vi.fn((fn: () => () => void) => disposers.push(fn())),
    // Cordis runs each callback once its optional service exists.
    inject: vi.fn((deps: string[], fn: (inner: unknown) => void) => {
      if (deps.length === 1 && deps[0] === "credentials" && credentials !== undefined) {
        fn(scoped({ credentials }));
        return;
      }
      if (deps.length === 1 && deps[0] === "commands" && optional.commands !== undefined) {
        fn(scoped({ commands: optional.commands }));
        return;
      }
      if (deps.length === 1 && deps[0] === "webServer" && optional.webServer !== undefined) {
        fn(scoped({ webServer: optional.webServer }));
      }
    }),
  };
  return {
    ctx: ctx as unknown as Parameters<typeof plugin.apply>[0],
    raw: ctx,
    info,
    warn,
    dispose: () => disposers.forEach((d) => d()),
    ...fake,
  };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 10));
const credentialsWith = (values: Record<string, string>) => ({
  describe: vi.fn(async (ref: string) => (ref in values ? { configured: true, source: "file", writable: true } : { configured: false, writable: true })),
  resolve: vi.fn(async (ref: string) => (ref in values ? { value: values[ref], source: "file" } : undefined)),
});

describe("plugin entry", () => {
  let home: string;
  const fetchMock = vi.fn(async () => {
    throw new Error("no network in unit tests");
  });
  beforeEach(() => {
    home = mkdtempSync(join(tmpdir(), "fm-plugin-"));
    vi.stubEnv("DSH_HOME", home);
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("exports what the Cordis loader needs", () => {
    expect(plugin.name).toBe("dsh-freemodel");
    expect(plugin.inject).toEqual(["llm"]);
    expect(typeof plugin.apply).toBe("function");
    expect(typeof plugin.Config).toBe("function");
  });

  it("lists both channels in the settings directory and offers discovery under its namespace", () => {
    const { ctx, llm } = fakeCtx(undefined);
    plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
    const entries = llm.registerConfigurableProviders.mock.calls[0]?.[0] as Array<Record<string, unknown>>;
    expect(entries.map((e) => [e.provider, e.settingsNs, e.settingsPath])).toEqual([
      ["freemodel-openrouter", "dsh-freemodel", ["providers", "openrouter"]],
      ["freemodel-groq", "dsh-freemodel", ["providers", "groq"]],
    ]);
    expect(llm.registerModelDiscovery.mock.calls[0]?.[0]).toBe("dsh-freemodel");
  });

  it("registers the OpenRouter route once its key is saved, and resolves the key only to use it", async () => {
    const credentials = credentialsWith({ OPENROUTER_API_KEY: OR_KEY });
    const { ctx, raw, llm, info, warn, dispose, adapterHandle, directoryHandle, releaseDiscovery } = fakeCtx(credentials);
    plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
    await settle();
    expect(llm.registerAdapter).toHaveBeenCalledTimes(1);
    expect(llm.registerAdapter.mock.calls[0]?.[0]).toEqual(["freemodel-openrouter"]);
    expect(credentials.resolve).not.toHaveBeenCalled();
    expect(raw.emit).toHaveBeenCalledWith("llm/adapters-updated");
    expect(warn).not.toHaveBeenCalled();
    expect(info.mock.calls.map((c) => c[0]).join("\n")).toContain("openrouter: 0 listed, 0 hidden; groq: off (disabled)");
    expect(JSON.stringify([info.mock.calls, warn.mock.calls])).not.toContain(OR_KEY);
    dispose();
    expect(adapterHandle).toHaveBeenCalled();
    expect(directoryHandle).toHaveBeenCalled();
    expect(releaseDiscovery).toHaveBeenCalled();
  });

  it("shows why an enabled channel is off in the settings directory", async () => {
    const credentials = credentialsWith({ GROQ_API_KEY: "gsk_test" });
    const { ctx, llm, directoryHandle } = fakeCtx(credentials);
    plugin.apply(ctx, plugin.Config({ providers: { groq: { enabled: true } }, refresh: { onStartup: false } }));
    await settle();
    expect(llm.registerAdapter).not.toHaveBeenCalled();
    const entries = directoryHandle.replace.mock.calls.at(-1)?.[0] as Array<Record<string, unknown>>;
    expect(entries[0]?.error).toBe("no key: save one for OPENROUTER_API_KEY in the settings page");
    expect(entries[1]?.error).toMatch(/freePlanConfirmed is off/);
  });

  it("works without a credential service", async () => {
    const { ctx, llm, warn } = fakeCtx(undefined);
    plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
    await settle();
    expect(llm.registerAdapter).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
  });

  it("refuses discovery for routes it does not own", async () => {
    const { ctx, llm } = fakeCtx(undefined);
    plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
    const discover = llm.registerModelDiscovery.mock.calls[0]?.[1] as (r: { provider?: string }) => Promise<unknown>;
    await expect(discover({ provider: "deepseek" })).rejects.toThrow(/freemodel-\*/);
  });

  it("registers /freemodel and the loopback-only local API when those services exist", async () => {
    const commandDispose = vi.fn();
    const routeDispose = vi.fn();
    const commands = { register: vi.fn((_definition: unknown) => commandDispose) };
    const webServer = { register: vi.fn((_route: unknown) => routeDispose) };
    const { ctx, dispose } = fakeCtx(undefined, { commands, webServer });
    plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
    await settle();

    expect(commands.register).toHaveBeenCalledTimes(1);
    const definition = commands.register.mock.calls[0]?.[0] as { name: string; handler: unknown };
    expect(definition.name).toBe("freemodel");
    expect(typeof definition.handler).toBe("function");

    expect(webServer.register).toHaveBeenCalledTimes(1);
    const route = webServer.register.mock.calls[0]?.[0] as { kind: string; path: string; handler: unknown };
    expect(route.kind).toBe("prefix");
    expect(route.path).toBe(API_PREFIX);
    expect(typeof route.handler).toBe("function");

    dispose();
    expect(commandDispose).toHaveBeenCalled();
    expect(routeDispose).toHaveBeenCalled();
  });
});
