/**
 * Plugin settings (plan section 6.3): channel switches and key references,
 * which models are listed, and the refresh cadence. Manual registration and
 * the default-model switch follow in later steps.
 *
 * `apiKeyEnv` fields carry the `credential-ref` role: the settings page stores
 * only the environment-variable NAME here and saves the key itself through
 * dsh's credential service (`ctx.credentials`), so no key ever lands in the
 * plugin configuration.
 */
import z from "@deepseek-ai/schemastery";
import {
  CHANNEL_LABELS,
  defaultProviders,
  defaultRanking,
  defaultRefresh,
  type FreemodelConfig,
  type FreemodelConfigInput,
  type GroqChannelConfig,
  type OpenRouterChannelConfig,
} from "./channels.ts";
import type { ChannelId } from "./spec.ts";

/** A credential reference: an environment-variable name, never a value. */
const DEFAULTS = defaultProviders();

function keyRef(channel: ChannelId) {
  const env = DEFAULTS[channel].apiKeyEnv;
  return z
    .string()
    .role("credential-ref")
    .pattern(/^[A-Za-z_][A-Za-z0-9_]*$/)
    .default(env)
    .description(
      `Environment variable naming the ${CHANNEL_LABELS[channel]} API key (default ${env}). ` +
        "Only the name is stored here; the key is saved by dsh's credential store.",
    );
}

const openrouter: z<Partial<OpenRouterChannelConfig>, OpenRouterChannelConfig> = z
  .object({
    enabled: z
      .boolean()
      .default(DEFAULTS.openrouter.enabled)
      .description("List OpenRouter's free (:free) models. Takes effect once a key is configured."),
    apiKeyEnv: keyRef("openrouter"),
  })
  .description(CHANNEL_LABELS.openrouter);

const groq: z<Partial<GroqChannelConfig>, GroqChannelConfig> = z
  .object({
    enabled: z.boolean().default(DEFAULTS.groq.enabled).description("List Groq models. Off by default."),
    apiKeyEnv: keyRef("groq"),
    freePlanConfirmed: z
      .boolean()
      .default(DEFAULTS.groq.freePlanConfirmed)
      .description(
        "I confirm this Groq key is on the free plan. Groq's catalogue has no per-model free flag, " +
          "so no Groq model is listed until this is ticked (same as `plan: free` in freemodel-sync).",
      ),
  })
  .description(CHANNEL_LABELS.groq);

const providersSchema = z
  .object({
    openrouter: openrouter.default({}),
    groq: groq.default({}),
  })
  .default({})
  .description("Channels")
  .volatile();

const RANKING = defaultRanking();
const REFRESH = defaultRefresh();

const rankingSchema = z
  .object({
    requireTools: z
      .boolean()
      .default(RANKING.requireTools)
      .description("Hide models whose catalogue says they cannot call tools (dsh's agent needs tools). Groq does not say; its models stay listed."),
    minContext: z.natural().default(RANKING.minContext).description("Hide models with a smaller context window (tokens)."),
  })
  .default({})
  .description("Which models are listed")
  .volatile();

const refreshSchema = z
  .object({
    onStartup: z
      .boolean()
      .default(REFRESH.onStartup)
      .description("At startup, list the cached models at once and refresh in the background."),
    catalogHours: z.number().min(1).max(168).default(REFRESH.catalogHours).description("Read each catalogue every N hours."),
    probeHours: z
      .number()
      .min(1)
      .max(168)
      .default(REFRESH.probeHours)
      .description("Probe models again after N hours (one tiny request per model)."),
    probeTopN: z.natural().min(1).max(20).default(REFRESH.probeTopN).description("Models probed per round and channel."),
    reserveRequests: z
      .natural()
      .default(REFRESH.reserveRequests)
      .description("Free requests per day the probes never touch, kept for your own use."),
    dailyProbeLimit: z
      .natural()
      .default(REFRESH.dailyProbeLimit)
      .description("Daily free-request budget per channel; 0 = what the channel reports (OpenRouter's /key), else 50."),
  })
  .default({})
  .description("Refresh")
  .volatile();

export const Config: z<FreemodelConfigInput, FreemodelConfig> = z.object({
  providers: providersSchema,
  ranking: rankingSchema,
  refresh: refreshSchema,
}) as unknown as z<FreemodelConfigInput, FreemodelConfig>;

