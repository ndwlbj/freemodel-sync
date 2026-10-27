import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CHANNEL_IDS, checkSpecVersion, providerSpec, providersSpec, rankingSpec, SpecError } from "../src/spec.ts";

const specDir = fileURLToPath(new URL("../../../spec/", import.meta.url));
const read = (name: string): unknown => JSON.parse(readFileSync(`${specDir}${name}`, "utf8"));

describe("bundled spec", () => {
  it("is the repository's spec/ files, unchanged", () => {
    expect(providersSpec).toEqual(read("providers.json"));
    expect(rankingSpec).toEqual(read("ranking.json"));
  });

  it("has an entry for every channel the plugin knows", () => {
    for (const id of CHANNEL_IDS) {
      expect(providerSpec(id).baseURL).toMatch(/^https:\/\//);
      expect(providerSpec(id).apiKeyEnv).toMatch(/^[A-Z][A-Z0-9_]*$/);
    }
  });

  it("carries only public channels", () => {
    // SenseNova and Bailian join in P7/P8 with their own confirmations.
    expect(Object.keys(providersSpec.providers).sort()).toEqual([...CHANNEL_IDS].sort());
  });

  it("rejects an unknown spec_version", () => {
    expect(() => checkSpecVersion({ spec_version: 2 }, "providers.json")).toThrow(SpecError);
    expect(() => checkSpecVersion({ spec_version: 2 }, "providers.json")).toThrow(/spec_version 2/);
  });

  it("reports a missing channel entry", () => {
    expect(() => providerSpec("nope" as never)).toThrow(/no entry for nope/);
  });
});
