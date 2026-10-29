/**
 * SenseNova Token Plan channel (https://token.sensenova.cn/v1, OpenAI-compatible).
 *
 * The public beta has no quota API and prices can change, so the caller lists
 * nothing until `tokenPlanConfirmed` is ticked (same as Python's
 * `plan: token-plan`). The catalogue is intersected with an optional allowlist;
 * only models whose `pricing` is the literal string "0" are free. Port of
 * `freemodel_sync.providers.sensenova`.
 */
import { providerSpec } from "../spec.ts";
import { asInt, isRecord } from "../util.ts";
import { OpenAICompatChannel, type FetchLike } from "./openai-compat.ts";
import { describeError } from "./openrouter.ts";
import { type Capabilities, type CatalogModel, ChannelError } from "./types.ts";

export interface SenseNovaLogger {
  warn(message: string, ...args: unknown[]): void;
}

const SPEC = providerSpec("sensenova");
const VISION_WORDS = ["image", "vision", "multimodal", "multi-modal", "图像", "视觉"];
const TOOLS_WORDS = ["function", "tool", "工具"];
const REASONING_WORDS = ["reasoning", "think", "推理"];

/** Only the literal string "0" is the free marker (a numeric 0 is not). */
export function pricingIsZero(value: unknown): boolean {
  return typeof value === "string" && value.trim() === "0";
}

function featureText(value: unknown): string {
  if (typeof value === "string") return value.toLowerCase();
  try {
    return JSON.stringify(value).toLowerCase();
  } catch {
    return String(value).toLowerCase();
  }
}

function includesAny(text: string, words: readonly string[]): boolean {
  return words.some((word) => text.includes(word));
}

/** Infer flags from `supported_features` / `businesses`; absence stays unknown, never false. */
export function senseNovaCapabilities(raw: unknown): Capabilities {
  if (!isRecord(raw)) return { tools: null, vision: null, reasoning: null, source: "unknown" };
  const text = `${featureText(raw.supported_features)} ${featureText(raw.businesses)}`;
  const tools = includesAny(text, TOOLS_WORDS) || null;
  const vision = includesAny(text, VISION_WORDS) || null;
  const reasoning = includesAny(text, REASONING_WORDS) || null;
  const known = tools !== null || vision !== null || reasoning !== null;
  return { tools, vision, reasoning, source: known ? "catalog" : "unknown" };
}

function modelOf(raw: Record<string, unknown>, fallbackId: string): CatalogModel {
  const id = typeof raw.id === "string" && raw.id !== "" ? raw.id : fallbackId;
  const capabilities = senseNovaCapabilities(raw);
  return {
    provider: "sensenova",
    id,
    name: typeof raw.name === "string" && raw.name !== "" ? raw.name : id,
    contextLength: asInt(raw.context_length) ?? asInt(raw.context_window) ?? 0,
    tools: capabilities.tools,
    input: capabilities.vision === true ? ["text", "image"] : ["text"],
    maxTokens: asInt(raw.max_tokens) ?? asInt(raw.max_completion_tokens),
    expirationDate: null,
    capabilities,
    quota: null,
    tier: 1,
  };
}

export class SenseNovaChannel extends OpenAICompatChannel {
  readonly id = "sensenova" as const;

  constructor(
    fetchImpl?: FetchLike,
    private readonly logger?: SenseNovaLogger,
  ) {
    super(fetchImpl);
  }

  private fallback(allowlist: readonly string[] | undefined, reason: string): CatalogModel[] {
    if (allowlist === undefined || allowlist.length === 0) {
      throw new ChannelError(`SenseNova model list failed: ${reason}`);
    }
    this.logger?.warn(
      `dsh-freemodel: SenseNova model list failed (${reason}); using the configured model allowlist`,
    );
    return allowlist.map((id) => modelOf({}, id));
  }

  /**
   * Read the catalogue, keep the intersection with `allowlist` and drop models
   * whose `pricing` is not "0". Without an allowlist, every zero-priced
   * catalogue model is used.
   */
  async discover(
    apiKey: string | undefined,
    signal?: AbortSignal,
    allowlist?: readonly string[],
  ): Promise<CatalogModel[]> {
    if (!apiKey) {
      throw new ChannelError(`sensenova: listing models needs ${SPEC.apiKeyEnv} (the model list requires a key)`);
    }
    let payload: unknown;
    try {
      payload = await this.getJson(SPEC.modelsPath, this.authHeaders(apiKey), signal);
    } catch (error) {
      return this.fallback(allowlist, describeError(error));
    }
    if (!isRecord(payload) || !Array.isArray(payload.data)) {
      return this.fallback(allowlist, "unexpected models payload");
    }

    const catalog = new Map<string, Record<string, unknown>>();
    for (const raw of payload.data) {
      if (!isRecord(raw)) continue;
      const id = raw.id;
      if (typeof id === "string" && id !== "") catalog.set(id, raw);
    }

    const configured = allowlist !== undefined && allowlist.length > 0 ? allowlist : null;
    const ids = configured ?? [...catalog.keys()];
    const models: CatalogModel[] = [];
    for (const id of ids) {
      const raw = catalog.get(id);
      if (raw === undefined) continue;
      if (!pricingIsZero(raw.pricing)) {
        this.logger?.warn(
          `dsh-freemodel: skipping SenseNova model ${id}: pricing is ${JSON.stringify(raw.pricing)}, not the string "0" (it is no longer free)`,
        );
        continue;
      }
      models.push(modelOf(raw, id));
    }
    return models;
  }
}
