/**
 * Failure classification from spec/providers.json: `errorMap` rules for
 * non-200 responses and the shared `streamError` algorithm for errors inside
 * the SSE stream. Same algorithm as `freemodel_sync.spec.classify_with` and
 * `freemodel_sync.providers.openai_compat.classify_stream_error`.
 */
import { type ChannelId, providersSpec, SpecError } from "./spec.ts";
import { isRecord, truthy } from "./util.ts";

export type FailureKind = "model" | "transient" | "account" | "capacity" | "quota";

export interface ErrorCondition {
  truthy?: string;
  notNull?: string;
  in?: string;
  values?: readonly unknown[];
}

export interface ErrorRule {
  status?: readonly number[];
  statusMin?: number;
  when?: readonly ErrorCondition[];
  kind: FailureKind;
}

export interface ErrorMap {
  preStream: readonly ErrorRule[];
  default: FailureKind;
}

export type ErrorObject = Record<string, unknown>;
export type Classifier = (status: number | null, error: unknown) => FailureKind;

interface StreamErrorSpec {
  accountCodes: readonly number[];
  delegateCodes: readonly number[];
  transientCodes: readonly number[];
}

function lookup(error: ErrorObject, path: string): unknown {
  let value: unknown = error;
  for (const part of path.split(".")) {
    if (!isRecord(value)) return null;
    value = value[part];
  }
  return value === undefined ? null : value;
}

function conditionMatches(condition: ErrorCondition, error: ErrorObject): boolean {
  if (condition.truthy !== undefined) return truthy(lookup(error, condition.truthy));
  if (condition.notNull !== undefined) return lookup(error, condition.notNull) !== null;
  if (condition.in !== undefined) {
    const value = lookup(error, condition.in);
    const scalar = typeof value === "string" || (typeof value === "number" && Number.isFinite(value));
    return scalar && (condition.values ?? []).includes(value);
  }
  throw new SpecError(`unknown condition in error rule: ${JSON.stringify(condition)}`);
}

function ruleMatches(rule: ErrorRule, status: number | null, error: ErrorObject): boolean {
  if (status === null) return false;
  if (rule.status !== undefined && !rule.status.includes(status)) return false;
  if (rule.statusMin !== undefined && status < rule.statusMin) return false;
  const when = rule.when ?? [];
  return when.length === 0 || when.some((c) => conditionMatches(c, error));
}

/**
 * Classify a non-200 response with an `errorMap`: the first rule whose status
 * matches and one of whose conditions holds (or that has none) wins.
 */
export function classifyWith(errorMap: ErrorMap, status: number | null, error: unknown): FailureKind {
  const obj = isRecord(error) ? error : {};
  for (const rule of errorMap.preStream ?? []) {
    if (ruleMatches(rule, status, obj)) return rule.kind;
  }
  return errorMap.default ?? "model";
}

export function defaultErrorMap(): ErrorMap {
  return providersSpec.defaultErrorMap as ErrorMap;
}

export function providerErrorMap(id: ChannelId): ErrorMap {
  return (providersSpec.providers[id]?.errorMap as ErrorMap | undefined) ?? defaultErrorMap();
}

/** The classifier for a channel, or the conservative default (`null`). */
export function classifierFor(id: ChannelId | null): Classifier {
  const map = id === null ? defaultErrorMap() : providerErrorMap(id);
  return (status, error) => classifyWith(map, status, error);
}

/**
 * Classify an error event that arrived inside the SSE stream (after HTTP 200).
 * @param code - the error's numeric code, if any.
 * @param error - the error object.
 * @param classify - the channel's pre-stream classifier (for 403 and odd 4xx codes).
 */
export function classifyStreamError(code: number | null, error: unknown, classify: Classifier): FailureKind {
  const rules = providersSpec.streamError as StreamErrorSpec;
  if (code !== null && rules.accountCodes.includes(code)) return "account";
  if (code !== null && rules.delegateCodes.includes(code)) return classify(code, error);
  if (code !== null && code >= 400 && code < 500 && !rules.transientCodes.includes(code)) {
    return classify(code, error) === "transient" ? "transient" : "model";
  }
  return "transient";
}

/** The error object of an OpenAI-style or DashScope-style JSON body, or `{}`. */
export function errorObjectOf(body: string): ErrorObject {
  try {
    const payload: unknown = JSON.parse(body);
    if (!isRecord(payload)) return {};
    if (isRecord(payload.error)) return payload.error;
    // DashScope sometimes returns code/message/type at the top level.
    const top: ErrorObject = {};
    for (const key of ["code", "message", "type"]) {
      if (key in payload) top[key] = payload[key];
    }
    return top;
  } catch {
    // not JSON
  }
  return {};
}
