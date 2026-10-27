#!/usr/bin/env node
/**
 * `dsh-freemodel status|doctor [--json]`: diagnostics that run without the
 * dsh host, e.g. `dsh plugin --profile <name> exec dsh-freemodel doctor`.
 * Output never contains a key value.
 */
import { execFileSync } from "node:child_process";
import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defaultProviders } from "./channels.ts";
import { buildStatus, type DoctorReport, describeFromEnv, installedDshVersion, runDoctor, type StatusReport } from "./status.ts";
import { PLUGIN_VERSION } from "./version.ts";

const USAGE = `usage: dsh-freemodel status [--json]
       dsh-freemodel doctor [--json] [--dsh-version <version>]
       dsh-freemodel --version`;

export interface CliIO {
  out: (line: string) => void;
  err: (line: string) => void;
  env: NodeJS.ProcessEnv;
  cwd: string;
  /** Ask the dsh on PATH for its version (default: run `dsh --version`). */
  dshCliVersion?: () => string | undefined;
}

const VERSION_RE = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;

function dshCliVersion(): string | undefined {
  try {
    const out = execFileSync("dsh", ["--version"], {
      encoding: "utf8",
      timeout: 15_000,
      stdio: ["ignore", "pipe", "ignore"],
      shell: process.platform === "win32",
    }).trim();
    return VERSION_RE.test(out) ? out : undefined;
  } catch {
    return undefined;
  }
}

/** Which dsh the doctor checks: --dsh-version, then a dsh package beside cwd, then `dsh --version`. */
function findDsh(flag: string | undefined, io: CliIO): { version: string; source: string } | undefined {
  if (flag !== undefined) return { version: flag, source: "--dsh-version" };
  const installed = installedDshVersion(io.cwd);
  if (installed !== undefined) return { version: installed, source: "installed package" };
  const cli = (io.dshCliVersion ?? dshCliVersion)();
  return cli === undefined ? undefined : { version: cli, source: "`dsh --version`" };
}

function formatStatus(report: StatusReport): string[] {
  const lines = [`dsh-freemodel ${report.version} (spec v${report.specVersion})`];
  for (const c of report.channels) {
    const key = c.key === "unknown" ? "unknown" : c.key.configured ? `configured (${c.key.source ?? "?"})` : "not set";
    const blocked = c.blocked === undefined ? "" : `  [${c.blocked}]`;
    lines.push(`  ${c.id.padEnd(11)} ${c.enabled ? "on " : "off"}  route ${c.route}  key ${c.apiKeyEnv}: ${key}${blocked}`);
  }
  lines.push(`  state file  ${report.statePath}${report.stateExists ? "" : " (not created yet)"}`);
  for (const c of report.channels) {
    const m = c.models;
    if (m.catalogFetchedAt === null && m.listed.length === 0 && m.hidden.length === 0) continue;
    const when = m.catalogFetchedAt === null ? "never" : new Date(m.catalogFetchedAt * 1000).toISOString().slice(0, 16).replace("T", " ") + " UTC";
    lines.push(`  ${c.id}: catalogue read ${when}, ${m.candidates} candidates, ${m.listed.length} listed, probes today ${m.probesToday}`);
    if (m.catalogError !== null) lines.push(`    catalogue error: ${m.catalogError}`);
    for (const l of m.listed) lines.push(`    + ${l.id}${l.ttftMs === null ? "" : `  (TTFT ${Math.round(l.ttftMs)} ms)`}`);
    for (const h of m.hidden) lines.push(`    - ${h.id}  ${h.reason}`);
    if (m.lastRound?.stopReason) lines.push(`    last round stopped: ${m.lastRound.stopReason}`);
  }
  return lines;
}

function formatDoctor(report: DoctorReport): string[] {
  return [
    ...report.checks.map((c) => `${c.level === "ok" ? "ok  " : c.level === "warn" ? "warn" : "FAIL"}  ${c.message}`),
    report.ok ? "doctor: no blocking problems" : "doctor: problems found",
  ];
}

/**
 * Run the CLI.
 * @returns the process exit code.
 */
export async function main(argv: string[], io: CliIO): Promise<number> {
  const json = argv.includes("--json");
  let args = argv.filter((a) => a !== "--json");
  let dshFlag: string | undefined;
  const at = args.indexOf("--dsh-version");
  if (at >= 0) {
    dshFlag = args[at + 1];
    if (args[0] !== "doctor" || dshFlag === undefined || !VERSION_RE.test(dshFlag)) {
      io.err(USAGE);
      return 2;
    }
    args = [...args.slice(0, at), ...args.slice(at + 2)];
  }
  const [command, ...rest] = args;
  if (command === "--version" || command === "-V") {
    io.out(PLUGIN_VERSION);
    return 0;
  }
  if (command === "--help" || command === "-h") {
    io.out(USAGE);
    return 0;
  }
  if (rest.length > 0 || (command !== "status" && command !== "doctor")) {
    io.err(USAGE);
    return 2;
  }
  if (command === "status") {
    // Outside the host only the defaults and the process environment are visible.
    const report = await buildStatus({ providers: defaultProviders() }, describeFromEnv(io.env), io.env);
    for (const line of json ? [JSON.stringify(report, null, 2)] : formatStatus(report)) io.out(line);
    return 0;
  }
  const dsh = findDsh(dshFlag, io);
  const report = await runDoctor({ env: io.env, dshVersion: dsh?.version, dshSource: dsh?.source });
  for (const line of json ? [JSON.stringify(report, null, 2)] : formatDoctor(report)) io.out(line);
  return report.ok ? 0 : 1;
}

function isEntryPoint(): boolean {
  const entry = process.argv[1];
  if (entry === undefined) return false;
  try {
    return realpathSync(entry) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return false;
  }
}

if (isEntryPoint()) {
  const code = await main(process.argv.slice(2), {
    out: (line) => process.stdout.write(`${line}\n`),
    err: (line) => process.stderr.write(`${line}\n`),
    env: process.env,
    cwd: process.cwd(),
  });
  process.exitCode = code;
}
