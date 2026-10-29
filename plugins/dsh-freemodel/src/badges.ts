/**
 * Short picker badges for a free model's capabilities and quota. The values
 * come from the catalogue (or a model-level quota) and never contain a key.
 * Missing/unknown data is shown explicitly as unknown, not as zero or false.
 */
import type { Capabilities, CatalogModel, QuotaPeriod, QuotaUnit } from "./providers/types.ts";

const SEPARATOR = " · ";

const WINDOW_LABELS: Record<QuotaPeriod, string | null> = {
  rolling_5h: "5小时",
  week: "每周",
  day: "每日",
  total: "总额",
  beta: "公测期",
  unknown: null,
};

const UNIT_LABELS: Record<QuotaUnit, string> = {
  requests: "次",
  tokens: "tokens",
  credits: "积分",
  unknown: "",
};

/** Compact a token/request count for a badge: `120000` -> `120k`, `1000000` -> `1M`. */
export function compactAmount(value: number): string {
  const abs = Math.abs(value);
  const scaled = (n: number): string => {
    const text = n.toFixed(n >= 100 ? 0 : n >= 10 ? 1 : 2);
    return text.replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1");
  };
  if (abs >= 1_000_000_000) return `${scaled(value / 1_000_000_000)}B`;
  if (abs >= 1_000_000) return `${scaled(value / 1_000_000)}M`;
  if (abs >= 1_000) return `${scaled(value / 1_000)}k`;
  return scaled(value);
}

/** Capability badges; `能力未知` when the catalogue says nothing about all three flags. */
export function capabilityBadges(
  capabilities: Pick<Capabilities, "tools" | "vision" | "reasoning"> | null | undefined,
): string[] {
  if (capabilities === null || capabilities === undefined) return ["能力未知"];
  const badges: string[] = [];
  if (capabilities.tools === true) badges.push("工具");
  if (capabilities.vision === true) badges.push("视觉");
  if (capabilities.reasoning === true) badges.push("推理");
  if (badges.length === 0 && capabilities.tools === null && capabilities.vision === null && capabilities.reasoning === null) {
    badges.push("能力未知");
  }
  return badges;
}

/** The shape `quotaBadge` needs; the status wire type may use plain strings. */
export interface QuotaLike {
  unit: string;
  period: string;
  limit: number | null;
  used: number | null;
  remaining: number | null;
  resetsAt: string | null;
  expiresAt: string | null;
  source: string;
}

/** One quota badge; `额度未知` when no usable number/period is reported. */
export function quotaBadge(quota: QuotaLike | null | undefined): string {
  if (quota === null || quota === undefined) return "额度未知";
  const period = quota.period as QuotaPeriod;
  const window = WINDOW_LABELS[period] ?? null;
  if (period === "beta") return "公测期";
  const unit = UNIT_LABELS[quota.unit as QuotaUnit] ?? "";
  const amount = quota.remaining ?? quota.limit;
  const manual = quota.source === "manual" ? " · 手动，未核实" : "";
  if (period === "unknown" || amount === null || window === null) {
    const base = quota.expiresAt === null ? "额度未知" : `额度未知 · 至 ${quota.expiresAt.slice(0, 10)}`;
    return `${base}${manual}`;
  }
  const value = `${compactAmount(amount)}${unit === "" ? "" : ` ${unit}`}`;
  const prefix = quota.remaining !== null ? `余 ${value}` : value;
  const resets = quota.resetsAt === null ? "" : ` · 重置 ${quota.resetsAt}`;
  const expires = quota.expiresAt === null ? "" : ` · 至 ${quota.expiresAt.slice(0, 10)}`;
  return `${prefix} · ${window}${manual}${resets}${expires}`;
}

/** Capability badges followed by the quota badge. */
export function modelBadges(model: Pick<CatalogModel, "capabilities" | "quota">): string[] {
  return [...capabilityBadges(model.capabilities), quotaBadge(model.quota)];
}

/** Join badges for a label or description. */
export function joinBadges(badges: readonly string[]): string {
  return badges.join(SEPARATOR);
}