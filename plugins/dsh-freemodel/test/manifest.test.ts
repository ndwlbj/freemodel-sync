import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { satisfies } from "../src/semver.ts";

const root = new URL("../", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("package.json", root), "utf8"));

/** The dsh runtime this plugin is verified on (docs/dsh-plugin-verification.md). */
const VERIFIED_DSH = "0.2.1-rc.3";

describe("package.json", () => {
  it("declares a dsh range that covers the verified runtime and stops before 0.3", () => {
    // dsh decides by engines.dsh alone when present, and silently skips a bundle outside it.
    expect(satisfies(VERIFIED_DSH, manifest.engines.dsh)).toBe(true);
    expect(satisfies("0.3.0-rc.1", manifest.engines.dsh)).toBe(false);
  });

  it("peers on the host packages it uses, in ranges that cover the runtime", () => {
    for (const [name, range] of Object.entries<string>(manifest.peerDependencies)) {
      expect(name.startsWith("@deepseek-ai/")).toBe(true);
      if (/^@deepseek-ai\/dsh(-|$)/.test(name)) expect(satisfies(VERIFIED_DSH, range), name).toBe(true);
    }
    expect(manifest.dependencies ?? {}).toEqual({});
  });

  it("is a dsh bundle with an ESM entry, a bin and locale files", () => {
    expect(manifest.name).toBe("dsh-freemodel");
    expect(manifest.type).toBe("module");
    expect(manifest.dsh.bundle.patch).toBe("./cordis.patch.yml");
    expect(manifest.exports["."].default).toBe("./lib/index.js");
    expect(manifest.exports["./locale/*.json"]).toBe("./locale/*.json");
    expect(manifest.bin["dsh-freemodel"]).toBe("lib/bin.js");
    expect(manifest.files).toEqual(expect.arrayContaining(["lib", "locale", "cordis.patch.yml"]));
  });

  it("cannot be published by accident", () => {
    expect(manifest.private).toBe(true);
  });
});

describe("cordis.patch.yml", () => {
  const patch = readFileSync(new URL("cordis.patch.yml", root), "utf8");
  it("only inserts the plugin entry", () => {
    const body = patch
      .split(/\r?\n/)
      .filter((l) => l.trim() !== "" && !l.trimStart().startsWith("#"))
      .join("\n");
    expect(body).toBe("- insert:\n    - id: dsh-freemodel\n      name: dsh-freemodel");
  });
});

describe("locale", () => {
  for (const lang of ["en", "zh"]) {
    it(`${lang}.json has a title and description`, () => {
      const locale = JSON.parse(readFileSync(new URL(`locale/${lang}.json`, root), "utf8"));
      expect(Object.keys(locale)).toEqual(["meta"]);
      expect(locale.meta.title.length).toBeGreaterThan(0);
      expect(locale.meta.description.length).toBeGreaterThan(0);
    });
  }
});

describe("CLI independence", () => {
  it("the bin's modules import no host package, so `dsh plugin exec` works without the host", () => {
    for (const file of ["bin.ts", "status.ts", "channels.ts", "spec.ts", "semver.ts", "version.ts"]) {
      const source = readFileSync(new URL(`src/${file}`, root), "utf8");
      expect(source, file).not.toMatch(/from\s+["']@deepseek-ai\//);
      expect(source, file).not.toMatch(/from\s+["']\.\/(config|index)\.ts["']/);
    }
  });
});
