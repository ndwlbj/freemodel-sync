import { describe, expect, it, vi } from "vitest";
import { FreemodelApiClient, LocalApiError } from "../src/client/api.ts";
import { renderCard, TABS, type CardProps, type Tab } from "../src/client/card.ts";
import { createTranslator, resolveLocale } from "../src/client/i18n.ts";
import * as client from "../src/client/index.ts";
import { setReact, type ReactElementLike, type ReactLike } from "../src/client/react-runtime.ts";
import type { ManualTestView, StatusReport } from "../src/client/types.ts";

function fakeReact(): ReactLike {
  return {
    createElement(type, props, ...children) {
      const merged: Record<string, unknown> = { ...(props ?? {}) };
      if (children.length === 1) merged.children = children[0];
      else if (children.length > 1) merged.children = children;
      return { type, props: merged };
    },
    useState<T>(initial: T | (() => T)): [T, (next: T | ((previous: T) => T)) => void] {
      const value = typeof initial === "function" ? (initial as () => T)() : initial;
      return [value, () => undefined];
    },
    useEffect() {
      // The pure render tests do not run effects.
    },
    useCallback<T extends (...args: never[]) => unknown>(callback: T): T {
      return callback;
    },
    useMemo<T>(factory: () => T): T {
      return factory();
    },
    Fragment: Symbol("Fragment"),
  };
}

function textOf(node: unknown): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join(" ");
  if (typeof node === "object" && "props" in node) {
    return textOf((node as ReactElementLike).props.children);
  }
  return "";
}

function buttonsOf(node: unknown, found: ReactElementLike[] = []): ReactElementLike[] {
  if (node === null || node === undefined || typeof node !== "object") return found;
  if (Array.isArray(node)) {
    for (const child of node) buttonsOf(child, found);
    return found;
  }
  const element = node as ReactElementLike;
  if (element.type === "button") found.push(element);
  buttonsOf(element.props.children, found);
  return found;
}

const NOW = 1_700_000_000;

const STATUS: StatusReport = {
  schemaVersion: 2,
  plugin: "dsh-freemodel",
  version: "0.1.0",
  specVersion: 1,
  statePath: "/tmp/dsh/freemodel/state.json",
  stateExists: true,
  channels: [
    {
      id: "openrouter",
      route: "freemodel-openrouter",
      enabled: true,
      apiKeyEnv: "OPENROUTER_API_KEY",
      key: { configured: true, source: "file" },
      models: {
        catalogFetchedAt: NOW,
        catalogError: null,
        candidates: 3,
        listed: [{ id: "vendor/working:free", ttftMs: 142, testedAt: NOW - 60 }],
        hidden: [
          { id: "vendor/slow:free", reason: "temporarily unavailable 429: rate limited (retried later)" },
          { id: "vendor/untested:free", reason: "untested" },
        ],
        probesToday: 2,
        lastRound: { at: NOW - 60, probes: 3, stopReason: null },
        blockedUntil: null,
      },
    },
    {
      id: "groq",
      route: "freemodel-groq",
      enabled: false,
      apiKeyEnv: "GROQ_API_KEY",
      key: { configured: false },
      blocked: "freePlanConfirmed is off",
      models: {
        catalogFetchedAt: null,
        catalogError: null,
        candidates: 0,
        listed: [],
        hidden: [{ id: "llama-3.1-8b-instant", reason: "untested" }],
        probesToday: 0,
        lastRound: null,
        blockedUntil: null,
      },
    },
  ],
};

function props(tab: Tab, overrides: Partial<CardProps> = {}): CardProps {
  return {
    t: createTranslator("en"),
    tab,
    onTab: vi.fn(),
    state: { phase: "ready", status: STATUS, loadedAt: NOW },
    testing: {},
    onRefresh: vi.fn(),
    onTest: vi.fn(),
    ...overrides,
  };
}

function fakeCtx(localeActive = "zh-CN") {
  const registrations: Array<{ options: Record<string, unknown>; component: unknown }> = [];
  const slotDisposers: Array<() => void> = [];
  const effects: string[] = [];
  let localeActiveValue = localeActive;
  const locale = {
    getLocale: () => ({ active: localeActiveValue }),
    register: vi.fn(() => vi.fn()),
  };
  const ctx = {
    slots: {
      inject: vi.fn((_name: string, factory: () => unknown) => {
        const dispose = vi.fn();
        slotDisposers.push(dispose);
        factory();
        return dispose;
      }),
      register: vi.fn((options: Record<string, unknown>, component: unknown) => {
        registrations.push({ options, component });
        return vi.fn();
      }),
    },
    effect: vi.fn((fn: () => void | (() => void), label?: string) => {
      if (label !== undefined) effects.push(label);
      return fn();
    }),
    get: vi.fn((name: string) => (name === "locale" ? locale : undefined)),
    on: vi.fn(() => vi.fn()),
    setLocale: (value: string) => {
      localeActiveValue = value;
    },
  };
  return { ctx, registrations, slotDisposers, effects, locale };
}

