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
import { dirname, join } from "node:path";
import { createAdapter, channelOfRoute, displayName } from "./adapter.ts";
import { type FreemodelConfig, routeOf } from "./channels.ts";
import { createFreemodelCommand } from "./command.ts";
import { API_PREFIX, createLocalApiHandler, generateSecret, loadOrCreateSecret } from "./local-api.ts";
import { FreemodelService } from "./service.ts";
import { CHANNEL_IDS, type ChannelId, providerSpec } from "./spec.ts";
import { buildStatus, type DescribeKey, statePath } from "./status.ts";
import { PLUGIN_VERSION } from "./version.ts";

export { channelStates, defaultProviders, defaultRanking, defaultRefresh, providersOf, routeOf } from "./channels.ts";
export type {
  ChannelState,
  FreemodelConfig,
  FreemodelConfigInput,
  Live,
  ProvidersConfig,
  RankingConfig,
  RefreshConfig,
} from "./channels.ts";
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
        if (credentials === undefined) return false;
        return (await credentials.describe(ref)).configured;
      },
      async resolve(ref) {
        return credentials === undefined ? undefined : (await credentials.resolve(ref))?.value;
      },
    },
    onChange: () => sync(),
  });
  const { adapter, invalidate } = createAdapter(service, () => ctx.get("attachments"));

  const describeKey: DescribeKey = async (ref) => {
    if (credentials === undefined) return { configured: false };
    const info = await credentials.describe(ref);
    return info.source === undefined ? { configured: info.configured } : { configured: info.configured, source: info.source };
  };
  const readStatus = () => buildStatus(config, credentials === undefined ? undefined : describeKey);

  let adapterHandle: ReturnType<LlmService["registerAdapter"]> | undefined;
  let lastSummary = "";
  let disposed = false;

  const directoryEntries = () =>
    CHANNEL_IDS.map((id) => {
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
  const directory = llm.registerConfigurableProviders(directoryEntries());

  function sync(): void {
    if (disposed) return;
    invalidate();
    const routes = service.activeRoutes();
    try {
      if (adapterHandle === undefined) {
        if (routes.length > 0) adapterHandle = llm.registerAdapter(routes, adapter);
      } else {
        adapterHandle.replace(routes);
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
  }

  const releaseDiscovery = llm.registerModelDiscovery(settingsNs, async (request, signal) => {
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

  ctx.effect(() => () => {
    disposed = true;
    service.dispose();
    releaseDiscovery();
    adapterHandle?.();
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
