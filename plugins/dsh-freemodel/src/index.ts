/**
 * dsh-freemodel: free models for DeepSeek Harness.
 *
 * Registers the model routes `freemodel-openrouter` and `freemodel-groq` for
 * the channels that are active (enabled, key saved, Groq: free plan
 * confirmed). Their models are the free catalogue entries that passed a tiny
 * probe; the others stay out of the picker and the reason is kept in the
 * state file and `dsh-freemodel status`. The profile's default model is
 * never changed.
 */
import type { Context } from "@deepseek-ai/cordis";
import type { StreamChunk } from "@deepseek-ai/dsh-llm";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { createAdapter, channelOfRoute, displayName, FREE_BADGE } from "./adapter.ts";
import {
  AUTO_MODEL_ID,
  AUTO_ROUTE,
  AutoRouteAdapter,
  collectCandidates,
  createAutoRouteAdapter,
  isAutoRoute,
  type AutoRouteCandidate,
} from "./auto-route.ts";
import {
  autoDefaultModelOf,
  autoRouteOf,
  defaultAutoRoute,
  type AutoRouteConfig,
  type FreemodelConfig,
  routeOf,
} from "./channels.ts";
import { createFreemodelCommand } from "./command.ts";
import {
  applyDefaultModelSwitch,
  assertSafeProfile,
  planDefaultModelSwitch,
  QQ_PROFILE_DENY,
  resolveProfile,
  updateDefaultModelPatch,
  type DefaultModelLogRecord,
  type DefaultModelPlan,
  type ResolvedProfile,
} from "./default-model.ts";
import { API_PREFIX, createLocalApiHandler, generateSecret, loadOrCreateSecret } from "./local-api.ts";
import { FreemodelService } from "./service.ts";
import { CHANNEL_IDS, type ChannelId, providerSpec } from "./spec.ts";
import { buildStatus, type DescribeKey, dshHome, statePath } from "./status.ts";
import { PLUGIN_VERSION } from "./version.ts";

export {
  autoDefaultModelOf,
  autoRouteOf,
  channelStates,
  defaultAutoRoute,
  defaultProviders,
  defaultRanking,
  defaultRefresh,
  providersOf,
  routeOf,
} from "./channels.ts";
export type {
  AutoRouteConfig,
  ChannelState,
  FreemodelConfig,
  FreemodelConfigInput,
  Live,
  ProvidersConfig,
  RankingConfig,
  RefreshConfig,
} from "./channels.ts";
export {
  AUTO_MODEL_ID,
  AUTO_ROUTE,
  AutoRouteAdapter,
  collectCandidates,
  createAutoRouteAdapter,
  isAutoRoute,
} from "./auto-route.ts";
export type { AutoRouteCandidate } from "./auto-route.ts";
export {
  applyDefaultModelSwitch,
  assertSafeProfile,
  planDefaultModelSwitch,
  QQ_PROFILE_DENY,
  resolveProfile,
  updateDefaultModelPatch,
} from "./default-model.ts";
export type { DefaultModelLogRecord, DefaultModelPlan, ResolvedProfile } from "./default-model.ts";
export { Config } from "./config.ts";
export { buildStatus, runDoctor, statePath } from "./status.ts";
export type { DoctorReport, StatusReport } from "./status.ts";
export { PLUGIN_VERSION } from "./version.ts";

/** Stable Cordis plugin name. */
export const name = "dsh-freemodel";

/** The model registry must exist before the plugin mounts. */
export const inject = ["llm"];

interface CredentialService {
  describe(ref: string): Promise<{ configured: boolean; source?: string; writable: boolean }>;
  resolve(ref: string): Promise<{ value: string; source: string } | undefined>;
}

