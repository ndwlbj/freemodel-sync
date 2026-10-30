import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyDefaultModelSwitch,
  assertSafeProfile,
  planDefaultModelSwitch,
  QQ_PROFILE_DENY,
  resetLastDefaultModelLog,
  resolveProfile,
  updateDefaultModelPatch,
} from "../src/default-model.ts";

describe("resolveProfile helper", () => {
  it("resolves profileContext name and dir when present", () => {
    const get = (k: string) => (k === "profileContext" ? { name: "fmtest", dir: "/tmp/profiles/fmtest" } : undefined);
    const profile = resolveProfile(get, {});
    expect(profile).toEqual({ name: "fmtest", dir: "/tmp/profiles/fmtest" });
  });

  it("resolves profileContext name when dir is absent or empty", () => {
    const get = (k: string) => (k === "profileContext" ? { name: "fmtest" } : undefined);
    expect(resolveProfile(get, {})).toEqual({ name: "fmtest" });

    const getEmptyDir = (k: string) => (k === "profileContext" ? { name: "fmtest", dir: "  " } : undefined);
    expect(resolveProfile(getEmptyDir, {})).toEqual({ name: "fmtest" });
  });

  it("accepts an object with a get method", () => {
    const ctx = {
      get: (k: string) => (k === "profileContext" ? { name: "ctx-test", dir: "/data/profiles/ctx-test" } : undefined),
    };
    expect(resolveProfile(ctx, {})).toEqual({ name: "ctx-test", dir: "/data/profiles/ctx-test" });
  });

  it("falls back to env DSH_PROFILE when profileContext is absent", () => {
    const get = (_k: string) => undefined;
    expect(resolveProfile(get, { DSH_PROFILE: "profile-from-env" })).toEqual({ name: "profile-from-env" });
  });

  it("falls back to env DSH_PROFILE when getter is undefined or null", () => {
    expect(resolveProfile(undefined, { DSH_PROFILE: "profile-from-env" })).toEqual({ name: "profile-from-env" });
    expect(resolveProfile(null, { DSH_PROFILE: "profile-from-env" })).toEqual({ name: "profile-from-env" });
  });

  it("never throws when getter throws and falls back to env DSH_PROFILE", () => {
    const throwingGet = () => {
      throw new Error("context access failed");
    };
    expect(resolveProfile(throwingGet, { DSH_PROFILE: "env-fallback" })).toEqual({ name: "env-fallback" });
    expect(resolveProfile(throwingGet, {})).toBeUndefined();
  });

  it("returns undefined when neither source gives a name", () => {
    const get = () => undefined;
    expect(resolveProfile(get, {})).toBeUndefined();
    expect(resolveProfile(get, { DSH_PROFILE: "  " })).toBeUndefined();
    expect(resolveProfile(() => ({ name: "   " }), {})).toBeUndefined();
    expect(resolveProfile(() => "not an object", {})).toBeUndefined();
  });
});

describe("default-model planning", () => {
  it("skips planning when autoDefaultModel is off", () => {
    const plan = planDefaultModelSwitch({
      enabled: false,
      profileId: "work-profile",
      autoRouteEnabled: true,
      top: { route: "freemodel-openrouter", modelId: "test:free" },
    });
    expect(plan.action).toBe("skipped");
    expect(plan.reason).toBe("autoDefaultModel is off");
  });

  it("skips planning when no profileId is supplied", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: undefined,
      autoRouteEnabled: true,
      top: { route: "freemodel-openrouter", modelId: "test:free" },
    });
    expect(plan.action).toBe("skipped");
    expect(plan.reason).toBe("no current profile");
  });

  it("skips planning and identifies QQ/bot profiles without throwing at plan time", () => {
    for (const name of ["qq-bot", "napcat_main", "my-astrbot", "onebot-worker", "test-BOT"]) {
      expect(QQ_PROFILE_DENY.test(name)).toBe(true);
      const plan = planDefaultModelSwitch({
        enabled: true,
        profileId: name,
        autoRouteEnabled: true,
        top: { route: "freemodel-openrouter", modelId: "test:free" },
      });
      expect(plan.action).toBe("skipped");
      expect(plan.reason).toContain("QQ/bot profile");
    }
  });

  it("assertSafeProfile throws on denied QQ/bot profiles", () => {
    expect(() => assertSafeProfile("my-qq-bot")).toThrow(/QQ\/bot profile/);
    expect(() => assertSafeProfile("onebot")).toThrow(/QQ\/bot profile/);
    expect(() => assertSafeProfile("work-profile")).not.toThrow();
  });

  it("targets freemodel-auto/best when autoRoute is enabled", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: "agent-session",
      autoRouteEnabled: true,
      top: { route: "freemodel-openrouter", modelId: "other:free" },
    });
    expect(plan.action).toBe("would-write");
    expect(plan.provider).toBe("freemodel-auto");
    expect(plan.model).toBe("best");
  });

  it("targets the top model pair when autoRoute is off but a top model exists", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: "agent-session",
      autoRouteEnabled: false,
      top: { route: "freemodel-groq", modelId: "llama-3-free" },
    });
    expect(plan.action).toBe("would-write");
    expect(plan.provider).toBe("freemodel-groq");
    expect(plan.model).toBe("llama-3-free");
  });

  it("skips when autoRoute is off and no models are listed", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: "agent-session",
      autoRouteEnabled: false,
      top: null,
    });
    expect(plan.action).toBe("skipped");
    expect(plan.reason).toBe("no listed model");
  });
});

