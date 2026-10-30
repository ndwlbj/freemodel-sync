/**
 * Short picker badges for the settings card's model tab.
 * Formats capability and quota badges through the card's Translator.
 */
import { compactAmount } from "../badges.ts";
import type { Translator } from "./i18n.ts";
import type { ListedCapabilities, ListedQuota } from "./types.ts";

export { compactAmount };

/** Capability badges; explicit unknown when the catalogue reports none. */
export function capabilityBadges(
  t: Translator,
  capabilities: Pick<ListedCapabilities, "tools" | "vision" | "reasoning"> | null | undefined,
): string[] {
  if (capabilities === null || capabilities === undefined) return [t("badgeCapabilitiesUnknown")];
  const badges: string[] = [];
  if (capabilities.tools === true) badges.push(t("badgeTools"));
  if (capabilities.vision === true) badges.push(t("badgeVision"));
  if (capabilities.reasoning === true) badges.push(t("badgeReasoning"));
  if (
    badges.length === 0 &&
    capabilities.tools === null &&
    capabilities.vision === null &&
    capabilities.reasoning === null
  ) {
    badges.push(t("badgeCapabilitiesUnknown"));
  }
  return badges;
}

/** Quota window label; null when unknown or invalid. */
export function quotaWindowLabel(t: Translator, period: string | null | undefined): string | null {
  if (period === null || period === undefined) return null;
  const normalized = period.toLowerCase().replace(/_/g, "-");
  switch (normalized) {
    case "rolling-5h":
    case "5h":
    case "5-hour":
    case "five-hour":
      return t("quotaWindowRolling5h");
    case "day":
    case "daily":
    case "per-day":
      return t("quotaWindowDay");
    case "minute":
    case "per-minute":
      return t("quotaWindowMinute");
    case "week":
    case "weekly":
    case "per-week":
      return t("quotaWindowWeek");
    case "month":
    case "monthly":
    case "per-month":
      return t("quotaWindowMonth");
    case "total":
      return t("quotaWindowTotal");
    case "beta":
    case "public-beta":
      return t("quotaWindowBeta");
    case "unknown":
      return null;
    default:
      return null;
  }
}

/** Formatted quota window label, falling back to unknown. */
export function formatQuotaWindow(t: Translator, period: string | null | undefined): string {
  return quotaWindowLabel(t, period) ?? t("quotaWindowUnknown");
}

/** Quota unit label; empty string when unknown or unrecognised. */
export function quotaUnitLabel(t: Translator, unit: string | null | undefined): string {
  if (unit === null || unit === undefined) return "";
  const normalized = unit.toLowerCase();
  switch (normalized) {
    case "requests":
      return t("quotaUnitRequests");
    case "tokens":
      return t("quotaUnitTokens");
    case "credits":
      return t("quotaUnitCredits");
    case "unknown":
    default:
      return "";
  }
}

/** Formatted quota unit label, falling back to unknown. */
export function formatQuotaUnit(t: Translator, unit: string | null | undefined): string {
  const label = quotaUnitLabel(t, unit);
  return label !== "" ? label : t("quotaUnitUnknown");
}

/** One quota badge; unknown when no usable number or period is reported. */
export function quotaBadge(t: Translator, quota: ListedQuota | null | undefined): string {
  if (quota === null || quota === undefined) return t("badgeQuotaUnknown");
  const period = (quota.period ?? "").toLowerCase();
  const window = quotaWindowLabel(t, period);
  if (period === "beta" || period === "public_beta" || period === "public-beta") {
    return t("quotaWindowBeta");
  }
  const unit = quotaUnitLabel(t, quota.unit);
  const amount = quota.remaining ?? quota.limit ?? null;
  const manual = quota.source === "manual" ? ` · ${t("badgeQuotaManual")}` : "";
  if (period === "unknown" || amount === null || window === null) {
    const base =
      quota.expiresAt == null || quota.expiresAt === ""
        ? t("badgeQuotaUnknown")
        : `${t("badgeQuotaUnknown")} · ${t("quotaUntil", { date: quota.expiresAt.slice(0, 10) })}`;
    return `${base}${manual}`;
  }
  const value = `${compactAmount(amount)}${unit === "" ? "" : ` ${unit}`}`;
  const prefix = quota.remaining !== null && quota.remaining !== undefined ? t("quotaRemaining", { value }) : value;
  const resets =
    quota.resetsAt == null || quota.resetsAt === ""
      ? ""
      : ` · ${t("quotaResets", { when: quota.resetsAt })}`;
  const expires =
    quota.expiresAt == null || quota.expiresAt === ""
      ? ""
      : ` · ${t("quotaUntil", { date: quota.expiresAt.slice(0, 10) })}`;
  return `${prefix} · ${window}${manual}${resets}${expires}`;
}

/** Capability badges followed by the quota badge. */
export function modelBadges(
  t: Translator,
  model: { capabilities?: ListedCapabilities | null; quota?: ListedQuota | null },
): string[] {
  return [...capabilityBadges(t, model.capabilities), quotaBadge(t, model.quota)];
}
