/**
 * Automatic best-model route (freemodel-auto / best, plan 6.3 / Q5).
 *
 * Always targets the current #1 ranked model across all active probe-ok channels.
 * When a request encounters a terminal failure before yielding any visible output,
 * it fails over in-process to the next candidate by rank.
 *
 * Mid-stream failures after any visible text-delta has already been yielded to the
 * caller are terminal and NEVER fail over mid-stream to avoid garbled output.
 */
import {
  LlmAdapter,
  type GenerateOptions,
  type LlmModelInfo,
  type LlmProviderInfo,
  type LlmResolvedModelInfo,
  type PreparedAdapterCall,
  type StreamChunk,
} from "@deepseek-ai/dsh-llm";
import { FREE_BADGE } from "./adapter.ts";
import { CHANNEL_LABELS, routeOf } from "./channels.ts";
import type { RankedModel } from "./rank.ts";
import type { FreemodelService } from "./service.ts";
import { CHANNEL_IDS, type ChannelId } from "./spec.ts";

export const AUTO_ROUTE = "freemodel-auto";
export const AUTO_MODEL_ID = "best";

/** Check whether a provider route is the auto route. */
export function isAutoRoute(provider: string | undefined): boolean {
  return provider === AUTO_ROUTE;
}

export interface AutoRouteCandidate {
  channel: ChannelId;
  route: string;
  ranked: RankedModel;
}

/**
 * Collect all probe-ok models from active channels, sorted by score descending.
 * Ties are broken stably by channel order in CHANNEL_IDS, then by model id.
 * Manual tier-2 models are NEVER included (only channel models via service.listed).
 */
export function collectCandidates(service: FreemodelService): AutoRouteCandidate[] {
  const candidates: AutoRouteCandidate[] = [];
  for (const id of CHANNEL_IDS) {
    if (!service.isActive(id)) continue;
    const route = routeOf(id);
    for (const ranked of service.listed(id)) {
      candidates.push({ channel: id, route, ranked });
    }
  }

  candidates.sort((a, b) => {
    if (b.ranked.score !== a.ranked.score) {
      return b.ranked.score - a.ranked.score;
    }
    const chA = CHANNEL_IDS.indexOf(a.channel);
    const chB = CHANNEL_IDS.indexOf(b.channel);
    if (chA !== chB) {
      return chA - chB;
    }
    return a.ranked.model.id < b.ranked.model.id ? -1 : a.ranked.model.id > b.ranked.model.id ? 1 : 0;
  });

  return candidates;
}

/**
 * Determine if a chunk represents a terminal stream failure or error.
 */
export function isTerminalFailure(chunk: unknown): boolean {
  if (chunk instanceof Error) return true;
  if (chunk === null || typeof chunk !== "object") return false;
  const c = chunk as Record<string, unknown>;
  if (c.type === "error") return true;
  if (c.type === "finish") {
    const reason = c.reason as Record<string, unknown> | undefined;
    if (reason && (reason.kind === "error" || reason.kind === "aborted")) {
      return true;
    }
  }
  return false;
}

/** Pure helper alias for failover decision. */
export function shouldFailover(chunk: unknown): boolean {
  return isTerminalFailure(chunk);
}

/**
 * Return the next candidate after a failure, or undefined if no more candidates remain.
 * Accepts the count/index of tried candidates, an array of tried candidates, or the last tried candidate.
 */
export function tryNextAfterFailure<T>(
  tried: number | T | readonly T[],
  candidates: readonly T[],
): T | undefined {
  if (typeof tried === "number") {
    return candidates[tried];
  }
  if (Array.isArray(tried)) {
    return candidates[tried.length];
  }
  const idx = candidates.indexOf(tried as T);
  return idx >= 0 ? candidates[idx + 1] : candidates[0];
}

export type DelegateStream = (
  options: GenerateOptions | (Record<string, unknown> & { provider: string; model: string }),
) => AsyncIterable<StreamChunk | Record<string, unknown>>;

/**
 * Lightweight adapter for the freemodel-auto route with in-process failover.
 */
export class AutoRouteAdapter extends LlmAdapter {
  constructor(
    private readonly service: FreemodelService,
    private readonly delegateStream: DelegateStream,
  ) {
    super();
  }

