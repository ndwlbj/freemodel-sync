/**
 * dsh-freemodel: free models for DeepSeek Harness.
 *
 * P3 skeleton: the plugin mounts, exposes its settings (channel switches and
 * credential references) and reports what it would do. It registers no model
 * route yet and never changes the profile's default model; routes for
 * `freemodel-openrouter` / `freemodel-groq` arrive in P4.
 */
import type { Context } from "@deepseek-ai/cordis";
import type { FreemodelConfig } from "./channels.ts";
import { buildStatus, type DescribeKey } from "./status.ts";
import { PLUGIN_VERSION } from "./version.ts";

export { channelStates, defaultProviders, providersOf, routeOf } from "./channels.ts";
export type { ChannelState, FreemodelConfig, FreemodelConfigInput, Live, ProvidersConfig } from "./channels.ts";
export { Config } from "./config.ts";
export { buildStatus, runDoctor, statePath } from "./status.ts";
export type { DoctorReport, StatusReport } from "./status.ts";
export { PLUGIN_VERSION } from "./version.ts";

/** Stable Cordis plugin name. */
export const name = "dsh-freemodel";

/** The model registry must exist before the plugin mounts (routes are registered from P4 on). */
export const inject = ["llm"];

interface CredentialService {
  describe(ref: string): Promise<{ configured: boolean; source?: string; writable: boolean }>;
}

/**
 * Plugin entry point.
 * @param ctx - plugin context.
 * @param config - validated settings.
 */
export function apply(ctx: Context, config: FreemodelConfig): void {
  const credentials = ctx.get("credentials") as CredentialService | undefined;
  const describe: DescribeKey | undefined = credentials === undefined ? undefined : (ref) => credentials.describe(ref);
  void buildStatus(config, describe).then(
    (status) => {
      const summary = status.channels
        .map((c) => {
          const key = c.key === "unknown" ? "key unknown" : c.key.configured ? "key configured" : "no key";
          return `${c.id}=${c.enabled ? "on" : "off"} (${key}${c.blocked === undefined ? "" : `, ${c.blocked}`})`;
        })
        .join(", ");
      ctx.logger.info(`dsh-freemodel ${PLUGIN_VERSION} mounted; ${summary}; no routes registered (skeleton)`);
    },
    (error: unknown) => {
      ctx.logger.warn("dsh-freemodel: status check failed", error);
    },
  );
}
