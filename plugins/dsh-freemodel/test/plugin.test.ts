import { describe, expect, it, vi } from "vitest";
import * as plugin from "../src/index.ts";

function fakeCtx(credentials?: unknown) {
  const info = vi.fn();
  const warn = vi.fn();
  const ctx = {
    get: vi.fn((service: string) => (service === "credentials" ? credentials : undefined)),
    logger: { info, warn },
  };
  return { ctx: ctx as unknown as Parameters<typeof plugin.apply>[0], info, warn };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("plugin entry", () => {
  it("exports what the Cordis loader needs", () => {
    expect(plugin.name).toBe("dsh-freemodel");
    expect(plugin.inject).toEqual(["llm"]);
    expect(typeof plugin.apply).toBe("function");
    expect(typeof plugin.Config).toBe("function");
  });

  it("mounts, asks the credential service only whether keys exist, and logs a summary", async () => {
    const describeRef = vi.fn(async (ref: string) =>
      ref === "OPENROUTER_API_KEY" ? { configured: true, source: "file", writable: true } : { configured: false, writable: true },
    );
    const credentials = { describe: describeRef, resolve: vi.fn() };
    const { ctx, info, warn } = fakeCtx(credentials);
    plugin.apply(ctx, plugin.Config({}));
    await settle();
    expect(describeRef).toHaveBeenCalledWith("OPENROUTER_API_KEY");
    expect(credentials.resolve).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
    expect(info).toHaveBeenCalledTimes(1);
    expect(info.mock.calls[0]?.[0]).toBe(
      "dsh-freemodel 0.1.0 mounted; openrouter=on (key configured), groq=off (no key); no routes registered (skeleton)",
    );
  });

  it("works without a credential service and shows the Groq confirmation gap", async () => {
    const { ctx, info } = fakeCtx(undefined);
    plugin.apply(ctx, plugin.Config({ providers: { groq: { enabled: true } } }));
    await settle();
    expect(info.mock.calls[0]?.[0]).toContain("groq=on (key unknown, freePlanConfirmed is off)");
  });

  it("treats a failing lookup as unknown", async () => {
    const { ctx, info } = fakeCtx({ describe: vi.fn(async () => Promise.reject(new Error("locked"))) });
    plugin.apply(ctx, plugin.Config({}));
    await settle();
    expect(info.mock.calls[0]?.[0]).toContain("openrouter=on (key unknown)");
  });

  it("logs a warning if the status check itself fails", async () => {
    const { ctx, warn } = fakeCtx(undefined);
    plugin.apply(ctx, { providers: {} } as never);
    await settle();
    expect(warn).toHaveBeenCalledTimes(1);
  });
});
