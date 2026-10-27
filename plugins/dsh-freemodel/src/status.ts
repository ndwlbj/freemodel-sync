/**
 * Status and doctor reports, shared by the plugin and the `dsh-freemodel`
 * CLI. Reports never contain a key: they say whether a key reference is
 * configured and from which layer, nothing more.
 */
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { join } from "node:path";
import { type ChannelState, channelStates, defaultProviders, type FreemodelConfig } from "./channels.ts";
import { satisfies } from "./semver.ts";
import { providersSpec, SUPPORTED_SPEC_VERSION } from "./spec.ts";
import { DSH_RANGE, NODE_RANGE, PLUGIN_VERSION } from "./version.ts";

/** Report format version for `--json` consumers. */
export const STATUS_SCHEMA_VERSION = 1;

/** Presence facts for one key reference, as dsh's credential service describes them. */
export interface KeyPresence {
  configured: boolean;
  /** Layer supplying the value (`file`, `env`, `project-env`, `user-env`). */
  source?: string;
}

/** Look up a key reference without reading its value. */
export type DescribeKey = (ref: string) => Promise<KeyPresence>;

export interface ChannelReport extends ChannelState {
  key: KeyPresence | "unknown";
}

export interface StatusReport {
  schemaVersion: number;
  plugin: string;
  version: string;
  specVersion: number;
  statePath: string;
  stateExists: boolean;
  channels: ChannelReport[];
  /** P3: no routes are registered yet. */
  routesRegistered: string[];
}

/** `$DSH_HOME`, else `~/.dsh`, as dsh itself resolves it. */
export function dshHome(env: NodeJS.ProcessEnv = process.env): string {
  const configured = env.DSH_HOME;
  return configured !== undefined && configured !== "" ? configured : join(homedir(), ".dsh");
}

/** Where the plugin will keep its cache (plan 6.3; written from P4 on). */
export function statePath(env: NodeJS.ProcessEnv = process.env): string {
  return join(dshHome(env), "freemodel", "state.json");
}

/** A {@link DescribeKey} that only checks the process environment (for the CLI outside dsh). */
export function describeFromEnv(env: NodeJS.ProcessEnv = process.env): DescribeKey {
  return async (ref) => {
    const value = env[ref];
    return value !== undefined && value !== "" ? { configured: true, source: "env" } : { configured: false };
  };
}

/**
 * Build the status report.
 * @param config - validated plugin configuration.
 * @param describe - key lookup; omitted when no credential service is available.
 * @param env - environment for the state path.
 */
export async function buildStatus(
  config: FreemodelConfig,
  describe?: DescribeKey,
  env: NodeJS.ProcessEnv = process.env,
): Promise<StatusReport> {
  const channels: ChannelReport[] = [];
  for (const state of channelStates(config)) {
    let key: ChannelReport["key"] = "unknown";
    if (describe !== undefined) {
      try {
        const info = await describe(state.apiKeyEnv);
        key = info.source === undefined ? { configured: info.configured } : { configured: info.configured, source: info.source };
      } catch {
        key = "unknown";
      }
    }
    channels.push({ ...state, key });
  }
  const path = statePath(env);
  return {
    schemaVersion: STATUS_SCHEMA_VERSION,
    plugin: "dsh-freemodel",
    version: PLUGIN_VERSION,
    specVersion: providersSpec.spec_version,
    statePath: path,
    stateExists: existsSync(path),
    channels,
    routesRegistered: [],
  };
}

export type CheckLevel = "ok" | "warn" | "fail";

export interface DoctorCheck {
  id: string;
  level: CheckLevel;
  message: string;
}

export interface DoctorReport {
  schemaVersion: number;
  ok: boolean;
  checks: DoctorCheck[];
}

/**
 * Version of an installed dsh runtime package, resolved from a directory
 * (the profile directory when run through `dsh plugin --profile <p> exec`).
 */
export function installedDshVersion(fromDir: string): string | undefined {
  const require = createRequire(join(fromDir, "noop.js"));
  for (const pkg of ["@deepseek-ai/dsh-app-boot", "@deepseek-ai/dsh-llm", "@deepseek-ai/dsh"]) {
    try {
      const manifest = require(`${pkg}/package.json`) as { version?: unknown };
      if (typeof manifest.version === "string") return manifest.version;
    } catch {
      // not resolvable from here; try the next one
    }
  }
  return undefined;
}

export interface DoctorOptions {
  nodeVersion?: string;
  dshVersion?: string | undefined;
  /** Where dshVersion came from, shown in the message. */
  dshSource?: string | undefined;
  env?: NodeJS.ProcessEnv;
}

/**
 * Run the doctor checks. Nothing here talks to the network or reads a key.
 */
export async function runDoctor(options: DoctorOptions = {}): Promise<DoctorReport> {
  const env = options.env ?? process.env;
  const nodeVersion = options.nodeVersion ?? process.versions.node;
  const checks: DoctorCheck[] = [];
  checks.push(
    satisfies(nodeVersion, NODE_RANGE)
      ? { id: "node", level: "ok", message: `Node.js ${nodeVersion} satisfies ${NODE_RANGE}` }
      : { id: "node", level: "fail", message: `Node.js ${nodeVersion} does not satisfy ${NODE_RANGE}` },
  );
  const dsh = options.dshVersion;
  if (dsh === undefined) {
    checks.push({
      id: "dsh",
      level: "warn",
      message: `dsh version unknown (no dsh package here and no \`dsh\` on PATH); pass --dsh-version to check it against ${DSH_RANGE}`,
    });
  } else {
    checks.push(
      satisfies(dsh, DSH_RANGE)
        ? {
            id: "dsh",
            level: "ok",
            message: `dsh ${dsh}${options.dshSource === undefined ? "" : ` (${options.dshSource})`} satisfies engines.dsh ${DSH_RANGE}`,
          }
        : {
            id: "dsh",
            level: "fail",
            message: `dsh ${dsh} is outside engines.dsh ${DSH_RANGE}; dsh will refuse to load this plugin`,
          },
    );
  }
  checks.push({
    id: "spec",
    level: providersSpec.spec_version === SUPPORTED_SPEC_VERSION ? "ok" : "fail",
    message: `bundled spec_version ${providersSpec.spec_version} (supported: ${SUPPORTED_SPEC_VERSION})`,
  });
  const status = await buildStatus({ providers: defaultProviders() }, describeFromEnv(env), env);
  for (const channel of status.channels) {
    const key = channel.key === "unknown" ? undefined : channel.key;
    checks.push({
      id: `key:${channel.id}`,
      level: key?.configured === true || !channel.enabled ? "ok" : "warn",
      message:
        key?.configured === true
          ? `${channel.apiKeyEnv} is set in this environment`
          : `${channel.apiKeyEnv} is not set in this environment (a key saved in dsh's settings page is not visible to this command)`,
    });
  }
  return { schemaVersion: STATUS_SCHEMA_VERSION, ok: checks.every((c) => c.level !== "fail"), checks };
}
