import { describe, expect, it, vi } from "vitest";
import { createFreemodelCommand, formatStatus, USAGE } from "../src/command.ts";
import { ManualTestError, type ManualTestOutcome } from "../src/service.ts";
import type { StatusReport } from "../src/status.ts";
import { model } from "./helpers/fake-fetch.ts";

function report(): StatusReport {
  return {
    schemaVersion: 2,
    plugin: "dsh-freemodel",
    version: "0.1.0",
    specVersion: 1,
    statePath: "/tmp/fm/state.json",
    stateExists: true,
    channels: [
      {
        id: "openrouter",
        route: "freemodel-openrouter",
        enabled: true,
        apiKeyEnv: "OPENROUTER_API_KEY",
        key: { configured: true, source: "file" },
        models: {
          catalogFetchedAt: 1_700_000_000,
          catalogError: null,
          candidates: 2,
          listed: [{ id: "vendor/model:free", ttftMs: 123.4, testedAt: 1_700_000_100 }],
          hidden: [{ id: "vendor/other:free", reason: "failed: HTTP 400" }],
          probesToday: 1,
          lastRound: { at: 1_700_000_100, probes: 1, stopReason: null },
          blockedUntil: null,
        },
      },
      {
        id: "groq",
        route: "freemodel-groq",
        enabled: false,
        apiKeyEnv: "GROQ_API_KEY",
        key: { configured: false },
        models: {
          catalogFetchedAt: null,
          catalogError: null,
          candidates: 0,
          listed: [],
          hidden: [],
          probesToday: 0,
          lastRound: null,
          blockedUntil: null,
        },
      },
    ],
  };
}

function deps() {
  const status = vi.fn(async () => report());
  const refresh = vi.fn(async () => undefined);
  const testModel = vi.fn(
    async (channel: "openrouter" | "groq", id: string): Promise<ManualTestOutcome> => ({
      channel,
      model: model(id, { provider: channel }),
      result: {
        key: `${channel}|${id}`,
        ok: true,
        ttftMs: 120,
        totalMs: 340,
        error: null,
        statusCode: 200,
        testedAt: 1_700_000_200,
        failureKind: null,
        retryAfterS: null,
        rateLimitRemaining: null,
      },
    }),
  );
  return { status, refresh, testModel };
}

describe("/freemodel command", () => {
  it("defaults to status and mirrors the CLI's report", async () => {
    const d = deps();
    const command = createFreemodelCommand(d);
    expect(command.name).toBe("freemodel");
    expect(command.input.hint).toContain("test <channel> <model>");

    const result = await command.handler({ rawInput: "" });
    expect(result.kind).toBe("success");
    expect(result.text).toContain("dsh-freemodel 0.1.0 (spec v1)");
    expect(result.text).toContain("openrouter on ");
    expect(result.text).toContain("key OPENROUTER_API_KEY: configured (file)");
    expect(result.text).toContain("+ vendor/model:free  (TTFT 123 ms)");
    expect(result.text).toContain("- vendor/other:free  failed: HTTP 400");
    expect(result.text).toContain("groq");
    expect(d.status).toHaveBeenCalledTimes(1);
    expect(d.refresh).not.toHaveBeenCalled();
  });

  it("rejects arguments to status and refresh", async () => {
    const command = createFreemodelCommand(deps());
    const status = await command.handler({ rawInput: "status now" });
    expect(status).toEqual({ kind: "error", text: `status takes no arguments. ${USAGE}` });
    const refresh = await command.handler({ rawInput: "refresh now" });
    expect(refresh).toEqual({ kind: "error", text: `refresh takes no arguments. ${USAGE}` });
  });

  it("refreshes and reports the resulting per-channel summary", async () => {
    const d = deps();
    const command = createFreemodelCommand(d);
    const result = await command.handler({ rawInput: "  refresh  " });
    expect(d.refresh).toHaveBeenCalledTimes(1);
    expect(result).toEqual({
      kind: "success",
      text: "refresh complete — openrouter: 1 listed, 1 hidden; groq: off",
    });
  });

  it("tests exactly one channel and model", async () => {
    const d = deps();
    const command = createFreemodelCommand(d);
    const result = await command.handler({ rawInput: "test openrouter vendor/model:free" });
    expect(d.testModel).toHaveBeenCalledWith("openrouter", "vendor/model:free");
    expect(result).toEqual({ kind: "success", text: "test openrouter/vendor/model:free: ok, TTFT 120 ms" });
  });

  it("formats failed probes without inventing a status", async () => {
    const d = deps();
    d.testModel.mockResolvedValueOnce({
      channel: "openrouter",
      model: model("bad/model"),
      result: {
        key: "openrouter|bad/model",
        ok: false,
        ttftMs: null,
        totalMs: null,
        error: "rate limited",
        statusCode: 429,
        testedAt: 1_700_000_200,
        failureKind: "transient",
        retryAfterS: 60,
        rateLimitRemaining: 0,
      },
    });
    const result = await createFreemodelCommand(d).handler({ rawInput: "test openrouter bad/model" });
    expect(result).toEqual({ kind: "success", text: "test openrouter/bad/model: failed (HTTP 429) [transient]: rate limited" });
  });

  it("rejects missing, extra and unknown test arguments", async () => {
    const d = deps();
    const command = createFreemodelCommand(d);
    expect((await command.handler({ rawInput: "test" })).kind).toBe("error");
    expect((await command.handler({ rawInput: "test openrouter" })).kind).toBe("error");
    expect((await command.handler({ rawInput: "test openrouter model extra" })).kind).toBe("error");
    expect(await command.handler({ rawInput: "test deepseek model" })).toEqual({
      kind: "error",
      text: "unknown channel deepseek; use one of: openrouter, groq",
    });
    expect(d.testModel).not.toHaveBeenCalled();
  });

  it("reports unknown subcommands", async () => {
    const command = createFreemodelCommand(deps());
    expect(await command.handler({ rawInput: "doctor" })).toEqual({
      kind: "error",
      text: `unknown subcommand doctor. ${USAGE}`,
    });
  });

  it("turns service refusals and unexpected failures into error results", async () => {
    const d = deps();
    d.testModel.mockRejectedValueOnce(new ManualTestError("no-key", "no key: save one for OPENROUTER_API_KEY"));
    const refused = await createFreemodelCommand(d).handler({ rawInput: "test openrouter x" });
    expect(refused).toEqual({ kind: "error", text: "test failed — no-key: no key: save one for OPENROUTER_API_KEY" });

    d.refresh.mockRejectedValueOnce(new Error("catalogue down"));
    const failed = await createFreemodelCommand(d).handler({ rawInput: "refresh" });
    expect(failed).toEqual({ kind: "error", text: "refresh failed — catalogue down" });
  });

  it("exposes the formatter for the same output without the command", () => {
    const text = formatStatus(report());
    expect(text.split("\n")[0]).toBe("dsh-freemodel 0.1.0 (spec v1)");
    expect(text).toContain("state: /tmp/fm/state.json");
  });
});