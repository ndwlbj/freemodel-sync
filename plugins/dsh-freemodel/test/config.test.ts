import { describe, expect, it } from "vitest";
import {
  autoDefaultModelOf,
  autoRouteOf,
  channelStates,
  defaultAutoRoute,
  defaultProviders,
  defaultRanking,
  defaultRefresh,
  providersOf,
  rankingOf,
  refreshOf,
  routeOf,
} from "../src/channels.ts";
import { Config } from "../src/config.ts";
import { providerSpec } from "../src/spec.ts";

type Node = { type: string; meta: Record<string, unknown>; dict?: Record<string, Node> };
const schema = Config as unknown as Node;
const field = (...path: string[]): Node =>
  path.reduce<Node>((node, key) => {
    const next = node.dict?.[key];
    if (next === undefined) throw new Error(`no field ${path.join(".")}`);
    return next;
  }, schema);

describe("Config", () => {
  it("defaults: OpenRouter on, Groq off and unconfirmed, key names from the spec", () => {
    expect(providersOf(Config({}))).toEqual({
      openrouter: { enabled: true, apiKeyEnv: providerSpec("openrouter").apiKeyEnv },
      groq: { enabled: false, apiKeyEnv: providerSpec("groq").apiKeyEnv, freePlanConfirmed: false },
      sensenova: {
        enabled: false,
        apiKeyEnv: providerSpec("sensenova").apiKeyEnv,
        tokenPlanConfirmed: false,
        models: [],
      },
      bailian: {
        enabled: false,
        apiKeyEnv: providerSpec("bailian").apiKeyEnv,
        freeQuotaGuardConfirmed: false,
        models: [],
      },
    });
  });

  it("validates to the same defaults the CLI uses", () => {
    expect(providersOf(Config({}))).toEqual(defaultProviders());
  });

  it("keeps the channel settings live, so the settings page shows them and edits apply without a restart", () => {
    // dsh-settings only builds a form from `.volatile()` nodes.
    expect(field("providers").meta.volatile).toBe(true);
    expect(typeof (Config({}).providers as { get?: unknown }).get).toBe("function");
    expect(providersOf({ providers: providersOf(Config({})) }).openrouter.enabled).toBe(true);
  });

  it("marks every apiKeyEnv as a credential reference", () => {
    for (const channel of ["openrouter", "groq", "sensenova", "bailian"]) {
      expect(field("providers", channel, "apiKeyEnv").meta.role).toBe("credential-ref");
    }
  });

  it("describes every field", () => {
    const walk = (node: Node, path: string): void => {
      for (const [key, child] of Object.entries(node.dict ?? {})) {
        expect(typeof child.meta.description, `${path}${key}`).toBe("string");
        walk(child, `${path}${key}.`);
      }
    };
    walk(schema, "");
  });

  it("accepts another variable name and keeps other defaults", () => {
    const providers = providersOf(Config({ providers: { openrouter: { apiKeyEnv: "MY_OR_KEY" } } }));
    expect(providers.openrouter).toEqual({ enabled: true, apiKeyEnv: "MY_OR_KEY" });
    expect(providers.groq.enabled).toBe(false);
  });

  it("refuses anything that is not a variable name (a pasted key, for instance)", () => {
    const pasted = ["sk", "or", "v1", "0".repeat(8)].join("-");
    expect(() => Config({ providers: { openrouter: { apiKeyEnv: pasted } } })).toThrow(/apiKeyEnv/);
    expect(() => Config({ providers: { groq: { apiKeyEnv: "has space" } } })).toThrow(/apiKeyEnv/);
  });

  it("has no field that could hold a secret value", () => {
    const names: string[] = [];
    const walk = (node: Node): void => {
      for (const [key, child] of Object.entries(node.dict ?? {})) {
        names.push(key);
        walk(child);
      }
    };
    walk(schema);
    expect(names.filter((n) => /^(token|secret|password|cookie|key|apiKey)$/i.test(n))).toEqual([]);
  });
});

