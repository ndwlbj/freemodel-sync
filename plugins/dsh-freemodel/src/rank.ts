/**
 * Filter, score and rank free models from their probe results. Port of
 * `freemodel_sync.ranking`; weights and constants come from spec/ranking.json
 * and the golden cases in spec/conformance/score.json pin the arithmetic.
 */
import type { CatalogModel, ProbeResult } from "./providers/types.ts";
import { modelKey } from "./providers/types.ts";
import { rankingSpec } from "./spec.ts";
import { daysBetween, fnmatchcase, utcToday } from "./util.ts";

export interface RankWeights {
  availability: number;
  latency: number;
  context: number;
  tools: number;
  expiry_penalty: number;
  untested_penalty: number;
}

interface ScoreSpec {
  failedScore: number;
  latencyScaleMs: number;
  contextReference: number;
  expiryWindowDays: number;
}

const SCORE = rankingSpec.score as unknown as ScoreSpec;
const LOG2_REFERENCE = Math.log2(SCORE.contextReference);

export function defaultWeights(): RankWeights {
  return { ...(rankingSpec.weights as unknown as RankWeights) };
}

/** Id/name globs (case-insensitive) of free models that are not chat models. */
export const NON_CHAT_PATTERNS: readonly string[] = rankingSpec.nonChatPatterns as string[];

export function isNonChat(model: Pick<CatalogModel, "id" | "name">): boolean {
  const haystacks = [model.id.toLowerCase(), (model.name || "").toLowerCase()];
  return haystacks.some((h) => NON_CHAT_PATTERNS.some((p) => fnmatchcase(h, p)));
}

export function daysUntilExpiry(model: Pick<CatalogModel, "expirationDate">, today: string = utcToday()): number | null {
  return model.expirationDate === null ? null : daysBetween(today, model.expirationDate);
}

export interface FilterOptions {
  /** Drop models whose catalogue says they have no tool calling (unknown passes). */
  requireTools?: boolean;
  minContext?: number;
  today?: string;
}

/** Models worth listing and probing, in input order: chat models, not expired, enough context, tools when required. */
export function filterModels(models: Iterable<CatalogModel>, options: FilterOptions = {}): CatalogModel[] {
  const kept: CatalogModel[] = [];
  for (const model of models) {
    if (isNonChat(model)) continue;
    if (options.requireTools === true && model.tools === false) continue;
    if (model.contextLength < (options.minContext ?? 0)) continue;
    const days = daysUntilExpiry(model, options.today);
    if (days !== null && days < 0) continue;
    kept.push(model);
  }
  return kept;
}

export type TestLike = Pick<ProbeResult, "ok" | "ttftMs" | "failureKind" | "error" | "statusCode">;

/** A model's score and short human-readable reasons. */
export function scoreModel(
  model: CatalogModel,
  test: TestLike | null | undefined,
  weights: RankWeights = defaultWeights(),
  today: string = utcToday(),
): [number, string[]] {
  const reasons: string[] = [];
  if (test !== null && test !== undefined && !test.ok) {
    if (test.failureKind === "transient") {
      const code = test.statusCode ? ` ${test.statusCode}` : "";
      return [SCORE.failedScore, [`temporarily unavailable${code}: ${test.error || "unknown error"} (retried later)`]];
    }
    return [SCORE.failedScore, [`failed: ${test.error || "unknown error"}`]];
  }
  let score: number;
  if (test === null || test === undefined) {
    score = -weights.untested_penalty;
    reasons.push("untested");
  } else {
    score = weights.availability;
  }
  if (test && test.ok && test.ttftMs) {
    score += weights.latency * Math.max(0, 1 - test.ttftMs / SCORE.latencyScaleMs);
  }
  const contextLength = Math.max(model.contextLength, 1);
  score += weights.context * Math.min(1, Math.log2(contextLength) / LOG2_REFERENCE);
  if (model.tools === true) score += weights.tools;
  const days = daysUntilExpiry(model, today);
  if (days !== null && days < SCORE.expiryWindowDays) {
    score -= (weights.expiry_penalty * (SCORE.expiryWindowDays - Math.max(days, 0))) / SCORE.expiryWindowDays;
    reasons.push(days < 0 ? `expired ${-days} day(s) ago` : `expires in ${days} days`);
  }
  return [score, reasons];
}

export interface RankedModel {
  model: CatalogModel;
  score: number;
  test: ProbeResult | null;
  reasons: string[];
}

/** Score and sort by descending score, ties by model id (code-point order, like Python). */
export function rank(
  models: Iterable<CatalogModel>,
  results: ReadonlyMap<string, ProbeResult> | Readonly<Record<string, ProbeResult>>,
  weights: RankWeights = defaultWeights(),
  today: string = utcToday(),
): RankedModel[] {
  const get = (key: string): ProbeResult | null =>
    (results instanceof Map ? results.get(key) : (results as Record<string, ProbeResult>)[key]) ?? null;
  const ranked: RankedModel[] = [];
  for (const model of models) {
    const test = get(modelKey(model));
    const [score, reasons] = scoreModel(model, test, weights, today);
    ranked.push({ model, score, test, reasons });
  }
  ranked.sort((a, b) => (b.score !== a.score ? b.score - a.score : a.model.id < b.model.id ? -1 : a.model.id > b.model.id ? 1 : 0));
  return ranked;
}