interface LlmService {
  registerAdapter(providers: string[], adapter: unknown): { (): void; replace(providers: string[]): void };
  registerConfigurableProviders(entries: readonly unknown[]): { (): void; replace(entries: readonly unknown[]): void };
  registerModelDiscovery(
    settingsNs: string,
    discover: (request: { provider?: string; apiKey?: string }, signal?: AbortSignal) => Promise<readonly unknown[]>,
  ): () => void;
  /** Public registry read used to detect manual dsh routes (no third-party state files). */
  listProviders(): Array<{ id: string; name: string }>;
  stream(options: {
    provider: string;
    model: string;
    messages: Array<{ role: "user"; content: Array<{ type: "text"; text: string }> }>;
    maxTokens: number;
    signal?: AbortSignal;
  }): AsyncIterable<{ type: string; reason?: { kind?: string; failure?: { code?: string; status?: number; message?: string } } }>;
}

/**
 * Plugin entry point.
 * @param ctx - plugin context.
 * @param config - validated settings.
 */
export function apply(ctx: Context, config: FreemodelConfig): void {
  // The credential service is optional and may start after this plugin.
  let credentials: CredentialService | undefined;
  const llm = (ctx as unknown as { llm: LlmService }).llm;
  const settingsNs =
    (ctx as unknown as { fiber?: { entry?: { options?: { id?: string } } } }).fiber?.entry?.options?.id ?? name;

  const service = new FreemodelService({
    config,
    statePath: statePath(),
    logger: ctx.logger,
    keys: {
      async configured(ref) {
        if (credentials !== undefined) {
          try {
            const desc = await credentials.describe(ref);
            if (desc?.configured) {
              return true;
            }
          } catch {
            // credentials lookup threw; fall through to process.env
          }
        }
        const envVal = process.env[ref];
        return envVal !== undefined && envVal.trim() !== "";
      },
      async resolve(ref) {
        if (credentials !== undefined) {
          try {
            const res = await credentials.resolve(ref);
            if (res?.value !== undefined && res.value.trim() !== "") {
              return res.value;
            }
          } catch {
            // credentials resolve threw; fall through to process.env
          }
        }
        const envVal = process.env[ref];
        return envVal !== undefined && envVal.trim() !== "" ? envVal : undefined;
      },
    },
    onChange: () => sync(),
    llm,
  });
  const { adapter, invalidate } = createAdapter(service, () => ctx.get("attachments"));
  const autoAdapter = createAutoRouteAdapter(service, (options) => {
    return typeof (llm as unknown as { stream?: unknown }).stream === "function"
      ? (llm as unknown as { stream: (opts: unknown) => AsyncIterable<StreamChunk> }).stream(options)
      : adapter.stream(options as Parameters<typeof adapter.stream>[0]);
  });

  const describeKey: DescribeKey = async (ref) => {
    if (credentials !== undefined) {
      try {
        const info = await credentials.describe(ref);
        if (info?.configured) {
          return info.source === undefined ? { configured: true } : { configured: true, source: info.source };
        }
      } catch {
        // credentials lookup threw; fall through to process.env
      }
    }
    const envVal = process.env[ref];
    if (envVal !== undefined && envVal.trim() !== "") {
      return { configured: true, source: "env" };
    }
    return { configured: false };
  };
  const readStatus = () =>
    buildStatus(
      config,
      describeKey,
      process.env,
      () => llm.listProviders().map((provider) => provider.id),
    );

  let adapterHandle: ReturnType<LlmService["registerAdapter"]> | undefined;
  let autoAdapterHandle: ReturnType<LlmService["registerAdapter"]> | undefined;
  let lastSummary = "";
  let disposed = false;
  let warnedMissingProfile = false;
  const lastDefaultModelLog = { current: undefined as DefaultModelLogRecord | undefined };

  const directoryEntries = () => {
    const entries: Array<Record<string, unknown>> = CHANNEL_IDS.map((id) => {
      const view = service.view(id);
      const entry: Record<string, unknown> = {
        provider: routeOf(id),
        displayName: displayName(id),
        settingsNs,
        settingsPath: ["providers", id],
        declared: false,
        defaultBaseURL: providerSpec(id).baseURL,
      };
      if (view.enabled && !view.active && view.blocked !== null && view.blocked !== "disabled") entry.error = view.blocked;
      return entry;
    });
    if (autoRouteOf(config).enabled) {
      entries.push({
        provider: AUTO_ROUTE,
        displayName: "FreeModel Auto (best)",
        settingsNs,
        settingsPath: ["autoRoute"],
        declared: false,
      });
    }
    return entries;
  };
  const directory = llm.registerConfigurableProviders(directoryEntries());

  function sync(): void {
    if (disposed) return;
    invalidate();
    const routes = service.activeRoutes();
    const autoEnabled = autoRouteOf(config).enabled;
    try {
      if (adapterHandle === undefined) {
        if (routes.length > 0) adapterHandle = llm.registerAdapter(routes, adapter);
      } else {
        adapterHandle.replace(routes);
      }
      if (autoEnabled) {
        if (autoAdapterHandle === undefined) {
          autoAdapterHandle = llm.registerAdapter([AUTO_ROUTE], autoAdapter);
        } else {
          autoAdapterHandle.replace([AUTO_ROUTE]);
        }
      } else if (autoAdapterHandle !== undefined) {
        autoAdapterHandle.replace([]);
      }
      directory.replace(directoryEntries());
    } catch (error) {
      ctx.logger.warn("dsh-freemodel: route registration failed", error);
    }
    (ctx as unknown as { emit(event: string): void }).emit("llm/adapters-updated");
    const summary = CHANNEL_IDS.map((id) => {
      const v = service.view(id);
      return v.active ? `${id}: ${v.listed.length} listed, ${v.hidden.length} hidden` : `${id}: off (${v.blocked ?? "inactive"})`;
    }).join("; ");
    if (summary !== lastSummary) {
      lastSummary = summary;
      ctx.logger.info(`dsh-freemodel ${PLUGIN_VERSION}: ${summary}`);
    }

    const defaultModelEnabled = autoDefaultModelOf(config);
    if (defaultModelEnabled) {
      try {
        const profile = resolveProfile((k) => ctx.get(k), process.env);
        if (!profile?.name) {
          if (!warnedMissingProfile) {
            warnedMissingProfile = true;
            ctx.logger.warn(
              "dsh-freemodel: autoDefaultModel is on but the current profile cannot be determined (no profileContext, no DSH_PROFILE); skipping",
            );
          }
        } else {
          const candidates = collectCandidates(service);
          const topCandidate = candidates[0];
          const top = topCandidate !== undefined ? { route: topCandidate.route, modelId: topCandidate.ranked.model.id } : null;
          const plan = planDefaultModelSwitch({
            enabled: defaultModelEnabled,
            profileId: profile.name,
            autoRouteEnabled: autoEnabled,
            top,
          });
          if (plan.action !== "skipped") {
            const home = dshHome();
            const homePatch = join(home, "cordis.patch.yml");
            const profilePatch = profile.dir
              ? (resolve(profile.dir) === resolve(home) || resolve(profile.dir) === resolve(homePatch)
                  ? homePatch
                  : join(profile.dir, "cordis.patch.yml"))
              : join(home, "profiles", profile.name, "cordis.patch.yml");
            applyDefaultModelSwitch(plan, {
              readPatch: (p) => readFileSync(p, "utf-8"),
              writePatch: (p, text) => {
                mkdirSync(dirname(p), { recursive: true });
                writeFileSync(p, text, "utf-8");
              },
              profilePatchPath: profilePatch,
              homePatchPath: homePatch,
              logger: ctx.logger,
              lastLog: lastDefaultModelLog,
            });
          }
        }
      } catch (error) {
        ctx.logger.warn("dsh-freemodel: failed to apply default model switch", error);
      }
    }
  }

  const releaseDiscovery = llm.registerModelDiscovery(settingsNs, async (request, signal) => {
    if (isAutoRoute(request.provider)) {
      return [
        {
          id: AUTO_MODEL_ID,
          name: `Auto · ${FREE_BADGE}`,
        },
      ];
    }
    const id = channelOfRoute(request.provider);
    if (id === undefined) throw new Error("dsh-freemodel: discovery serves only the freemodel-* routes");
    const models = await service.discoverFor(id, request.apiKey, signal);
    return models.map((m) => ({
      id: m.id,
      name: m.name,
      ...(m.contextLength > 0 ? { contextWindow: m.contextLength } : {}),
      ...(m.maxTokens === null ? {} : { maxTokens: m.maxTokens }),
      inputModalities: m.input,
    }));
  });

  type Injectable = { inject(deps: string[], fn: (inner: Context) => void): unknown };

  (ctx as unknown as Injectable).inject(["commands"], (inner) => {
    const commands = (inner as unknown as {
      commands: { register(definition: ReturnType<typeof createFreemodelCommand>): () => void };
    }).commands;
    const scoped = inner as unknown as { effect(fn: () => () => void): unknown };
    scoped.effect(() =>
      commands.register(
        createFreemodelCommand({
          status: readStatus,
          refresh: () => service.refresh({ catalog: true, probe: true }),
          testModel: (channel: ChannelId, model: string) => service.testModel(channel, model),
        }),
      ),
    );
  });

  (ctx as unknown as Injectable).inject(["webServer"], (inner) => {
    const web = (inner as unknown as {
      webServer: { register(route: { kind: "prefix"; path: string; handler: ReturnType<typeof createLocalApiHandler> }): () => void };
    }).webServer;
    let secret: string;
    try {
      secret = loadOrCreateSecret(join(dirname(statePath()), "api-secret"));
    } catch (error) {
      ctx.logger.warn("dsh-freemodel: cannot load the local API secret; using an in-memory one", error);
      secret = generateSecret();
    }
    // The settings card cannot read the on-disk secret. Give it a separate
    // process-local token through the loopback status document; it authorizes
    // the same writes and dies with this plugin instance.
    const clientKey = generateSecret();
    const handler = createLocalApiHandler({
      status: readStatus,
      refresh: () => service.refresh({ catalog: true, probe: true }),
      testModel: async (channel: ChannelId, model: string) => {
        const outcome = await service.testModel(channel, model);
        return { channel: outcome.channel, model: outcome.model.id, result: outcome.result };
      },
      secret: () => secret,
      clientKey: () => clientKey,
      logger: ctx.logger,
    });
    const scoped = inner as unknown as { effect(fn: () => () => void): unknown };
    scoped.effect(() => web.register({ kind: "prefix", path: API_PREFIX, handler }));
  });

  let releaseAdaptersListener: (() => void) | undefined;
  if (typeof (ctx as unknown as { on?: unknown }).on === "function") {
    releaseAdaptersListener = (ctx as unknown as { on(event: string, fn: () => void): () => void }).on(
      "llm/adapters-updated",
      () => {
        try {
          const registeredRoutes = llm.listProviders().map((p) => p.id);
          service.recheckManualRoutes(registeredRoutes);
        } catch {
          // ignore
        }
      },
    );
  }

  ctx.effect(() => () => {
    disposed = true;
    service.dispose();
    releaseDiscovery();
    releaseAdaptersListener?.();
    adapterHandle?.();
    autoAdapterHandle?.();
    directory();
  });

  const started = service.start().catch((error: unknown) => ctx.logger.warn("dsh-freemodel: start failed", error));
  (ctx as unknown as { inject(deps: string[], fn: (inner: Context) => void): unknown }).inject(["credentials"], (inner) => {
    credentials = (inner as unknown as { credentials: CredentialService }).credentials;
    void started.then(() => service.recheck());
    inner.effect(() => () => {
      credentials = undefined;
      void service.recheck();
    });
  });
}
