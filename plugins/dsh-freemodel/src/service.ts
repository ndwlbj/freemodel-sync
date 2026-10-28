/**
 * The free-model service: keeps each channel's catalogue and probe results
 * (state file), decides which channels are active, which models are listed
 * and why the others are not, and schedules the background refresh.
 *
 * A channel is ACTIVE when it is enabled, its key reference resolves, and
 * (Groq) the free plan is confirmed. Only active channels are read, probed or
 * registered. Listed models are the filtered catalogue entries whose latest
 * probe succeeded; failed or untested ones are kept in the report with the
 * reason. Keys are resolved per operation and never stored or logged.
 */
import {
  type FreemodelConfig,
  providersOf,
  rankingOf,
  refreshOf,
  routeOf,
} from "./channels.ts";
import { FALLBACK_DAILY_FREE_LIMIT, runProbeRound } from "./probe.ts";
import { GroqChannel } from "./providers/groq.ts";
import type { OpenAICompatChannel } from "./providers/openai-compat.ts";
import { OpenRouterChannel } from "./providers/openrouter.ts";
import { type CatalogModel, modelKey, type ProbeResult } from "./providers/types.ts";
import { filterModels, rank, type RankedModel } from "./rank.ts";
import { redact } from "./redact.ts";
import { CHANNEL_IDS, type ChannelId } from "./spec.ts";
import { addRequests, loadState, requestsToday, saveState, type StateData } from "./state.ts";

/** Transient failures are retried after this long (Python's transient_ttl_minutes). */
export const TRANSIENT_TTL_S = 30 * 60;
/** How often the key references and settings are re-checked. */
export const KEY_CHECK_MS = 15_000;
/** Shortest gap between two scheduled refreshes. */
const MIN_TIMER_MS = 5_000;

export interface KeyAccess {
  /** Whether the reference resolves, without reading it. */
  configured(ref: string): Promise<boolean>;
  /** The value, for one operation only. */
  resolve(ref: string): Promise<string | undefined>;
}

export interface ServiceLogger {
  info(message: string, ...args: unknown[]): void;
  warn(message: string, ...args: unknown[]): void;
}

export interface ServiceOptions {
  config: FreemodelConfig;
  statePath: string;
  keys: KeyAccess;
  logger: ServiceLogger;
  channels?: Partial<Record<ChannelId, OpenAICompatChannel>>;
  /** Called whenever active channels or listed models may have changed. */
  onChange?: () => void;
  now?: () => number;
}

/** Why a manual probe was refused before any request was sent. */
export type ManualTestErrorCode = "channel-disabled" | "free-plan-unconfirmed" | "no-key" | "model-not-found";

/** A refused manual probe; the message is safe to show and never holds a key. */
export class ManualTestError extends Error {
  override name = "ManualTestError";
  readonly code: ManualTestErrorCode;

  constructor(code: ManualTestErrorCode, message: string) {
    super(message);
    this.code = code;
  }
}

/** A manual probe that was sent and stored. */
export interface ManualTestOutcome {
  channel: ChannelId;
  model: CatalogModel;
  result: ProbeResult;
}

export interface ChannelView {
  id: ChannelId;
  route: string;
  enabled: boolean;
  active: boolean;
  /** Why the channel lists nothing, when it does not. */
  blocked: string | null;
  listed: RankedModel[];
  /** Catalogue models not listed, with the reason (failed probe, not probed yet). */
  hidden: Array<{ id: string; reason: string }>;
  catalogFetchedAt: number | null;
  catalogError: string | null;
  probesToday: number;
  lastRound: StateData["channels"][ChannelId]["lastRound"];
  blockedUntil: number | null;
}

export class FreemodelService {
  readonly channels: Record<ChannelId, OpenAICompatChannel>;
  state: StateData;
  private readonly active = new Set<ChannelId>();
  private readonly blockedReason = new Map<ChannelId, string>();
  private timer: NodeJS.Timeout | undefined;
  private keyTimer: NodeJS.Timeout | undefined;
  private running: Promise<void> | undefined;
  private readonly abort = new AbortController();
  private disposed = false;

  constructor(private readonly options: ServiceOptions) {
    this.channels = {
      openrouter: options.channels?.openrouter ?? new OpenRouterChannel(),
      groq: options.channels?.groq ?? new GroqChannel(),
    };
    this.state = loadState(options.statePath);
  }

  private now(): number {
    return this.options.now?.() ?? Date.now();
  }

  private ref(id: ChannelId): string {
    return providersOf(this.options.config)[id].apiKeyEnv;
  }

