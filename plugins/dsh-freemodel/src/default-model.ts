/**
 * Opt-in switch of current-profile default model (plan 6.3 / P10).
 *
 * SAFETY RULES & GUARDS:
 * 1. Default model switch is OFF by default.
 * 2. Only the current profile's patch is ever modified; never other profiles.
 * 3. Never QQ/bot profiles (QQ_PROFILE_DENY rejects matching names).
 * 4. Never touches $DSH_HOME/cordis.patch.yml (the home layer).
 * 5. Writes ONLY when deps.writePatch is provided AND env DSH_FREEMODEL_APPLY_DEFAULT=1 is set;
 *    otherwise applyDefaultModelSwitch returns action "would-write" and logs via injected logger.
 *    Never silently writes to disk without explicit environment authorization.
 */
import { resolve } from "node:path";
import { AUTO_MODEL_ID, AUTO_ROUTE } from "./auto-route.ts";

/** Match profiles dedicated to QQ or chat bots that must never be altered. */
export const QQ_PROFILE_DENY = /qq|bot|astrbot|napcat|onebot/i;

/** Throw if the profile name matches the QQ/bot profile deny list. */
export function assertSafeProfile(profileId: string): void {
  if (QQ_PROFILE_DENY.test(profileId)) {
    throw new Error(`Profile ${JSON.stringify(profileId)} is a QQ/bot profile; modifying default model is denied.`);
  }
}

export interface ResolvedProfile {
  name: string;
  dir?: string | undefined;
}

export type ProfileGetter =
  | ((key: string) => unknown)
  | { get?: (key: string) => unknown }
  | null
  | undefined;

/**
 * Resolve current profile identity from a Cordis context (or getter function) with env fallback.
 * Checks ctx.get("profileContext") for { name, dir? }, then falls back to DSH_PROFILE (name only).
 * Never throws.
 */
export function resolveProfile(
  getter?: ProfileGetter,
  env: Record<string, string | undefined> = process.env,
): ResolvedProfile | undefined {
  if (getter) {
    try {
      const fn = typeof getter === "function" ? getter : typeof getter.get === "function" ? getter.get.bind(getter) : undefined;
      if (fn) {
        const val = fn("profileContext") as unknown;
        if (val && typeof val === "object" && "name" in val && typeof (val as { name: unknown }).name === "string") {
          const profile = val as { name: string; dir?: unknown };
          const name = profile.name.trim();
          if (name.length > 0) {
            const dir =
              typeof profile.dir === "string" && profile.dir.trim().length > 0
                ? profile.dir.trim()
                : undefined;
            return dir !== undefined ? { name, dir } : { name };
          }
        }
      }
    } catch {
      // Never throw (ctx.get may throw or return undefined)
    }
  }

  const envProfile = env?.DSH_PROFILE;
  if (typeof envProfile === "string") {
    const name = envProfile.trim();
    if (name.length > 0) {
      return { name };
    }
  }

  return undefined;
}

export interface DefaultModelPlan {
  profileId?: string | undefined;
  entryId: "agent-default-model";
  provider?: string | undefined;
  model?: string | undefined;
  action: "would-write" | "skipped" | "applied";
  reason?: string | undefined;
}

export interface PlanOptions {
  enabled: boolean;
  profileId: string | undefined;
  autoRouteEnabled: boolean;
  top?: { route: string; modelId: string } | null;
}

/**
 * Compute the default-model switch plan based on settings and available models.
 * Does not throw for denied profiles at plan time (records reason and action: "skipped").
 */