describe("client module", () => {
  it("loads as a browser module and exports the loader contract", async () => {
    const loaded = await import("../src/client/index.ts");
    expect(loaded.name).toBe("dsh-freemodel-client");
    expect(loaded.inject).toEqual(["slots"]);
    expect(typeof loaded.apply).toBe("function");
  });

  it("registers the card on the bundle and row seats with the package key", () => {
    setReact(fakeReact());
    const { ctx, registrations, slotDisposers, effects, locale } = fakeCtx();
    client.apply(ctx as unknown as Parameters<typeof client.apply>[0]);

    expect(ctx.slots.inject).toHaveBeenCalledTimes(2);
    expect(ctx.slots.inject.mock.calls.map((call) => call[0])).toEqual([
      "plugins.bundle.config",
      "plugins.row.config",
    ]);
    expect(registrations).toHaveLength(2);
    expect(registrations.map((registration) => registration.options.key)).toEqual([
      "dsh-freemodel",
      "dsh-freemodel#dsh-freemodel",
    ]);
    for (const registration of registrations) {
      expect(registration.options.name).toMatch(/^plugins\.(bundle|row)\.config$/);
      expect(registration.component).toBeTypeOf("function");
      const face = (registration.options.inject as () => Record<string, unknown>)();
      expect(typeof face.t).toBe("function");
      expect(face.api).toBeInstanceOf(FreemodelApiClient);
    }
    expect(slotDisposers).toHaveLength(2);
    expect(effects).toContain("dsh-freemodel: card styles");
    expect(locale.register).toHaveBeenCalledWith("dsh-freemodel.client", expect.objectContaining({ zh: expect.any(Object), en: expect.any(Object) }));
  });

  it("renders all four tabs without throwing and shows model reasons", () => {
    setReact(fakeReact());
    const expected: Record<Tab, string[]> = {
      overview: ["At a glance", "OpenRouter", "FreeModel"],
      channels: ["Channels", "OPENROUTER_API_KEY", "configured", "freePlanConfirmed is off"],
      models: ["Models and probe results", "vendor/working:free", "vendor/untested:free", "Reason: untested", "Test now"],
      diagnostics: ["Diagnostics", "State file", "freePlanConfirmed is off", "dsh-freemodel doctor"],
    };

    for (const tab of TABS) {
      const tree = renderCard(props(tab));
      const text = textOf(tree);
      for (const needle of expected[tab]) expect(text, `${tab}: ${needle}`).toContain(needle);
      expect(buttonsOf(tree).length).toBeGreaterThan(0);
    }
  });

  it("shows the Chinese copy when the host locale is zh", () => {
    setReact(fakeReact());
    const tree = renderCard(props("models", { t: createTranslator(resolveLocale("zh-CN")) }));
    const text = textOf(tree);
    expect(text).toContain("模型与探测状态");
    expect(text).toContain("手动测试");
    expect(text).toContain("原因: untested");
  });

  it("invokes the manual test callback with the exact channel and model", () => {
    setReact(fakeReact());
    const onTest = vi.fn();
    const tree = renderCard(props("models", { onTest }));
    const testButton = buttonsOf(tree).find((button) => textOf(button).includes("Test now"));
    expect(testButton).toBeDefined();
    (testButton?.props.onClick as (() => void) | undefined)?.();
    expect(onTest).toHaveBeenCalledWith("openrouter", "vendor/working:free");
  });

  it("renders loading and error states without a fake status", () => {
    setReact(fakeReact());
    const loading = textOf(renderCard(props("overview", { state: { phase: "loading" } })));
    expect(loading).toContain("Reading status");
    const error = textOf(renderCard(props("overview", { state: { phase: "error", error: "HTTP 500" } })));
    expect(error).toContain("Could not read status");
    expect(error).toContain("HTTP 500");
  });
});

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

const TEST_RESULT: ManualTestView = {
  channel: "openrouter",
  model: "vendor/working:free",
  result: { ok: true, ttftMs: 120, error: null },
};

describe("FreemodelApiClient", () => {
  it("reads status, keeps the write token private and sends it on every test", async () => {
    const fetchImpl = vi.fn(async (input: string, init?: { method?: string; headers?: Record<string, string>; body?: string }) => {
      if (input.endsWith("/status")) return response({ ok: true, status: STATUS, writeToken: "write-token-0123456789" });
      if (input.endsWith("/test")) {
        expect(init?.method).toBe("POST");
        expect(init?.headers?.["x-freemodel-secret"]).toBe("write-token-0123456789");
        expect(JSON.parse(init?.body ?? "{}")).toEqual({ channel: "openrouter", model: "vendor/working:free" });
        return response({ ok: true, ...TEST_RESULT });
      }
      return response({ ok: false, error: { code: "not-found", message: "no route" } }, 404);
    });
    const api = new FreemodelApiClient(fetchImpl);
    const status = await api.load();
    expect(status.version).toBe("0.1.0");
    expect(api.hasWriteToken()).toBe(true);
    expect(JSON.stringify(api)).not.toContain("write-token");
    await expect(api.test("openrouter", "vendor/working:free")).resolves.toEqual(TEST_RESULT);
  });

  it("refuses before a POST when status did not hand out a token", async () => {
    const fetchImpl = vi.fn(async () => response({ ok: true, status: STATUS }));
    const api = new FreemodelApiClient(fetchImpl);
    await expect(api.test("openrouter", "vendor/working:free")).rejects.toMatchObject({ code: "missing-write-token" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("turns an error envelope into a readable LocalApiError", async () => {
    const fetchImpl = vi.fn(async () => response({ ok: false, error: { code: "no-key", message: "no key: save one" } }, 409));
    const api = new FreemodelApiClient(fetchImpl);
    await expect(api.load()).rejects.toBeInstanceOf(LocalApiError);
    await expect(api.load()).rejects.toMatchObject({ code: "no-key", status: 409 });
  });
});