  /** Re-evaluate which channels are active; true when the set changed. */
  async checkActive(): Promise<boolean> {
    const providers = providersOf(this.options.config);
    let changed = false;
    for (const id of CHANNEL_IDS) {
      const channel = providers[id];
      let reason: string | null = null;
      if (!channel.enabled) reason = "disabled";
      else if (id === "groq" && !providers.groq.freePlanConfirmed) {
        reason = "freePlanConfirmed is off (Groq models are free only on a Free-plan organization)";
      } else {
        let configured = false;
        try {
          configured = await this.options.keys.configured(channel.apiKeyEnv);
        } catch {
          configured = false;
        }
        if (!configured) reason = `no key: save one for ${channel.apiKeyEnv} in the settings page`;
      }
      const isActive = reason === null;
      if (isActive !== this.active.has(id)) changed = true;
      if (isActive) this.active.add(id);
      else this.active.delete(id);
      if (reason === null) this.blockedReason.delete(id);
      else this.blockedReason.set(id, reason);
    }
    return changed;
  }

  isActive(id: ChannelId): boolean {
    return this.active.has(id);
  }

  activeRoutes(): string[] {
    return CHANNEL_IDS.filter((id) => this.active.has(id)).map(routeOf);
  }

  /** The key for one operation on an active channel. */
  async resolveKey(id: ChannelId): Promise<string | undefined> {
    try {
      const value = await this.options.keys.resolve(this.ref(id));
      return value === undefined || value === "" ? undefined : value;
    } catch {
      return undefined;
    }
  }

  /**
   * Probe one model on demand (settings page / `/freemodel test`), bypassing
   * the cache and the scheduled budget because the user asked for it. The
   * model must be in the channel's free catalogue; disabled channels, Groq
   * without the free-plan confirmation, and missing keys are refused before
   * any request is sent. The result is stored and the counter is incremented.
   * @param id - channel to probe.
   * @param modelId - exact catalogue model id.
   */
  async testModel(id: ChannelId, modelId: string): Promise<ManualTestOutcome> {
    const providers = providersOf(this.options.config);
    if (!providers[id].enabled) throw new ManualTestError("channel-disabled", `${id} is disabled in the freemodel settings`);
    if (id === "groq" && !providers.groq.freePlanConfirmed) {
      throw new ManualTestError("free-plan-unconfirmed", "groq needs freePlanConfirmed before any probe, or the request could be billed");
    }
    const channel = this.state.channels[id];
    const model = (channel.catalog?.models ?? []).find((m) => m.id === modelId);
    if (model === undefined) throw new ManualTestError("model-not-found", `${modelId} is not in the ${id} free catalogue`);
    const apiKey = await this.resolveKey(id);
    if (apiKey === undefined) throw new ManualTestError("no-key", `no key: save one for ${this.ref(id)} in the settings page`);
    let result: ProbeResult;
    try {
      result = await this.channels[id].probe(model, apiKey);
    } catch (error) {
      const e = error as { name?: string; message?: string };
      result = {
        key: modelKey(model),
        ok: false,
        ttftMs: null,
        totalMs: null,
        error: `${e?.name ?? "Error"}: ${e?.message ?? String(error)}`,
        statusCode: null,
        testedAt: this.now() / 1000,
        failureKind: "transient",
        retryAfterS: null,
        rateLimitRemaining: null,
      };
    }
    if (result.error !== null) result = { ...result, error: redact(result.error, [apiKey]) };
    addRequests(channel, 1, this.now());
    if (result.ok || result.failureKind !== "account") {
      channel.results[modelKey(model)] = result;
    } else if (result.retryAfterS !== null) {
      channel.blockedUntil = this.now() / 1000 + result.retryAfterS;
    }
    this.save();
    this.options.onChange?.();
    return { channel: id, model, result };
  }

  /** Catalogue models that pass the listing filters, ranked with their probe results. */
  ranked(id: ChannelId): RankedModel[] {
    const channel = this.state.channels[id];
    const ranking = rankingOf(this.options.config);
    const today = new Date(this.now()).toISOString().slice(0, 10);
    const models = filterModels(channel.catalog?.models ?? [], {
      requireTools: ranking.requireTools,
      minContext: ranking.minContext,
      today,
    });
    return rank(models, channel.results, undefined, today);
  }

  /** Models to show in the picker: active channel, filters passed, latest probe succeeded. */
  listed(id: ChannelId): RankedModel[] {
    if (!this.active.has(id)) return [];
    return this.ranked(id).filter((r) => r.test?.ok === true);
  }

