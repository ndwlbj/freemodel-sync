import type { ClientLocale } from "./i18n.ts";

const FAILED_REGEX = /^failed: ([\s\S]*)$/;
const CAPACITY_RETRY_REGEX = /^no capacity: ([\s\S]*) \((\d+\/\d+) in a row, retried later\)$/;
const CAPACITY_DOWNGRADED_REGEX = /^no capacity (\d+) times in a row: ([\s\S]*) \(downgraded\)$/;
const TEMPORARILY_UNAVAILABLE_REGEX = /^temporarily unavailable(?: (\S+))?: ([\s\S]*) \(retried later\)$/;
const EXPIRED_AGO_REGEX = /^expired (\d+) day\(s\) ago$/;
const EXPIRES_IN_REGEX = /^expires in (\d+) days$/;

/**
 * Localize server-produced reason strings for client presentation.
 * Returns the reason unchanged when locale is "en" or when the reason
 * does not match any known form. Provider error text is preserved verbatim.
 */
export function localizeReason(reason: string, locale: ClientLocale): string {
  if (locale !== "zh") return reason;

  if (reason === "not probed yet") return "尚未探测";
  if (reason === "untested") return "未测试";
  if (reason === "failed") return "失败";

  const failed = FAILED_REGEX.exec(reason);
  if (failed) return `失败：${failed[1]}`;

  const capacityRetry = CAPACITY_RETRY_REGEX.exec(reason);
  if (capacityRetry) return `无可用容量：${capacityRetry[1]}（连续 ${capacityRetry[2]} 次，稍后重试）`;

  const capacityDowngraded = CAPACITY_DOWNGRADED_REGEX.exec(reason);
  if (capacityDowngraded) return `无可用容量，已连续 ${capacityDowngraded[1]} 次：${capacityDowngraded[2]}（已降级）`;

  const tempUnavailable = TEMPORARILY_UNAVAILABLE_REGEX.exec(reason);
  if (tempUnavailable) {
    const code = tempUnavailable[1] ? ` ${tempUnavailable[1]}` : "";
    return `暂时不可用${code}：${tempUnavailable[2]}（稍后重试）`;
  }

  const expiredAgo = EXPIRED_AGO_REGEX.exec(reason);
  if (expiredAgo) return `已过期 ${expiredAgo[1]} 天`;

  const expiresIn = EXPIRES_IN_REGEX.exec(reason);
  if (expiresIn) return `${expiresIn[1]} 天后到期`;

  return reason;
}