export function planDefaultModelSwitch(opts: PlanOptions): DefaultModelPlan {
  if (!opts.enabled) {
    return {
      entryId: "agent-default-model",
      profileId: opts.profileId,
      action: "skipped",
      reason: "autoDefaultModel is off",
    };
  }
  if (!opts.profileId || opts.profileId.trim() === "") {
    return {
      entryId: "agent-default-model",
      profileId: undefined,
      action: "skipped",
      reason: "no current profile",
    };
  }
  if (QQ_PROFILE_DENY.test(opts.profileId)) {
    return {
      entryId: "agent-default-model",
      profileId: opts.profileId,
      action: "skipped",
      reason: `profile ${opts.profileId} is a QQ/bot profile; autoDefaultModel is denied`,
    };
  }

  let provider: string;
  let model: string;
  if (opts.autoRouteEnabled) {
    provider = AUTO_ROUTE;
    model = AUTO_MODEL_ID;
  } else if (opts.top) {
    provider = opts.top.route;
    model = opts.top.modelId;
  } else {
    return {
      entryId: "agent-default-model",
      profileId: opts.profileId,
      action: "skipped",
      reason: "no listed model",
    };
  }

  return {
    entryId: "agent-default-model",
    profileId: opts.profileId,
    provider,
    model,
    action: "would-write",
  };
}

/** Update or append the agent-default-model entry in a cordis.patch.yml text. */
export function updateDefaultModelPatch(
  text: string,
  entry: { entryId?: string; provider: string; model: string; entryName?: string },
): string {
  const entryId = entry.entryId ?? "agent-default-model";
  const entryName = entry.entryName ?? "@deepseek-ai/dsh-agent-default-model";
  const safeModel = entry.model.includes("'") ? `"${entry.model}"` : `'${entry.model}'`;
  const renderedConfig = `{provider: ${entry.provider}, model: ${safeModel}}`;

  if (!text || text.trim() === "") {
    return `- id: ${entryId}\n  name: '${entryName}'\n  config: ${renderedConfig}\n`;
  }

  const idPattern = new RegExp(`(^|\\n)( *- +id: +['"]?${entryId}['"]?.*?)(?=(\\n *- +id:|\\n*$))`, "s");
  const match = idPattern.exec(text);

  const prefix = match?.[1];
  const existingBlock = match?.[2];
  const fullMatch = match?.[0];

  if (!match || prefix === undefined || existingBlock === undefined || fullMatch === undefined) {
    const trimmed = text.trimEnd();
    return `${trimmed}\n\n- id: ${entryId}\n  name: '${entryName}'\n  config: ${renderedConfig}\n`;
  }

  let updatedBlock: string;

  if (/config:/.test(existingBlock)) {
    if (/config:\s*\{[^}]*\}/.test(existingBlock)) {
      updatedBlock = existingBlock.replace(/config:\s*\{[^}]*\}/, `config: ${renderedConfig}`);
    } else if (/config:\s*\n(\s+[^\n]+\n?)+/.test(existingBlock)) {
      updatedBlock = existingBlock.replace(/config:\s*\n(\s+[^\n]+\n?)+/, `config: ${renderedConfig}\n`);
    } else {
      updatedBlock = existingBlock.replace(/config:.*$/, `config: ${renderedConfig}`);
    }
  } else {
    updatedBlock = `${existingBlock.trimEnd()}\n  config: ${renderedConfig}\n`;
  }

  return text.slice(0, match.index + prefix.length) + updatedBlock + text.slice(match.index + fullMatch.length);
}

export interface DefaultModelLogRecord {
  action: "would-write" | "applied";
  provider?: string | undefined;
  model?: string | undefined;
  path: string;
}

let moduleLastLog: DefaultModelLogRecord | undefined;

/** Reset the module-level last logged default model record (used in testing). */
export function resetLastDefaultModelLog(): void {
  moduleLastLog = undefined;
}

function matchesLastLog(
  last: DefaultModelLogRecord | undefined,
  action: "would-write" | "applied",
  provider: string | undefined,
  model: string | undefined,
  path: string,
): boolean {
  if (!last) return false;
  return (
    last.action === action &&
    last.provider === provider &&
    last.model === model &&
    (last.path === path || resolve(last.path) === resolve(path))
  );
}

