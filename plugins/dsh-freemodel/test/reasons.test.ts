import { describe, expect, it } from "vitest";
import { localizeReason } from "../src/client/reasons.ts";

describe("localizeReason", () => {
  describe("zh locale mappings", () => {
    it("maps 'not probed yet' to '尚未探测'", () => {
      expect(localizeReason("not probed yet", "zh")).toBe("尚未探测");
    });

    it("maps 'untested' to '未测试'", () => {
      expect(localizeReason("untested", "zh")).toBe("未测试");
    });

    it("maps 'failed' to '失败'", () => {
      expect(localizeReason("failed", "zh")).toBe("失败");
    });

    it("maps 'failed: <error text>' to '失败：<原文错误>'", () => {
      expect(localizeReason("failed: connection timed out", "zh")).toBe("失败：connection timed out");
    });

    it("maps 'no capacity: <error> (<n>/<m> in a row, retried later)'", () => {
      expect(
        localizeReason("no capacity: server busy (2/3 in a row, retried later)", "zh"),
      ).toBe("无可用容量：server busy（连续 2/3 次，稍后重试）");
    });

    it("maps 'no capacity <n> times in a row: <error> (downgraded)'", () => {
      expect(
        localizeReason("no capacity 3 times in a row: rate limited (downgraded)", "zh"),
      ).toBe("无可用容量，已连续 3 次：rate limited（已降级）");
    });

    it("maps 'temporarily unavailable: <error> (retried later)' without statusCode", () => {
      expect(
        localizeReason("temporarily unavailable: gateway timeout (retried later)", "zh"),
      ).toBe("暂时不可用：gateway timeout（稍后重试）");
    });

    it("maps 'temporarily unavailable <statusCode>: <error> (retried later)' with statusCode", () => {
      expect(
        localizeReason("temporarily unavailable 429: rate limited (retried later)", "zh"),
      ).toBe("暂时不可用 429：rate limited（稍后重试）");
      expect(
        localizeReason("temporarily unavailable 503: backend unavailable (retried later)", "zh"),
      ).toBe("暂时不可用 503：backend unavailable（稍后重试）");
    });

    it("maps 'expired <n> day(s) ago' to '已过期 n 天'", () => {
      expect(localizeReason("expired 1 day(s) ago", "zh")).toBe("已过期 1 天");
      expect(localizeReason("expired 5 day(s) ago", "zh")).toBe("已过期 5 天");
    });

    it("maps 'expires in <n> days' to 'n 天后到期'", () => {
      expect(localizeReason("expires in 0 days", "zh")).toBe("0 天后到期");
      expect(localizeReason("expires in 7 days", "zh")).toBe("7 天后到期");
    });
  });

  describe("fallbacks and edge cases", () => {
    it("falls back to the original string for unknown reasons", () => {
      expect(localizeReason("unknown custom reason", "zh")).toBe("unknown custom reason");
      expect(localizeReason("model quota exceeded", "zh")).toBe("model quota exceeded");
    });

    it("handles empty string gracefully", () => {
      expect(localizeReason("", "zh")).toBe("");
      expect(localizeReason("", "en")).toBe("");
    });

    it("preserves error text with colons verbatim", () => {
      expect(
        localizeReason("failed: HTTP 500: internal error: host unreachable", "zh"),
      ).toBe("失败：HTTP 500: internal error: host unreachable");

      expect(
        localizeReason("no capacity: 429: rate: limit: tokens (2/3 in a row, retried later)", "zh"),
      ).toBe("无可用容量：429: rate: limit: tokens（连续 2/3 次，稍后重试）");

      expect(
        localizeReason("no capacity 3 times in a row: 429: rate: limit: tokens (downgraded)", "zh"),
      ).toBe("无可用容量，已连续 3 次：429: rate: limit: tokens（已降级）");

      expect(
        localizeReason("temporarily unavailable: 503: service: unavailable (retried later)", "zh"),
      ).toBe("暂时不可用：503: service: unavailable（稍后重试）");

      expect(
        localizeReason("temporarily unavailable 503: http: 503: service: unavailable (retried later)", "zh"),
      ).toBe("暂时不可用 503：http: 503: service: unavailable（稍后重试）");
    });
  });

  describe("en locale", () => {
    const samples = [
      "not probed yet",
      "untested",
      "failed",
      "failed: connection timed out",
      "failed: HTTP 500: internal error",
      "no capacity: server busy (2/3 in a row, retried later)",
      "no capacity: 429: limit (1/3 in a row, retried later)",
      "no capacity 3 times in a row: rate limited (downgraded)",
      "no capacity 5 times in a row: 429: limit (downgraded)",
      "temporarily unavailable: gateway timeout (retried later)",
      "temporarily unavailable 429: rate limited (retried later)",
      "temporarily unavailable 503: http: 503: error (retried later)",
      "expired 1 day(s) ago",
      "expired 5 day(s) ago",
      "expires in 0 days",
      "expires in 7 days",
      "unknown custom reason",
      "",
    ];

    for (const sample of samples) {
      it(`returns input unchanged for "${sample}"`, () => {
        expect(localizeReason(sample, "en")).toBe(sample);
      });
    }
  });
});
