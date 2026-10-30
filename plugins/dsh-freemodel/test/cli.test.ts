import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { main } from "../src/bin.ts";
import { emptyState, saveState } from "../src/state.ts";
import { describeFromEnv, installedDshVersion, runDoctor, statePath } from "../src/status.ts";

function run(argv: string[], env: NodeJS.ProcessEnv = {}, cwd = tmpdir(), dshCli?: string) {
  const out: string[] = [];
  const err: string[] = [];
  const io = { out: (l: string) => out.push(l), err: (l: string) => err.push(l), env, cwd, dshCliVersion: () => dshCli };
  return main(argv, io).then((code) => ({
    code,
    out: out.join("\n"),
    err: err.join("\n"),
  }));
}

const fakeKey = ["sk", "or", "v1", "f".repeat(64)].join("-");

describe("dsh-freemodel CLI", () => {
  it("prints the version and help", async () => {
    expect((await run(["--version"])).out).toBe("1.0.0");
    expect((await run(["--help"])).out).toContain("usage: dsh-freemodel");
  });

  it("rejects unknown commands with exit 2", async () => {
    for (const argv of [[], ["nope"], ["status", "extra"]]) {
      const result = await run(argv);
      expect(result.code).toBe(2);
      expect(result.err).toContain("usage:");
    }
  });

  it("status shows key presence, never the key", async () => {
    const home = mkdtempSync(join(tmpdir(), "fm-home-"));
    const result = await run(["status"], { DSH_HOME: home, OPENROUTER_API_KEY: fakeKey });
    expect(result.code).toBe(0);
    expect(result.out).toContain("OPENROUTER_API_KEY: configured (env)");
    expect(result.out).toContain("GROQ_API_KEY: not set");
    expect(result.out).toContain(join(home, "freemodel", "state.json"));
    expect(result.out).toContain("(not created yet)");
    expect(result.out).not.toContain(fakeKey);
    expect(result.out).not.toContain("f".repeat(16));
  });

  it("status --json is machine-readable and notices an existing state file", async () => {
    const home = mkdtempSync(join(tmpdir(), "fm-home-"));
    mkdirSync(join(home, "freemodel"));
    writeFileSync(join(home, "freemodel", "state.json"), "{}");
    const result = await run(["status", "--json"], { DSH_HOME: home, OPENROUTER_API_KEY: fakeKey });
    const report = JSON.parse(result.out);
    expect(report).toMatchObject({ schemaVersion: 2, plugin: "dsh-freemodel", version: "1.0.0", stateExists: true });
    expect(report.channels.map((c: { route: string }) => c.route)).toEqual(["freemodel-openrouter", "freemodel-groq", "freemodel-sensenova", "freemodel-bailian"]);
    expect(report.channels[0].models).toMatchObject({ catalogFetchedAt: null, listed: [], hidden: [] });
    expect(result.out).not.toContain(fakeKey);
  });

  it("status lists the models that passed and why the others are hidden, from the state file", async () => {
    const home = mkdtempSync(join(tmpdir(), "fm-home-"));
    const state = emptyState();
    const nowS = Date.now() / 1000;
    const m = (id: string) => ({ provider: "openrouter" as const, id, name: id, contextLength: 131072, tools: true, input: ["text" as const], maxTokens: null, expirationDate: null, capabilities: { tools: true, vision: false, reasoning: false, source: "catalog" as const }, quota: null, tier: 1 });
    state.channels.openrouter.catalog = { fetchedAt: nowS, models: [m("good:free"), m("bad:free"), m("new:free")], error: null, errorAt: null };
    const base = { totalMs: 1, testedAt: nowS, retryAfterS: null, rateLimitRemaining: null };
    state.channels.openrouter.results["openrouter|good:free"] = { ...base, key: "openrouter|good:free", ok: true, ttftMs: 321, error: null, statusCode: 200, failureKind: null };
    state.channels.openrouter.results["openrouter|bad:free"] = { ...base, key: "openrouter|bad:free", ok: false, ttftMs: null, error: "No endpoints found", statusCode: 404, failureKind: "model" };
    saveState(statePath({ DSH_HOME: home }), state);
    const result = await run(["status"], { DSH_HOME: home });
    expect(result.out).toContain("+ good:free  (TTFT 321 ms)");
    expect(result.out).toContain("- bad:free  failed: No endpoints found");
    expect(result.out).toContain("- new:free  not probed yet");
    expect(result.out).toMatch(/openrouter: catalogue read .* UTC, 3 candidates, 1 listed/);
  });

  it("doctor finds the dsh runtime from a profile directory", async () => {
    // The plugin's own devDependencies include @deepseek-ai/dsh-llm, as a profile does.
    const result = await run(["doctor"], { OPENROUTER_API_KEY: fakeKey }, process.cwd());
    expect(result.out).toMatch(/ok {4}dsh 0\.2\.1-rc\.\d+ \(installed package\) satisfies engines\.dsh/);
    expect(result.code).toBe(0);
  });

  it("doctor --json warns when no dsh runtime is reachable or a key is missing", async () => {
    const result = await run(["doctor", "--json"], {}, mkdtempSync(join(tmpdir(), "fm-empty-")));
    const report = JSON.parse(result.out);
    expect(report.ok).toBe(true);
    const levels = Object.fromEntries(report.checks.map((c: { id: string; level: string }) => [c.id, c.level]));
    expect(levels).toMatchObject({
      node: "ok",
      dsh: "warn",
      spec: "ok",
      "key:openrouter": "warn",
      "key:groq": "ok",
      "key:sensenova": "ok",
      "key:bailian": "ok",
    });
  });
});

describe("doctor's dsh lookup", () => {
  const empty = () => mkdtempSync(join(tmpdir(), "fm-empty-"));

  it("falls back to `dsh --version` when no dsh package is beside cwd (as under `dsh plugin exec`)", async () => {
    const result = await run(["doctor"], {}, empty(), "0.2.1-rc.3");
    expect(result.out).toContain("ok    dsh 0.2.1-rc.3 (`dsh --version`) satisfies engines.dsh");
  });

  it("prefers --dsh-version, and fails when it is out of range", async () => {
    const result = await run(["doctor", "--dsh-version", "0.3.0", "--json"], {}, empty(), "0.2.1-rc.3");
    const dsh = JSON.parse(result.out).checks.find((c: { id: string }) => c.id === "dsh");
    expect(dsh.level).toBe("fail");
    expect(result.code).toBe(1);
  });

  it.each([[["doctor", "--dsh-version"]], [["doctor", "--dsh-version", "latest"]], [["status", "--dsh-version", "0.2.1"]]])(
    "rejects a bad --dsh-version use: %j",
    async (argv) => {
      expect((await run(argv)).code).toBe(2);
    },
  );
});

describe("doctor checks", () => {
  it("fails on an unsupported Node.js or dsh", async () => {
    const report = await runDoctor({ env: {}, nodeVersion: "20.19.0", dshVersion: "0.3.0" });
    expect(report.ok).toBe(false);
    expect(report.checks.filter((c) => c.level === "fail").map((c) => c.id)).toEqual(["node", "dsh"]);
  });

  it("uses the process environment by default", async () => {
    const report = await runDoctor();
    expect(report.checks[0]?.id).toBe("node");
    expect(statePath()).toMatch(/freemodel[\\/]state\.json$/);
    expect(await describeFromEnv()("DSH_FREEMODEL_SURELY_UNSET")).toEqual({ configured: false });
    expect(installedDshVersion(mkdtempSync(join(tmpdir(), "fm-none-")))).toBeUndefined();
  });
});
