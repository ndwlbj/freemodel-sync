/**
 * The status document the card reads, repeated as minimal local types.
 *
 * The browser bundle must not import the host-side `status.ts` (it pulls in
 * `node:fs`); these interfaces are the wire shape documented there and in
 * `spec/state.schema.json`. They contain no key, only key presence facts.
 */

export const CHANNEL_IDS = ["openrouter", "groq", "sensenova", "bailian"] as const;
export type ChannelId = (typeof CHANNEL_IDS)[number];

export interface KeyPresence {
  configured: boolean;
  source?: string;
}

export interface ListedCapabilities {
  tools: boolean | null;
  vision: boolean | null;
  reasoning: boolean | null;
  source: string;
}

export interface ListedQuota {
  unit: string;
  period: string;
  limit: number | null;
  used: number | null;
  remaining: number | null;
  resetsAt: string | null;
  expiresAt: string | null;
  source: string;
  scope: string;
}

export interface ListedModel {
  id: string;
  ttftMs: number | null;
  testedAt: number;
  capabilities?: ListedCapabilities;
  quota?: ListedQuota | null;
  tier?: number;
}

export interface HiddenModel {
  id: string;
  reason: string;
}

export interface LastRound {
  at: number;
  probes: number;
  stopReason: string | null;
}

export interface ChannelModels {
  catalogFetchedAt: number | null;
  catalogError: string | null;
  candidates: number;
  listed: ListedModel[];
  hidden: HiddenModel[];
  probesToday: number;
  lastRound: LastRound | null;
  blockedUntil: number | null;
}

export interface ChannelReport {
  id: ChannelId;
  route: string;
  enabled: boolean;
  apiKeyEnv: string;
  blocked?: string;
  key: KeyPresence | "unknown";
  models: ChannelModels;
}

export interface ManualProbeView {
  provider: string;
  model: string;
  ok: boolean;
  failure_kind: string | null;
  error_code: string | null;
  tested_at: number;
}

export interface ManualEntryView {
  dshProvider: string;
  model: string;
  label: string;
  quotaNote: string;
  expiresAt: string;
  probe: boolean;
  expired: boolean;
  /** null when dsh's provider list is unavailable (e.g. the CLI). */
  detected: boolean | null;
  lastProbe: ManualProbeView | null;
  /** Set when a probe was not run because the route was not registered in dsh. */
  notRunReason?: "route-not-registered" | null;
}

export interface ManualReport {
  enabled: boolean;
  entries: ManualEntryView[];
}

export interface StatusReport {
  schemaVersion: number;
  plugin: string;
  version: string;
  specVersion: number;
  statePath: string;
  stateExists: boolean;
  channels: ChannelReport[];
  manual?: ManualReport;
}

export interface ProbeResultView {
  ok: boolean;
  ttftMs: number | null;
  error: string | null;
  statusCode?: number | null;
  failureKind?: string | null;
  testedAt?: number;
}

export interface ManualTestView {
  channel: ChannelId;
  model: string;
  result: ProbeResultView;
}

export interface ApiErrorBody {
  ok: false;
  error: { code: string; message: string };
}

export interface StatusEnvelope {
  ok: true;
  status: StatusReport;
  /**
   * Process-local token the loopback card presents on writes. It is not the
   * on-disk API secret and is never the provider key.
   */
  writeToken?: string;
}

export interface TestEnvelope {
  ok: true;
  channel: ChannelId;
  model: string;
  result: ProbeResultView;
}

export function isChannelId(value: unknown): value is ChannelId {
  return typeof value === "string" && (CHANNEL_IDS as readonly string[]).includes(value);
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}