  view(id: ChannelId): ChannelView {
    const providers = providersOf(this.options.config);
    const channel = this.state.channels[id];
    const ranked = this.ranked(id);
    const active = this.active.has(id);
    const listed = active ? ranked.filter((r) => r.test?.ok === true) : [];
    const hidden = ranked
      .filter((r) => r.test?.ok !== true)
      .map((r) => ({ id: r.model.id, reason: r.test === null ? "not probed yet" : (r.reasons[0] ?? "failed") }));
    return {
      id,
      route: routeOf(id),
      enabled: providers[id].enabled,
      active,
      blocked: this.blockedReason.get(id) ?? (active && listed.length === 0 ? "no model has passed a probe yet" : null),
      listed,
      hidden,
      catalogFetchedAt: channel.catalog?.fetchedAt ?? null,
      catalogError: channel.catalog?.error ?? null,
      probesToday: requestsToday(channel, this.now()),
      lastRound: channel.lastRound,
      blockedUntil: channel.blockedUntil,
    };
  }

  private catalogDue(id: ChannelId): boolean {
    const catalog = this.state.channels[id].catalog;
    if (catalog === null || catalog.fetchedAt === 0) return true;
    return this.now() / 1000 - catalog.fetchedAt >= refreshOf(this.options.config).catalogHours * 3600;
  }

  private probeDue(id: ChannelId): boolean {
    const channel = this.state.channels[id];
    const nowS = this.now() / 1000;
    if (channel.blockedUntil !== null && channel.blockedUntil > nowS) return false;
    const last = channel.lastRound;
    if (last === null) return true;
    const sinceLast = nowS - last.at;
    if (sinceLast >= refreshOf(this.options.config).probeHours * 3600) return true;
    // A model that failed transiently is retried soon, as are newly listed models never probed.
    const top = this.ranked(id).slice(0, refreshOf(this.options.config).probeTopN);
    return sinceLast >= TRANSIENT_TTL_S && top.some((r) => r.test === null || (r.test.failureKind === "transient" && nowS - r.test.testedAt >= TRANSIENT_TTL_S));
  }

  /** Seconds until the next refresh is due for any active channel (null: nothing scheduled). */
  nextDueMs(): number | null {
    const refresh = refreshOf(this.options.config);
    const nowS = this.now() / 1000;
    let next: number | null = null;
    const consider = (atS: number): void => {
      const ms = Math.max(MIN_TIMER_MS, (atS - nowS) * 1000);
      next = next === null ? ms : Math.min(next, ms);
    };
    for (const id of this.active) {
      const channel = this.state.channels[id];
      consider((channel.catalog?.fetchedAt ?? 0) + refresh.catalogHours * 3600);
      const last = channel.lastRound?.at ?? 0;
      consider(Math.max(last + refresh.probeHours * 3600, channel.blockedUntil ?? 0));
      if (this.ranked(id).slice(0, refresh.probeTopN).some((r) => r.test === null || r.test.failureKind === "transient")) {
        consider(Math.max(last + TRANSIENT_TTL_S, channel.blockedUntil ?? 0));
      }
    }
    return next;
  }

  /** Read catalogues and probe what is due on every active channel (one run at a time). */
  refresh(force: { catalog?: boolean; probe?: boolean } = {}): Promise<void> {
    if (this.running !== undefined) return this.running;
    this.running = this.doRefresh(force).finally(() => {
      this.running = undefined;
      this.schedule();
    });
    return this.running;
  }

  private async doRefresh(force: { catalog?: boolean; probe?: boolean }): Promise<void> {
    await this.checkActive();
    let dirty = false;
    for (const id of CHANNEL_IDS) {
      if (this.disposed || !this.active.has(id)) continue;
      const apiKey = await this.resolveKey(id);
      if (apiKey === undefined) continue;
      try {
        if (force.catalog === true || this.catalogDue(id)) {
          dirty = true;
          await this.refreshCatalog(id, apiKey);
        }
        if (force.probe === true || this.probeDue(id)) {
          dirty = true;
          await this.probeRound(id, apiKey);
        }
      } catch (error) {
        this.options.logger.warn(`dsh-freemodel: ${id} refresh failed: ${redact(String(error), [apiKey])}`);
      }
    }
    if (dirty && !this.disposed) {
      this.save();
      this.options.onChange?.();
    }
  }

  private async refreshCatalog(id: ChannelId, apiKey: string): Promise<void> {
    const channel = this.state.channels[id];
    const nowS = this.now() / 1000;
    try {
      const models = await this.channels[id].discover(apiKey, this.abort.signal);
      channel.catalog = { fetchedAt: nowS, models, error: null, errorAt: null };
      this.options.logger.info(`dsh-freemodel: ${id} catalogue: ${models.length} free models`);
    } catch (error) {
      const message = redact(error instanceof Error ? error.message : String(error), [apiKey]);
      channel.catalog = {
        fetchedAt: channel.catalog?.fetchedAt ?? 0,
        models: channel.catalog?.models ?? [],
        error: message,
        errorAt: nowS,
      };
      this.options.logger.warn(`dsh-freemodel: ${message}`);
    }
  }

