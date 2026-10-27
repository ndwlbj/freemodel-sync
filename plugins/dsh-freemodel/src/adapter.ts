/**
 * The model routes: one `PiAiAdapter` serving `freemodel-openrouter` and
 * `freemodel-groq`, with hand-built pi-ai profiles (dsh-llm-pi-ai's profile
 * resolver is not public; same approach as other dsh model plugins). Each
 * route's models are the service's currently listed models; the key is
 * resolved through dsh's credential store for every request.
 */
import { resolveRetryPolicy } from "@deepseek-ai/dsh-llm";
import { PiAiAdapter } from "@deepseek-ai/dsh-llm-pi-ai";
import { createProvider } from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { CHANNEL_LABELS, routeOf } from "./channels.ts";
import type { RankedModel } from "./rank.ts";
import type { FreemodelService } from "./service.ts";
import { CHANNEL_IDS, type ChannelId, providerSpec } from "./spec.ts";

/** Display suffix telling the picker a model is a free one (the picker shows `name` only). */
export const FREE_BADGE = "免费";
const SEPARATOR = " · ";
const STREAM_IDLE_TIMEOUT_MS = 120_000;
const RETRY_MAX_DELAY_MS = 60_000;
const DEFAULT_MAX_TOKENS = 8192;
const FALLBACK_CONTEXT = 8192;
const REQUEST_IMAGE_BUDGETS = {
  maxRequestImageBytes: 20_971_520,
  requestImagePixelBudget: 4_194_304,
  requestImageMaxBytes: 1_048_576,
};
const NO_COST = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 };

/** pi-ai's own credential lifecycle is unused: keys come from `resolveApiKey`. */
const INERT_AUTH = {
  credentials: {
    async read() {
      return undefined;
    },
    async list() {
      return [];
    },
    async modify(): Promise<never> {
      throw new Error("dsh-freemodel: routes have no pi-ai credential lifecycle");
    },
    async delete() {},
  },
  authContext: {
    async env() {
      return undefined;
    },
    async fileExists() {
      return false;
    },
  },
};

/** Route -> channel, or undefined for a route this plugin does not own. */
export function channelOfRoute(route: string | undefined): ChannelId | undefined {
  return CHANNEL_IDS.find((id) => routeOf(id) === route);
}

export function displayName(id: ChannelId): string {
  return `${CHANNEL_LABELS[id]} Free (dsh-freemodel)`;
}

function maxTokensField(id: ChannelId): "max_tokens" | "max_completion_tokens" {
  return providerSpec(id).probe && (providerSpec(id).probe as { maxTokensParam: string }).maxTokensParam === "max_completion_tokens"
    ? "max_completion_tokens"
    : "max_tokens";
}

/** Picker label: the catalogue name with its own "(free)" replaced by the badge. */
export function pickerName(name: string): string {
  return `${name.replace(/\s*\(free\)\s*$/i, "")}${SEPARATOR}${FREE_BADGE}`;
}

/** One pi-ai model descriptor for a listed model. Text only until P6 adds capabilities. */
export function toPiModel(id: ChannelId, ranked: RankedModel) {
  const model = ranked.model;
  const contextWindow = model.contextLength > 0 ? model.contextLength : FALLBACK_CONTEXT;
  const maxTokens = Math.min(model.maxTokens ?? DEFAULT_MAX_TOKENS, contextWindow);
  return {
    id: model.id,
    name: pickerName(model.name),
    api: "openai-completions" as const,
    provider: routeOf(id),
    baseUrl: providerSpec(id).baseURL,
    input: ["text" as const],
    reasoning: false,
    cost: NO_COST,
    contextWindow,
    maxTokens,
    ...(id === "openrouter" ? { headers: { "X-Title": "dsh-freemodel" } } : {}),
    compat: { maxTokensField: maxTokensField(id) },
  };
}

type Profiles = Map<string, ConstructorParameters<typeof PiAiAdapter>[0] extends { profiles: () => ReadonlyMap<string, infer P> } ? P : never>;

/** Short description for selectors: the probe result behind the listing. */
export function describeListed(ranked: RankedModel): string {
  const ttft = ranked.test?.ttftMs;
  const parts = [`${CHANNEL_LABELS[ranked.model.provider]} free`];
  if (typeof ttft === "number") parts.push(`TTFT ${Math.round(ttft)} ms`);
  if (ranked.model.tools === true) parts.push("tools");
  return parts.join(" · ");
}

export class FreemodelAdapter extends PiAiAdapter {
  constructor(
    private readonly service: FreemodelService,
    options: ConstructorParameters<typeof PiAiAdapter>[0],
  ) {
    super(options);
  }

  override async listModels(provider: string) {
    const id = channelOfRoute(provider);
    const listed = id === undefined ? [] : this.service.listed(id);
    return (await super.listModels(provider)).map((model) => {
      const entry = listed.find((r) => r.model.id === model.id);
      return entry === undefined ? model : { ...model, description: describeListed(entry) };
    });
  }
}

export interface AdapterHandle {
  adapter: FreemodelAdapter;
  /** Rebuild the profiles so the next operation sees the current models. */
  invalidate(): void;
}

/**
 * Build the adapter for every channel route.
 * @param service - source of active channels, listed models and keys.
 * @param resolveAttachments - dsh's attachment store, when present.
 */
export function createAdapter(service: FreemodelService, resolveAttachments?: () => unknown): AdapterHandle {
  const api = openAICompletionsApi();
  const build = (): Profiles => {
    const profiles: Profiles = new Map();
    for (const id of CHANNEL_IDS) {
      if (!service.isActive(id)) continue;
      const route = routeOf(id);
      const name = displayName(id);
      const buildModels = () => service.listed(id).map((r) => toPiModel(id, r));
      const piProvider = {
        ...createProvider({
          id: route,
          name,
          auth: {
            apiKey: {
              name: `${CHANNEL_LABELS[id]} API key`,
              async resolve({ credential }: { credential?: { key?: string } }) {
                const apiKey = credential?.key;
                return apiKey === undefined || apiKey.length === 0 ? undefined : { auth: { apiKey }, source: name };
              },
            },
          },
          models: buildModels(),
          api,
        } as never),
        getModels: () => buildModels(),
      };
      profiles.set(route, {
        provider: route,
        displayName: name,
        streamIdleTimeoutMs: STREAM_IDLE_TIMEOUT_MS,
        retryPolicy: resolveRetryPolicy({ mode: "normal", backoff: { maxDelayMs: RETRY_MAX_DELAY_MS } }, `dsh-freemodel:${route} retryPolicy`),
        configuredMaxTokens: new Map(),
        modelErrors: new Map(),
        ...REQUEST_IMAGE_BUDGETS,
        piProvider,
      } as never);
    }
    return profiles;
  };
  let profiles = build();
  const options = {
    profiles: () => profiles,
    auth: INERT_AUTH,
    resolveApiKey: async (provider: string) => {
      const id = channelOfRoute(provider);
      return id === undefined || !service.isActive(id) ? undefined : service.resolveKey(id);
    },
    ...(resolveAttachments === undefined ? {} : { resolveAttachments }),
  } as unknown as ConstructorParameters<typeof PiAiAdapter>[0];
  return {
    adapter: new FreemodelAdapter(service, options),
    invalidate: () => {
      profiles = build();
    },
  };
}
