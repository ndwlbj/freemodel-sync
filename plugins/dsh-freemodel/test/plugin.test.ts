import { existsSync, mkdtempSync, readFileSync } from "node:fs";
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
    get: vi.fn((_key: string) => undefined as unknown),
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
  const originalEnv = { ...process.env };
  const fetchMock = vi.fn(async () => {
    throw new Error("no network in unit tests");
  });
  beforeEach(() => {
    home = mkdtempSync(join(tmpdir(), "fm-plugin-"));
    vi.stubEnv("DSH_HOME", home);
    vi.stubGlobal("fetch", fetchMock);
    delete process.env.OPENROUTER_API_KEY;
    delete process.env.GROQ_API_KEY;
    delete process.env.SENSENOVA_API_KEY;
    delete process.env.DASHSCOPE_API_KEY;
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    for (const key of ["OPENROUTER_API_KEY", "GROQ_API_KEY", "SENSENOVA_API_KEY", "DASHSCOPE_API_KEY"]) {
      if (originalEnv[key] !== undefined) {
        process.env[key] = originalEnv[key];
      } else {
        delete process.env[key];
      }
    }
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
      ["freemodel-sensenova", "dsh-freemodel", ["providers", "sensenova"]],
      ["freemodel-bailian", "dsh-freemodel", ["providers", "bailian"]],
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
    expect(info.mock.calls.map((c) => c[0]).join("\n")).toContain(
      "openrouter: 0 listed, 0 hidden; groq: off (disabled); sensenova: off (disabled); bailian: off (disabled)",
    );
    expect(JSON.stringify([info.mock.calls, warn.mock.calls])).not.toContain(OR_KEY);
    dispose();
    expect(adapterHandle).toHaveBeenCalled();
    expect(directoryHandle).toHaveBeenCalled();
    expect(releaseDiscovery).toHaveBeenCalled();
  });

  it("shows why an enabled channel is off in the settings directory", async () => {
    const credentials = credentialsWith({ GROQ_API_KEY: "gsk_test" });
    const { ctx, llm, directoryHandle } = fakeCtx(credentials);
    plugin.apply(
      ctx,
      plugin.Config({
        providers: { groq: { enabled: true }, sensenova: { enabled: true }, bailian: { enabled: true } },
        refresh: { onStartup: false },
      }),
    );
    await settle();
    expect(llm.registerAdapter).not.toHaveBeenCalled();
    const entries = directoryHandle.replace.mock.calls.at(-1)?.[0] as Array<Record<string, unknown>>;
    expect(entries[0]?.error).toBe("no key: save one for OPENROUTER_API_KEY in the settings page");
    expect(entries[1]?.error).toMatch(/freePlanConfirmed is off/);
    expect(entries[2]?.error).toMatch(/tokenPlanConfirmed is off/);
    expect(entries[3]?.error).toMatch(/freeQuotaGuardConfirmed is off/);
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

  it("registers freemodel-auto adapter and directory entry when autoRoute is enabled", async () => {
    const credentials = credentialsWith({ OPENROUTER_API_KEY: OR_KEY });
    const { ctx, llm, directoryHandle, dispose } = fakeCtx(credentials);
    plugin.apply(
      ctx,
      plugin.Config({
        autoRoute: { enabled: true },
        refresh: { onStartup: false },
      }),
    );
    await settle();

    // Check directory includes freemodel-auto
    const entries = directoryHandle.replace.mock.calls.at(-1)?.[0] as Array<Record<string, unknown>>;
    const autoEntry = entries.find((e) => e.provider === "freemodel-auto");
    expect(autoEntry).toMatchObject({
      provider: "freemodel-auto",
      displayName: "FreeModel Auto (best)",
      settingsNs: "dsh-freemodel",
      settingsPath: ["autoRoute"],
      declared: false,
    });

    // registerAdapter called for freemodel-openrouter and freemodel-auto
    const registeredRoutes = llm.registerAdapter.mock.calls.map((call) => call[0]);
    expect(registeredRoutes).toContainEqual(["freemodel-openrouter"]);
    expect(registeredRoutes).toContainEqual(["freemodel-auto"]);

    // discovery handles freemodel-auto
    const discover = llm.registerModelDiscovery.mock.calls[0]?.[1] as (r: { provider?: string }) => Promise<unknown[]>;
    const models = await discover({ provider: "freemodel-auto" });
    expect(models).toEqual([{ id: "best", name: "Auto · 免费" }]);

    dispose();
  });

  describe("autoDefaultModel profile resolution and deduplication (Findings 1 & 5)", () => {
    it("handles mocked ctx.get('profileContext') with would-write (env unset) and no file written", async () => {
      const profileDir = join(home, "profiles", "fmtest");
      const { ctx, raw, info, dispose } = fakeCtx(undefined);
      raw.get.mockImplementation((k: string) => (k === "profileContext" ? { name: "fmtest", dir: profileDir } : undefined));

      plugin.apply(
        ctx,
        plugin.Config({
          autoDefaultModel: true,
          autoRoute: { enabled: true },
          refresh: { onStartup: false },
        }),
      );
      await settle();

      expect(existsSync(join(profileDir, "cordis.patch.yml"))).toBe(false);
      const wouldWriteLogs = info.mock.calls
        .map((c) => String(c[0]))
        .filter((msg) => msg.includes("autoDefaultModel would write"));
      expect(wouldWriteLogs.length).toBe(1);
      expect(wouldWriteLogs[0]).toContain("provider=freemodel-auto");
      expect(wouldWriteLogs[0]).toContain("model=best");
      expect(wouldWriteLogs[0]).toContain(profileDir);

      dispose();
    });

    it("applies patch when ctx.get('profileContext') is present and DSH_FREEMODEL_APPLY_DEFAULT=1", async () => {
      vi.stubEnv("DSH_FREEMODEL_APPLY_DEFAULT", "1");
      const profileDir = join(home, "profiles", "fmtest");
      const patchPath = join(profileDir, "cordis.patch.yml");
      const { ctx, raw, info, dispose } = fakeCtx(undefined);
      raw.get.mockImplementation((k: string) => (k === "profileContext" ? { name: "fmtest", dir: profileDir } : undefined));

      plugin.apply(
        ctx,
        plugin.Config({
          autoDefaultModel: true,
          autoRoute: { enabled: true },
          refresh: { onStartup: false },
        }),
      );
      await settle();

      expect(existsSync(patchPath)).toBe(true);
      const content = readFileSync(patchPath, "utf-8");
      expect(content).toContain("- id: agent-default-model");
      expect(content).toContain("config: {provider: freemodel-auto, model: 'best'}");

      const appliedLogs = info.mock.calls
        .map((c) => String(c[0]))
        .filter((msg) => msg.includes("updated agent-default-model"));
      expect(appliedLogs.length).toBe(1);

      dispose();
    });

    it("falls back to DSH_PROFILE when profileContext is absent", async () => {
      vi.stubEnv("DSH_PROFILE", "env-profile");
      vi.stubEnv("DSH_FREEMODEL_APPLY_DEFAULT", "1");
      const expectedPatch = join(home, "profiles", "env-profile", "cordis.patch.yml");
      const { ctx, raw, info, dispose } = fakeCtx(undefined);
      raw.get.mockReturnValue(undefined);

      plugin.apply(
        ctx,
        plugin.Config({
          autoDefaultModel: true,
          autoRoute: { enabled: true },
          refresh: { onStartup: false },
        }),
      );
      await settle();

      expect(existsSync(expectedPatch)).toBe(true);
      const content = readFileSync(expectedPatch, "utf-8");
      expect(content).toContain("provider: freemodel-auto");

      dispose();
    });

    it("warns exactly once when neither profileContext nor DSH_PROFILE provides a name", async () => {
      const credentials = credentialsWith({ OPENROUTER_API_KEY: OR_KEY });
      const { ctx, raw, warn, dispose } = fakeCtx(credentials);
      raw.get.mockReturnValue(undefined);

      plugin.apply(
        ctx,
        plugin.Config({
          autoDefaultModel: true,
          autoRoute: { enabled: true },
          refresh: { onStartup: false },
        }),
      );
      await settle();

      const expectedWarning =
        "dsh-freemodel: autoDefaultModel is on but the current profile cannot be determined (no profileContext, no DSH_PROFILE); skipping";
      const matchingWarns = warn.mock.calls.map((c) => String(c[0])).filter((msg) => msg === expectedWarning);
      expect(matchingWarns.length).toBe(1);

      dispose();
    });

    it("does not warn about missing profile when autoDefaultModel is off", async () => {
      const { ctx, raw, warn, dispose } = fakeCtx(undefined);
      raw.get.mockReturnValue(undefined);

      plugin.apply(
        ctx,
        plugin.Config({
          autoDefaultModel: false,
          refresh: { onStartup: false },
        }),
      );
      await settle();

      const warnMsgs = warn.mock.calls.map((c) => String(c[0]));
      expect(warnMsgs.some((m) => m.includes("cannot be determined"))).toBe(false);

      dispose();
    });

    it("skips and refuses QQ/bot profile names from profileContext", async () => {
      vi.stubEnv("DSH_FREEMODEL_APPLY_DEFAULT", "1");
      const profileDir = join(home, "profiles", "my-qqbot");
      const patchPath = join(profileDir, "cordis.patch.yml");
      const { ctx, raw, dispose } = fakeCtx(undefined);
      raw.get.mockImplementation((k: string) => (k === "profileContext" ? { name: "my-qqbot", dir: profileDir } : undefined));

      plugin.apply(
        ctx,
        plugin.Config({
          autoDefaultModel: true,
          autoRoute: { enabled: true },
          refresh: { onStartup: false },
        }),
      );
      await settle();

      expect(existsSync(patchPath)).toBe(false);

      dispose();
    });

    it("refuses writing when dir equals the home layer", async () => {
      vi.stubEnv("DSH_FREEMODEL_APPLY_DEFAULT", "1");
      const { ctx, raw, warn, dispose } = fakeCtx(undefined);
      // profileContext pointing to the root home directory
      raw.get.mockImplementation((k: string) => (k === "profileContext" ? { name: "fmtest", dir: home } : undefined));

      plugin.apply(
        ctx,
        plugin.Config({
          autoDefaultModel: true,
          autoRoute: { enabled: true },
          refresh: { onStartup: false },
        }),
      );
      await settle();

      // Home layer patch should NOT be created or written
      expect(existsSync(join(home, "cordis.patch.yml"))).toBe(false);

      // Warning logged regarding refusal
      const warnCalls = warn.mock.calls.map((c) => String(c[0]));
      expect(warnCalls.some((msg) => msg.includes("failed to apply default model switch"))).toBe(true);

      dispose();
    });

    it("deduplicates identical consecutive log lines across multiple sync runs in one plugin instance", async () => {
      const credentials = credentialsWith({ OPENROUTER_API_KEY: OR_KEY });
      const profileDir = join(home, "profiles", "fmtest");
      const { ctx, raw, info, dispose } = fakeCtx(credentials);
      raw.get.mockImplementation((k: string) => (k === "profileContext" ? { name: "fmtest", dir: profileDir } : undefined));

      plugin.apply(
        ctx,
        plugin.Config({
          autoDefaultModel: true,
          autoRoute: { enabled: true },
          refresh: { onStartup: false },
        }),
      );
      await settle();

      // Multiple sync() runs happen during startup and credentials resolution
      const wouldWriteLogs = info.mock.calls
        .map((c) => String(c[0]))
        .filter((msg) => msg.includes("autoDefaultModel would write"));

      // Exactly one would-write log line despite multiple sync passes
      expect(wouldWriteLogs.length).toBe(1);

      dispose();
    });
  });

  describe("environment key fallback (Finding 2)", () => {
    it("no credentials service + env var set -> channel active and resolveKey returns the value", async () => {
      const fakeKey = ["sk", "notarealkey", "x".repeat(16)].join("-");
      vi.stubEnv("OPENROUTER_API_KEY", fakeKey);
      const { ctx, llm, dispose } = fakeCtx(undefined);
      plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
      await settle();

      expect(llm.registerAdapter).toHaveBeenCalledWith(["freemodel-openrouter"], expect.anything());
      const adapter = llm.registerAdapter.mock.calls[0]?.[1] as unknown as { service: { resolveKey(id: string): Promise<string | undefined> } };
      expect(await adapter.service.resolveKey("openrouter")).toBe(fakeKey);
      dispose();
    });

    it("credentials returns nothing + env set -> falls back", async () => {
      const fakeKey = ["sk", "notarealkey", "x".repeat(16)].join("-");
      vi.stubEnv("OPENROUTER_API_KEY", fakeKey);
      const credentials = credentialsWith({});
      const { ctx, llm, dispose } = fakeCtx(credentials);
      plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
      await settle();

      expect(llm.registerAdapter).toHaveBeenCalledWith(["freemodel-openrouter"], expect.anything());
      const adapter = llm.registerAdapter.mock.calls[0]?.[1] as unknown as { service: { resolveKey(id: string): Promise<string | undefined> } };
      expect(await adapter.service.resolveKey("openrouter")).toBe(fakeKey);
      dispose();
    });

    it("credentials has a value and env differs -> credentials wins", async () => {
      const credKey = ["sk", "credkey", "c".repeat(16)].join("-");
      const envKey = ["sk", "envkey", "e".repeat(16)].join("-");
      vi.stubEnv("OPENROUTER_API_KEY", envKey);
      const credentials = credentialsWith({ OPENROUTER_API_KEY: credKey });
      const { ctx, llm, dispose } = fakeCtx(credentials);
      plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
      await settle();

      expect(llm.registerAdapter).toHaveBeenCalledWith(["freemodel-openrouter"], expect.anything());
      const adapter = llm.registerAdapter.mock.calls[0]?.[1] as unknown as { service: { resolveKey(id: string): Promise<string | undefined> } };
      expect(await adapter.service.resolveKey("openrouter")).toBe(credKey);
      dispose();
    });

    it("neither -> inactive with the existing 'no key' reason", async () => {
      const { ctx, llm, directoryHandle, dispose } = fakeCtx(undefined);
      plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
      await settle();

      expect(llm.registerAdapter).not.toHaveBeenCalled();
      const entries = directoryHandle.replace.mock.calls.at(-1)?.[0] as Array<Record<string, unknown>>;
      expect(entries[0]?.error).toBe("no key: save one for OPENROUTER_API_KEY in the settings page");
      dispose();
    });

    it("logs/status JSON never contain the value", async () => {
      const fakeKey = ["sk", "notarealkey", "x".repeat(16)].join("-");
      vi.stubEnv("OPENROUTER_API_KEY", fakeKey);
      const { ctx, info, warn, dispose } = fakeCtx(undefined);
      plugin.apply(ctx, plugin.Config({ refresh: { onStartup: false } }));
      await settle();

      const status = await plugin.buildStatus(plugin.Config(), undefined, process.env);
      expect(status.channels[0]?.key).toEqual({ configured: true, source: "env" });
      expect(JSON.stringify(status)).not.toContain(fakeKey);
      expect(JSON.stringify([info.mock.calls, warn.mock.calls])).not.toContain(fakeKey);
      dispose();
    });
  });
});
