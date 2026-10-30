/**
 * Plugin settings (plan section 6.3): channel switches and key references,
 * which models are listed, the refresh cadence and opt-in tier-2 manual
 * registration. The default-model switch follows in a later step.
 *
 * `apiKeyEnv` fields carry the `credential-ref` role: the settings page stores
 * only the environment-variable NAME here and saves the key itself through
 * dsh's credential service (`ctx.credentials`), so no key ever lands in the
 * plugin configuration. Manual entries are checked one more time by
 * `validateManualConfig`, which rejects secret-bearing keys/values.
 */
import z from "@deepseek-ai/schemastery";
import {
  CHANNEL_LABELS,
  defaultAutoRoute,
  defaultManualProbe,
  defaultProviders,
  defaultRanking,
  defaultRefresh,
  type AutoRouteConfig,
  type BailianChannelConfig,
  type FreemodelConfig,
  type FreemodelConfigInput,
  type GroqChannelConfig,
  type ManualEntryConfig,
  type ManualProbeConfig,
  type OpenRouterChannelConfig,
  type SenseNovaChannelConfig,
} from "./channels.ts";
import { validateManualConfig } from "./manual.ts";
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

const sensenova: z<Partial<SenseNovaChannelConfig>, SenseNovaChannelConfig> = z
  .object({
    enabled: z
      .boolean()
      .default(DEFAULTS.sensenova.enabled)
      .description("List SenseNova Token Plan models. Off by default (public beta)."),
    apiKeyEnv: keyRef("sensenova"),
    tokenPlanConfirmed: z
      .boolean()
      .default(DEFAULTS.sensenova.tokenPlanConfirmed)
      .description(
        "I confirm this key is inside the SenseNova Token Plan public beta. The API has no quota " +
          "endpoint and prices can change, so no SenseNova model is listed or probed until this is " +
          "ticked (same as `plan: token-plan` in freemodel-sync).",
      ),
    models: z
      .array(z.string())
      .default(DEFAULTS.sensenova.models)
      .description(
        "Model allowlist. Empty means every catalogue model whose pricing is the string \"0\"; " +
          "the catalogue is intersected with this list when it can be read.",
      ),
  })
  .description(CHANNEL_LABELS.sensenova);

const bailian: z<Partial<BailianChannelConfig>, BailianChannelConfig> = z
  .object({
    enabled: z
      .boolean()
      .default(DEFAULTS.bailian.enabled)
      .description("List Alibaba Cloud Bailian (DashScope) models. Off by default; Beijing region only."),
    apiKeyEnv: keyRef("bailian"),
    freeQuotaGuardConfirmed: z
      .boolean()
      .default(DEFAULTS.bailian.freeQuotaGuardConfirmed)
      .description(
        "I confirm the console's \"stop when the free quota is used up\" switch is on. Bailian's API " +
          "cannot tell free calls from billed ones, so no model is listed or probed until this is ticked " +
          "(same as `free_quota_guard: confirmed` in freemodel-sync).",
      ),
    models: z
      .array(
        z.object({
          id: z.string().description("Model id exactly as shown in the Bailian console."),
          quotaTokens: z.natural().description("Optional hand-entered one-off token allowance; shown as manual/unverified."),
        }),
      )
      .default(DEFAULTS.bailian.models)
      .description("Allowlist and optional manual allowances. Empty means the channel does nothing."),
  })
  .description(CHANNEL_LABELS.bailian);

const providersSchema = z
  .object({
    openrouter: openrouter.default({}),
    groq: groq.default({}),
    sensenova: sensenova.default({}),
    bailian: bailian.default({}),
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
    capacityDowngradeAfter: z
      .natural()
      .min(1)
      .max(20)
      .default(RANKING.capacityDowngradeAfter)
      .description(
        "Consecutive queue / no-capacity results after which a model is no longer selectable (default from spec/ranking.json).",
      ),
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

const MANUAL_PROBE = defaultManualProbe();

const manualEntrySchema = z
  .object({
    dshProvider: z
      .string()
      .default("")
      .description("dsh provider/route id registered by the platform's own plugin, e.g. dsh-zcode or qoder-global."),
    model: z.string().default("").description("Model id exactly as that dsh route knows it."),
    label: z.string().default("").description("Optional display label; public information only."),
    quotaNote: z
      .string()
      .default("")
      .description("Optional hand-written quota note. Always shown as manual/unverified; never deducted locally."),
    expiresAt: z
      .string()
      .pattern(/^$|^\d{4}-\d{2}-\d{2}$/)
      .default("")
      .description("Optional YYYY-MM-DD after which the entry is expired and is not probed."),
    probe: z
      .boolean()
      .default(false)
      .description(
        "Opt this entry in to the dsh probe. manualProbe.enabled must also be on, and each model is still probed at most once per day.",
      ),
  })
  .description("One tier-2 manual registration (public facts only; no token/PAT/cookie).");

const manualSchema = z
  .array(manualEntrySchema)
  .default([])
  .description("Tier-2 platforms whose login is owned by their own dsh plugin. Never auto-selected; no probe by default.");

const manualProbeSchema = z
  .object({
    enabled: z
      .boolean()
      .default(MANUAL_PROBE.enabled)
      .description(
        "Global switch for manual availability probes. Off by default; when on, only entries with probe=true are probed, at most once per model per day. Account errors stop that platform for the day.",
      ),
  })
  .default({})
  .description("Manual availability probing (through dsh only)")
  .volatile();

const AUTO_ROUTE = defaultAutoRoute();

const autoRouteSchema = z
  .object({
    enabled: z
      .boolean()
      .default(AUTO_ROUTE.enabled)
      .description(
        "Register the freemodel-auto route that always targets the current #1 available free model and fails over in-process to the next by rank on the same request. Off by default.",
      ),
  })
  .default({})
  .description("Automatic best-model route")
  .volatile();

const autoDefaultModelSchema = z
  .boolean()
  .default(false)
  .description(
    "When on, ask dsh to point THIS profile's agent-default-model at freemodel-auto/best (or the current #1 listed model if autoRoute is off). Never touches other profiles, never QQ/bot profiles, never $DSH_HOME/cordis.patch.yml home layer. Off by default.",
  );

const baseConfig = z.object({
  providers: providersSchema,
  ranking: rankingSchema,
  refresh: refreshSchema,
  manual: manualSchema,
  manualProbe: manualProbeSchema,
  autoRoute: autoRouteSchema,
  autoDefaultModel: autoDefaultModelSchema,
});

type BaseConfig = typeof baseConfig;

/**
 * The same form schema, with one extra guard: dsh's schemastery objects keep
 * unknown keys, so a pasted `token`/`pat`/`cookie` or a `sk-...` value would
 * otherwise pass through. `validateManualConfig` rejects those before the
 * normal schema runs; the form fields themselves still come from `baseConfig`.
 */
function guardedConfig(value: unknown, options?: unknown): FreemodelConfig {
  validateManualConfig(value);
  return (baseConfig as unknown as (input: unknown, opts?: unknown) => FreemodelConfig)(value, options);
}

export const Config = Object.assign(guardedConfig, baseConfig) as unknown as z<FreemodelConfigInput, FreemodelConfig>;
Object.setPrototypeOf(Config as unknown as object, Object.getPrototypeOf(baseConfig));
Object.defineProperty(Config, "uid", { value: (baseConfig as unknown as { uid: number }).uid });