describe("channelStates", () => {
  it("lists every channel with its route", () => {
    expect(channelStates(Config({}))).toEqual([
      { id: "openrouter", route: "freemodel-openrouter", enabled: true, apiKeyEnv: "OPENROUTER_API_KEY" },
      { id: "groq", route: "freemodel-groq", enabled: false, apiKeyEnv: "GROQ_API_KEY" },
      {
        id: "sensenova",
        route: "freemodel-sensenova",
        enabled: false,
        apiKeyEnv: "SENSENOVA_API_KEY",
      },
      {
        id: "bailian",
        route: "freemodel-bailian",
        enabled: false,
        apiKeyEnv: "DASHSCOPE_API_KEY",
      },
    ]);
    expect(routeOf("groq")).toBe("freemodel-groq");
  });

  it("flags an enabled SenseNova channel without the token-plan confirmation", () => {
    const sensenova = channelStates(
      Config({ providers: { sensenova: { enabled: true, tokenPlanConfirmed: false } } }),
    ).find((entry) => entry.id === "sensenova");
    expect(sensenova?.blocked).toBe("tokenPlanConfirmed is off");
    const confirmed = channelStates(
      Config({ providers: { sensenova: { enabled: true, tokenPlanConfirmed: true } } }),
    ).find((entry) => entry.id === "sensenova");
    expect(confirmed?.blocked).toBeUndefined();
    expect(routeOf("sensenova")).toBe("freemodel-sensenova");
  });

  it("flags an enabled Bailian channel without the guard or allowlist", () => {
    const guardOff = channelStates(Config({ providers: { bailian: { enabled: true } } })).find(
      (entry) => entry.id === "bailian",
    );
    expect(guardOff?.blocked).toBe("freeQuotaGuardConfirmed is off");
    const noModels = channelStates(
      Config({ providers: { bailian: { enabled: true, freeQuotaGuardConfirmed: true } } }),
    ).find((entry) => entry.id === "bailian");
    expect(noModels?.blocked).toBe("models is empty");
    const ready = channelStates(
      Config({
        providers: {
          bailian: {
            enabled: true,
            freeQuotaGuardConfirmed: true,
            models: [{ id: "deepseek-v3.2", quotaTokens: 1000000 }],
          },
        },
      }),
    ).find((entry) => entry.id === "bailian");
    expect(ready?.blocked).toBeUndefined();
    expect(routeOf("bailian")).toBe("freemodel-bailian");
  });

  it("flags an enabled Groq channel without the free-plan confirmation", () => {
    const groq = channelStates(Config({ providers: { groq: { enabled: true } } }))[1];
    expect(groq?.blocked).toBe("freePlanConfirmed is off");
    const confirmed = channelStates(Config({ providers: { groq: { enabled: true, freePlanConfirmed: true } } }))[1];
    expect(confirmed?.blocked).toBeUndefined();
  });
});

describe("ranking and refresh settings", () => {
  it("default to the plan's values", () => {
    const config = Config({});
    expect(rankingOf(config)).toEqual(defaultRanking());
    expect(refreshOf(config)).toEqual(defaultRefresh());
    expect(defaultRanking()).toEqual({ requireTools: true, minContext: 32000, capacityDowngradeAfter: 3 });
    expect(defaultRefresh()).toEqual({
      onStartup: true,
      catalogHours: 6,
      probeHours: 12,
      probeTopN: 5,
      reserveRequests: 10,
      dailyProbeLimit: 0,
    });
  });

  it("accept overrides and refuse out-of-range values", () => {
    expect(refreshOf(Config({ refresh: { probeTopN: 3 } })).probeTopN).toBe(3);
    expect(rankingOf(Config({ ranking: { minContext: 8000 } })).minContext).toBe(8000);
    expect(() => Config({ refresh: { probeTopN: 0 } })).toThrow();
    expect(() => Config({ refresh: { catalogHours: 0.5 } })).toThrow();
    expect(() => Config({ ranking: { minContext: -1 } })).toThrow();
  });

  it("are live, so edits apply without a restart", () => {
    expect(field("ranking").meta.volatile).toBe(true);
    expect(field("refresh").meta.volatile).toBe(true);
  });
});

describe("autoRoute and autoDefaultModel settings", () => {
  it("default to off", () => {
    const config = Config({});
    expect(autoRouteOf(config)).toEqual(defaultAutoRoute());
    expect(autoRouteOf(config).enabled).toBe(false);
    expect(autoDefaultModelOf(config)).toBe(false);
  });

  it("accepts enabled overrides", () => {
    expect(autoRouteOf(Config({ autoRoute: { enabled: true } })).enabled).toBe(true);
    expect(autoDefaultModelOf(Config({ autoDefaultModel: true }))).toBe(true);
  });

  it("autoRoute is live (volatile)", () => {
    expect(field("autoRoute").meta.volatile).toBe(true);
  });
});
