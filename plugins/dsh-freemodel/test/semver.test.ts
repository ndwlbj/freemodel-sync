import { describe, expect, it } from "vitest";
import { compareVersions, satisfies } from "../src/semver.ts";

describe("compareVersions", () => {
  it.each([
    ["0.2.1-rc.3", "0.2.1-rc.1", 1],
    ["0.2.1-rc.10", "0.2.1-rc.9", 1],
    ["0.2.1", "0.2.1-rc.9", 1],
    ["0.2.1-alpha.5", "0.2.1-rc.1", -1],
    ["0.2.1-rc.1", "0.2.1-1", 1],
    ["0.2.1-rc", "0.2.1-rc.1", -1],
    ["v22.19.0", "22.19.0", 0],
    ["1.0.0", "0.9.9", 1],
  ])("%s vs %s", (a, b, sign) => {
    expect(Math.sign(compareVersions(a, b) as number)).toBe(sign);
  });

  it("returns undefined for non-versions", () => {
    expect(compareVersions("latest", "1.0.0")).toBeUndefined();
  });
});

describe("satisfies", () => {
  const dsh = ">=0.2.1-rc.1 <0.3.0-0";
  it.each([
    ["0.2.1-rc.1", true],
    ["0.2.1-rc.3", true],
    ["0.2.1-rc.4", true],
    ["0.2.1", true],
    ["0.2.9", true],
    ["0.2.1-alpha.5", false],
    ["0.3.0-rc.1", false],
    ["0.3.0", false],
    ["0.1.7", false],
  ])("dsh %s -> %s", (version, ok) => {
    expect(satisfies(version, dsh)).toBe(ok);
  });

  const node = "^22.19.0 || >=24.0.0";
  it.each([
    ["22.19.0", true],
    ["22.23.4", true],
    ["23.1.0", false],
    ["24.0.0", true],
    ["26.1.0", true],
    ["20.19.0", false],
    ["22.18.9", false],
  ])("node %s -> %s", (version, ok) => {
    expect(satisfies(version, node)).toBe(ok);
  });

  it("handles ^0.x, exact, <= and > comparators and junk", () => {
    expect(satisfies("0.2.5", "^0.2.1")).toBe(true);
    expect(satisfies("0.3.0", "^0.2.1")).toBe(false);
    expect(satisfies("1.2.3", "1.2.3")).toBe(true);
    expect(satisfies("1.2.3", "=1.2.4")).toBe(false);
    expect(satisfies("1.2.3", "<=1.2.3")).toBe(true);
    expect(satisfies("1.2.3", ">1.2.3")).toBe(false);
    expect(satisfies("1.2.3", "")).toBe(false);
    expect(satisfies("1.2.3", ">=nope")).toBe(false);
  });
});