describe("applyDefaultModelSwitch safety guards", () => {
  beforeEach(() => {
    resetLastDefaultModelLog();
  });
  it("refuses to apply to denied QQ/bot profiles by throwing an error", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: "work-profile",
      autoRouteEnabled: true,
    });
    // If a plan somehow has a denied profile at apply time:
    const deniedPlan = { ...plan, profileId: "my-qq-assistant" };
    expect(() =>
      applyDefaultModelSwitch(deniedPlan, {
        readPatch: () => "",
        writePatch: vi.fn(),
        profilePatchPath: "/tmp/profiles/my-qq-assistant/cordis.patch.yml",
        env: { DSH_FREEMODEL_APPLY_DEFAULT: "1" },
      }),
    ).toThrow(/QQ\/bot profile/);
  });

  it("refuses writing when profilePatchPath equals home patch path", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: "dev-profile",
      autoRouteEnabled: true,
    });

    expect(() =>
      applyDefaultModelSwitch(plan, {
        readPatch: () => "",
        writePatch: vi.fn(),
        profilePatchPath: "/home/box/.dsh/cordis.patch.yml",
        homePatchPath: "/home/box/.dsh/cordis.patch.yml",
        env: { DSH_FREEMODEL_APPLY_DEFAULT: "1" },
      }),
    ).toThrow(/home layer patch/);
  });

  it("refuses writing when profilePatchPath resolves to $DSH_HOME/cordis.patch.yml", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: "dev-profile",
      autoRouteEnabled: true,
    });

    expect(() =>
      applyDefaultModelSwitch(plan, {
        readPatch: () => "",
        writePatch: vi.fn(),
        profilePatchPath: "/data/dsh/cordis.patch.yml",
        env: { DSH_HOME: "/data/dsh", DSH_FREEMODEL_APPLY_DEFAULT: "1" },
      }),
    ).toThrow(/\$DSH_HOME layer patch/);
  });

  it("returns action: would-write when DSH_FREEMODEL_APPLY_DEFAULT is not 1", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: "dev-profile",
      autoRouteEnabled: true,
    });
    const writePatch = vi.fn();
    const infoLog = vi.fn();

    const applied = applyDefaultModelSwitch(plan, {
      readPatch: () => "",
      writePatch,
      profilePatchPath: "/home/box/.dsh/profiles/dev-profile/cordis.patch.yml",
      homePatchPath: "/home/box/.dsh/cordis.patch.yml",
      env: {}, // no apply flag
      logger: { info: infoLog },
    });

    expect(applied.action).toBe("would-write");
    expect(applied.reason).toContain("DSH_FREEMODEL_APPLY_DEFAULT=1 is not set");
    expect(writePatch).not.toHaveBeenCalled();
    expect(infoLog).toHaveBeenCalledWith(expect.stringContaining("would write"));
  });

  it("applies the change when DSH_FREEMODEL_APPLY_DEFAULT=1 is set", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: "dev-profile",
      autoRouteEnabled: true,
    });
    const writePatch = vi.fn();
    const infoLog = vi.fn();

    const existingPatch = `# User config\n- id: cordis-console\n  config: {port: 8080}\n`;

    const applied = applyDefaultModelSwitch(plan, {
      readPatch: () => existingPatch,
      writePatch,
      profilePatchPath: "/home/box/.dsh/profiles/dev-profile/cordis.patch.yml",
      homePatchPath: "/home/box/.dsh/cordis.patch.yml",
      env: { DSH_FREEMODEL_APPLY_DEFAULT: "1" },
      logger: { info: infoLog },
    });

    expect(applied.action).toBe("applied");
    expect(writePatch).toHaveBeenCalledTimes(1);
    const writtenText = writePatch.mock.calls[0]?.[1] as string;
    expect(writtenText).toContain("- id: agent-default-model");
    expect(writtenText).toContain("config: {provider: freemodel-auto, model: 'best'}");
    expect(writtenText).toContain("# User config");
  });

  it("logs once on two consecutive apply calls with the same plan (would-write and applied)", () => {
    const plan = planDefaultModelSwitch({
      enabled: true,
      profileId: "dev-profile",
      autoRouteEnabled: true,
    });
    const infoLog = vi.fn();
    const deps = {
      readPatch: () => "",
      writePatch: vi.fn(),
      profilePatchPath: "/home/box/.dsh/profiles/dev-profile/cordis.patch.yml",
      homePatchPath: "/home/box/.dsh/cordis.patch.yml",
      env: {}, // would-write
      logger: { info: infoLog },
    };

    // First call logs
    applyDefaultModelSwitch(plan, deps);
    expect(infoLog).toHaveBeenCalledTimes(1);
    expect(infoLog.mock.calls[0]?.[0]).toContain("would write");

    // Second consecutive call with identical plan and path does not log
    applyDefaultModelSwitch(plan, deps);
    expect(infoLog).toHaveBeenCalledTimes(1);

    // When applied with env flag set, action changes to "applied", so it logs once
    const applyDeps = { ...deps, env: { DSH_FREEMODEL_APPLY_DEFAULT: "1" } };
    applyDefaultModelSwitch(plan, applyDeps);
    expect(infoLog).toHaveBeenCalledTimes(2);
    expect(infoLog.mock.calls[1]?.[0]).toContain("updated agent-default-model");

    // Consecutive applied call with same plan does not log again
    applyDefaultModelSwitch(plan, applyDeps);
    expect(infoLog).toHaveBeenCalledTimes(2);
  });
});