function recordLog(
  deps: ApplyDeps,
  action: "would-write" | "applied",
  provider: string | undefined,
  model: string | undefined,
  path: string,
): void {
  const record: DefaultModelLogRecord = { action, provider, model, path };
  if (deps.lastLog) {
    if ("current" in deps.lastLog) {
      deps.lastLog.current = record;
    } else {
      const target = deps.lastLog as DefaultModelLogRecord;
      target.action = action;
      target.provider = provider;
      target.model = model;
      target.path = path;
    }
  }
  moduleLastLog = record;
}

export interface ApplyDeps {
  readPatch(path: string): string;
  writePatch(path: string, text: string): void;
  profilePatchPath: string;
  homePatchPath?: string;
  env?: Record<string, string | undefined>;
  logger?: { info?: (msg: string) => void; warn?: (msg: string, ...args: unknown[]) => void };
  lastLog?: { current?: DefaultModelLogRecord | undefined } | DefaultModelLogRecord;
}

/**
 * Apply the planned default model switch.
 *
 * Enforces safety boundaries:
 * - Refuses denied profiles (throws).
 * - Refuses profilePatchPath equaling home patch or $DSH_HOME/cordis.patch.yml (throws).
 * - Requires DSH_FREEMODEL_APPLY_DEFAULT=1 to actually write to disk; otherwise returns action: "would-write".
 */
export function applyDefaultModelSwitch(plan: DefaultModelPlan, deps: ApplyDeps): DefaultModelPlan {
  if (plan.action === "skipped") {
    return plan;
  }

  if (plan.profileId !== undefined) {
    assertSafeProfile(plan.profileId);
  } else {
    throw new Error("Cannot apply default model switch without a profileId");
  }

  const resolvedProfile = resolve(deps.profilePatchPath);

  if (deps.homePatchPath) {
    const resolvedHome = resolve(deps.homePatchPath);
    if (resolvedProfile === resolvedHome) {
      throw new Error(`Refusing to write default model to home layer patch: ${deps.profilePatchPath}`);
    }
  }

  const env = deps.env ?? process.env;
  const dshHome = env.DSH_HOME;
  if (dshHome && dshHome.trim() !== "") {
    const resolvedDshHomePatch = resolve(dshHome, "cordis.patch.yml");
    if (resolvedProfile === resolvedDshHomePatch) {
      throw new Error(`Refusing to write default model to $DSH_HOME layer patch: ${deps.profilePatchPath}`);
    }
  }

  const lastLogRecord: DefaultModelLogRecord | undefined =
    deps.lastLog && "current" in deps.lastLog
      ? deps.lastLog.current
      : (deps.lastLog as DefaultModelLogRecord | undefined) ?? moduleLastLog;

  if (env.DSH_FREEMODEL_APPLY_DEFAULT !== "1") {
    if (!matchesLastLog(lastLogRecord, "would-write", plan.provider, plan.model, deps.profilePatchPath)) {
      deps.logger?.info?.(
        `dsh-freemodel: autoDefaultModel would write provider=${plan.provider} model=${plan.model} to ${deps.profilePatchPath} (set DSH_FREEMODEL_APPLY_DEFAULT=1 to apply)`,
      );
      recordLog(deps, "would-write", plan.provider, plan.model, deps.profilePatchPath);
    }
    return {
      ...plan,
      action: "would-write",
      reason: "DSH_FREEMODEL_APPLY_DEFAULT=1 is not set",
    };
  }

  let currentText = "";
  try {
    currentText = deps.readPatch(deps.profilePatchPath);
  } catch {
    currentText = "";
  }

  const updatedText = updateDefaultModelPatch(currentText, {
    entryId: plan.entryId,
    provider: plan.provider!,
    model: plan.model!,
  });

  deps.writePatch(deps.profilePatchPath, updatedText);
  if (!matchesLastLog(lastLogRecord, "applied", plan.provider, plan.model, deps.profilePatchPath)) {
    deps.logger?.info?.(
      `dsh-freemodel: updated agent-default-model to provider=${plan.provider} model=${plan.model} in ${deps.profilePatchPath}`,
    );
    recordLog(deps, "applied", plan.provider, plan.model, deps.profilePatchPath);
  }
  return { ...plan, action: "applied" };
}