  override providerInfo(provider: string): LlmProviderInfo {
    return {
      id: AUTO_ROUTE,
      name: "FreeModel Auto (best)",
    };
  }

  override async listModels(provider: string): Promise<readonly LlmModelInfo[]> {
    if (provider !== AUTO_ROUTE) return [];
    const candidates = collectCandidates(this.service);
    const top = candidates[0];
    const description = top
      ? `Auto #1: ${top.ranked.model.id} (${CHANNEL_LABELS[top.channel]})`
      : "Auto route (no free model currently available)";
    const inputModalities = top?.ranked.model.input.includes("image")
      ? (["text", "image"] as const)
      : (["text"] as const);

    return [
      {
        provider: AUTO_ROUTE,
        id: AUTO_MODEL_ID,
        name: `Auto · ${FREE_BADGE}`,
        description,
        inputModalities: [...inputModalities],
      },
    ];
  }

  override async resolveModel(
    provider: string,
    model: string,
    _signal?: AbortSignal,
  ): Promise<LlmResolvedModelInfo> {
    const candidates = collectCandidates(this.service);
    const top = candidates[0];
    const contextWindow = top && top.ranked.model.contextLength > 0 ? top.ranked.model.contextLength : 8192;
    const maxTokens = top ? Math.min(top.ranked.model.maxTokens ?? 8192, contextWindow) : 8192;
    const inputModalities = top?.ranked.model.input.includes("image")
      ? (["text", "image"] as const)
      : (["text"] as const);

    return {
      provider: AUTO_ROUTE,
      id: AUTO_MODEL_ID,
      name: `Auto · ${FREE_BADGE}`,
      context: { contextWindow },
      defaultMaxTokens: maxTokens,
      inputModalities: [...inputModalities],
    };
  }

  override async prepareCall(
    provider: string,
    model: string,
    signal?: AbortSignal,
  ): Promise<PreparedAdapterCall> {
    const modelInfo = await this.resolveModel(provider, model, signal);
    return {
      model: modelInfo,
      stream: (options) => this.stream(options),
    };
  }

  override async *stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    const candidates = collectCandidates(this.service);
    if (candidates.length === 0) {
      throw new Error("dsh-freemodel: no free model available");
    }

    let lastFailureChunk: StreamChunk | undefined;
    let lastError: unknown;

    for (const candidate of candidates) {
      let emittedVisible = false;
      const buffer: StreamChunk[] = [];
      let candidateFailed = false;

      try {
        const delegateOptions = {
          ...options,
          provider: candidate.route,
          model: candidate.ranked.model.id,
        };
        const stream = this.delegateStream(delegateOptions as GenerateOptions);

        for await (const rawChunk of stream) {
          const chunk = rawChunk as StreamChunk;
          if (isTerminalFailure(chunk)) {
            if (emittedVisible) {
              // Visible content was already yielded: do NOT failover mid-stream.
              yield chunk;
              return;
            }
            // Terminal failure before any text-delta: record and fail over.
            lastFailureChunk = chunk;
            candidateFailed = true;
            break;
          }

          if (chunk.type === "text-delta" || (chunk as { type?: string }).type === "content-delta") {
            if (!emittedVisible) {
              emittedVisible = true;
              for (const buffered of buffer) {
                yield buffered;
              }
              buffer.length = 0;
            }
            yield chunk;
          } else if (emittedVisible) {
            yield chunk;
          } else {
            buffer.push(chunk);
          }
        }

        if (candidateFailed) {
          continue;
        }

        // Stream completed cleanly without text-delta: flush buffer
        for (const buffered of buffer) {
          yield buffered;
        }
        return;
      } catch (err) {
        if (emittedVisible) {
          // Thrown error mid-stream after visible output: do NOT failover.
          throw err;
        }
        lastError = err;
        // Continue to next candidate
      }
    }

    if (lastError !== undefined) {
      throw lastError;
    }
    if (lastFailureChunk !== undefined) {
      yield lastFailureChunk;
      return;
    }
    throw new Error("dsh-freemodel: all candidate models failed");
  }
}

export function createAutoRouteAdapter(
  service: FreemodelService,
  delegateStream: DelegateStream,
): AutoRouteAdapter {
  return new AutoRouteAdapter(service, delegateStream);
}