describe("updateDefaultModelPatch", () => {
  it("creates a new block when file is empty", () => {
    const result = updateDefaultModelPatch("", { provider: "freemodel-auto", model: "best" });
    expect(result).toBe("- id: agent-default-model\n  name: '@deepseek-ai/dsh-agent-default-model'\n  config: {provider: freemodel-auto, model: 'best'}\n");
  });

  it("updates existing flow-style config and preserves comments and entry name", () => {
    const original = `# Keep this header comment\n- id: other-service\n  config: {}\n\n- id: agent-default-model\n  name: 'my-custom-name'\n  config: {provider: old-prov, model: 'old:model'}\n\n# Footer comment\n`;
    const updated = updateDefaultModelPatch(original, { provider: "freemodel-auto", model: "best" });
    expect(updated).toContain("# Keep this header comment");
    expect(updated).toContain("# Footer comment");
    expect(updated).toContain("name: 'my-custom-name'");
    expect(updated).toContain("config: {provider: freemodel-auto, model: 'best'}");
    expect(updated).not.toContain("old-prov");
  });

  it("updates multiline config block cleanly", () => {
    const original = `- id: agent-default-model\n  name: '@deepseek-ai/dsh-agent-default-model'\n  config:\n    provider: old-prov\n    model: old-model\n- id: after-entry\n  config: {}\n`;
    const updated = updateDefaultModelPatch(original, { provider: "freemodel-groq", model: "llama-3-free" });
    expect(updated).toContain("config: {provider: freemodel-groq, model: 'llama-3-free'}");
    expect(updated).toContain("- id: after-entry");
    expect(updated).not.toContain("old-prov");
  });
});
