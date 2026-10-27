import { describe, expect, it } from "vitest";
import { channelStates, defaultProviders, providersOf, routeOf } from "../src/channels.ts";
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
    for (const channel of ["openrouter", "groq"]) {
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
    expect(names.filter((n) => /token|secret|password|cookie|^key$|^apiKey$/i.test(n))).toEqual([]);
  });
});

describe("channelStates", () => {
  it("lists every channel with its route", () => {
    expect(channelStates(Config({}))).toEqual([
      { id: "openrouter", route: "freemodel-openrouter", enabled: true, apiKeyEnv: "OPENROUTER_API_KEY" },
      { id: "groq", route: "freemodel-groq", enabled: false, apiKeyEnv: "GROQ_API_KEY" },
    ]);
    expect(routeOf("groq")).toBe("freemodel-groq");
  });

  it("flags an enabled Groq channel without the free-plan confirmation", () => {
    const groq = channelStates(Config({ providers: { groq: { enabled: true } } }))[1];
    expect(groq?.blocked).toBe("freePlanConfirmed is off");
    const confirmed = channelStates(Config({ providers: { groq: { enabled: true, freePlanConfirmed: true } } }))[1];
    expect(confirmed?.blocked).toBeUndefined();
  });
});
