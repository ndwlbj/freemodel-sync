/**
 * Plugin settings (plan section 6.3). P3 ships only the channel switches and
 * the key references; ranking, refresh and manual registration follow in
 * later steps.
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

export const Config: z<FreemodelConfigInput, FreemodelConfig> = z.object({
  providers: providersSchema,
}) as unknown as z<FreemodelConfigInput, FreemodelConfig>;

