/**
 * Channel settings without the schema library, so the `dsh-freemodel` CLI can
 * run where only the plugin package is installed (`dsh plugin exec`), with no
 * host packages beside it. The schemastery `Config` is in config.ts.
 */
import { type ChannelId, CHANNEL_IDS, providerSpec } from "./spec.ts";

/** Short channel names for settings text. */
export const CHANNEL_LABELS: Record<ChannelId, string> = { openrouter: "OpenRouter", groq: "Groq" };

export interface OpenRouterChannelConfig {
  enabled: boolean;
  apiKeyEnv: string;
}

export interface GroqChannelConfig {
  enabled: boolean;
  apiKeyEnv: string;
  freePlanConfirmed: boolean;
}

export interface ProvidersConfig {
  openrouter: OpenRouterChannelConfig;
  groq: GroqChannelConfig;
}

/**
 * A live settings value. dsh's settings page only shows (and edits in place)
 * fields declared `.volatile()`; the plugin reads them through `get()` at each
 * use, so an edit takes effect without a restart.
 */
export interface Live<T> {
  get(): T;
}

export interface FreemodelConfig {
  providers: Live<ProvidersConfig> | ProvidersConfig;
}

/** What a user (or a patch file) may write: every field optional. */
export interface FreemodelConfigInput {
  providers?: {
    openrouter?: Partial<OpenRouterChannelConfig>;
    groq?: Partial<GroqChannelConfig>;
  };
}

/** The settings every field defaults to (key variable names come from spec/providers.json). */
export function defaultProviders(): ProvidersConfig {
  return {
    openrouter: { enabled: true, apiKeyEnv: providerSpec("openrouter").apiKeyEnv },
    groq: { enabled: false, apiKeyEnv: providerSpec("groq").apiKeyEnv, freePlanConfirmed: false },
  };
}

function isLive<T>(value: Live<T> | T): value is Live<T> {
  return typeof (value as Partial<Live<T>>).get === "function";
}

/**
 * Current channel settings, unwrapping the live value.
 * @param config - validated settings (output of `Config`).
 */
export function providersOf(config: FreemodelConfig): ProvidersConfig {
  return isLive(config.providers) ? config.providers.get() : config.providers;
}

/** One channel's effective state, for logs, status and doctor. Never holds a key. */
export interface ChannelState {
  id: ChannelId;
  /** The model route the channel will register (P4). */
  route: string;
  enabled: boolean;
  apiKeyEnv: string;
  /** Why an enabled channel will still list nothing, if it will not. */
  blocked?: string;
}

/** Route id for a channel; prefixed so it never collides with a hand-written `fms-*` or official route. */
export function routeOf(id: ChannelId): string {
  return `freemodel-${id}`;
}

/**
 * Effective per-channel state of a validated configuration.
 * @param config - validated settings (output of `Config`).
 * @returns one entry per known channel, in display order.
 */
export function channelStates(config: FreemodelConfig): ChannelState[] {
  const providers = providersOf(config);
  return CHANNEL_IDS.map((id) => {
    const channel = providers[id];
    const state: ChannelState = { id, route: routeOf(id), enabled: channel.enabled, apiKeyEnv: channel.apiKeyEnv };
    if (id === "groq" && channel.enabled && !providers.groq.freePlanConfirmed) {
      state.blocked = "freePlanConfirmed is off";
    }
    return state;
  });
}