  private async probeRound(id: ChannelId, apiKey: string): Promise<void> {
    const refresh = refreshOf(this.options.config);
    const channel = this.state.channels[id];
    const candidates = this.ranked(id).map((r) => r.model);
    let dailyBudget: number | null = null;
    let remainingBudget: number | null = null;
    if (refresh.dailyProbeLimit > 0) {
      dailyBudget = refresh.dailyProbeLimit;
    } else {
      const quota = await this.channels[id].quota(apiKey, this.abort.signal);
      if (quota !== null && quota.dailyFreeRemaining !== null) {
        remainingBudget = quota.dailyFreeRemaining;
        const local = requestsToday(channel, this.now());
        if (quota.dailyFreeLimit !== null && local > (quota.dailyFreeUsed ?? 0)) {
          remainingBudget = Math.min(remainingBudget, Math.max(0, quota.dailyFreeLimit - local));
        }
      } else if (quota !== null && quota.dailyFreeLimit !== null) {
        dailyBudget = quota.dailyFreeLimit;
      } else {
        dailyBudget = FALLBACK_DAILY_FREE_LIMIT;
      }
    }
    const round = await runProbeRound(this.channels[id], candidates, channel, {
      apiKey,
      maxTests: refresh.probeTopN,
      cacheTtlS: refresh.probeHours * 3600,
      transientTtlS: TRANSIENT_TTL_S,
      dailyBudget,
      remainingBudget,
      reserve: refresh.reserveRequests,
      signal: this.abort.signal,
      nowS: () => this.now() / 1000,
    });
    channel.lastRound = { at: this.now() / 1000, probes: round.probes, stopReason: round.stopReason };
    const ok = [...round.results.values()].filter((r) => r.ok).length;
    this.options.logger.info(
      `dsh-freemodel: ${id} probes: ${round.probes} sent, ${ok} working` + (round.stopReason === null ? "" : `; stopped: ${round.stopReason}`),
    );
  }

  /**
   * Start: list from the cached state at once, then refresh (onStartup) or
   * wait for the scheduler, and keep checking keys.
   */
  async start(): Promise<void> {
    await this.checkActive();
    this.options.onChange?.();
    if (refreshOf(this.options.config).onStartup) void this.refresh();
    else this.schedule();
    const tick = (): void => {
      this.keyTimer = setTimeout(() => {
        void this.recheck().then(() => {
          if (!this.disposed) tick();
        });
      }, KEY_CHECK_MS);
      this.keyTimer.unref?.();
    };
    tick();
  }

  /** Re-check keys and settings now (e.g. the credential service appeared); refresh if the active set changed. */
  async recheck(): Promise<void> {
    if (this.disposed) return;
    const changed = await this.checkActive();
    if (this.disposed || !changed) return;
    this.options.onChange?.();
    if (refreshOf(this.options.config).onStartup) void this.refresh();
    else this.schedule();
  }

  private schedule(): void {
    clearTimeout(this.timer);
    if (this.disposed) return;
    const ms = this.nextDueMs();
    if (ms === null) return;
    this.timer = setTimeout(() => void this.refresh(), Math.min(ms, 2 ** 31 - 1));
    this.timer.unref?.();
  }

  private save(): void {
    try {
      saveState(this.options.statePath, this.state);
    } catch (error) {
      this.options.logger.warn(`dsh-freemodel: cannot write ${this.options.statePath}: ${String(error)}`);
    }
  }

  dispose(): void {
    this.disposed = true;
    clearTimeout(this.timer);
    clearTimeout(this.keyTimer);
    this.abort.abort();
  }

  /** Models a catalogue lists right now for the settings page's discovery (no probe, nothing stored). */
  async discoverFor(id: ChannelId, apiKey: string | undefined, signal?: AbortSignal): Promise<CatalogModel[]> {
    const cached = this.state.channels[id].catalog?.models;
    if (cached !== undefined && cached.length > 0) return filterModels(cached, rankingOf(this.options.config));
    if (id === "groq" && !providersOf(this.options.config).groq.freePlanConfirmed) return [];
    const key = apiKey ?? (await this.resolveKey(id));
    return filterModels(await this.channels[id].discover(key, signal), rankingOf(this.options.config));
  }
}
