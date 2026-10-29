/**
 * The `/freemodel` slash command: `status`, `refresh`, and
 * `test <channel> <model>`. It is the interactive counterpart of the
 * `dsh-freemodel status|doctor` CLI and reads the same state; output never
 * contains a key.
 */
import { ManualTestError, type ManualTestOutcome } from "./service.ts";
import { CHANNEL_IDS, type ChannelId } from "./spec.ts";
import type { StatusReport } from "./status.ts";

/** The part of a command invocation this handler needs. */
export interface CommandInvocationLike {
  readonly rawInput: string;
  readonly signal?: AbortSignal;
}

export type CommandResultLike = { readonly kind: "success"; readonly text?: string } | { readonly kind: "error"; readonly text: string };

/** What the command needs from the running plugin. */
export interface FreemodelCommandDeps {
  status: () => Promise<StatusReport>;
  refresh: () => Promise<void>;
  testModel: (channel: ChannelId, model: string) => Promise<ManualTestOutcome>;
}

export interface FreemodelCommand {
  readonly name: "freemodel";
  readonly description: string;
  readonly input: { readonly hint: string };
  handler: (invocation: CommandInvocationLike) => Promise<CommandResultLike>;
}

export const USAGE = "usage: /freemodel status | refresh | test <channel> <model>";

function keyText(report: StatusReport["channels"][number]): string {
  if (report.key === "unknown") return "unknown";
  return report.key.configured ? `configured${report.key.source === undefined ? "" : ` (${report.key.source})`}` : "not set";
}

/** A compact version of the CLI's `status` output. */
export function formatStatus(report: StatusReport): string {
  const lines = [`dsh-freemodel ${report.version} (spec v${report.specVersion})`];
  for (const channel of report.channels) {
    lines.push(`${channel.id.padEnd(10)} ${channel.enabled ? "on " : "off"}  route ${channel.route}  key ${channel.apiKeyEnv}: ${keyText(channel)}`);
    if (channel.blocked !== undefined) lines.push(`  blocked: ${channel.blocked}`);
    const models = channel.models;
    const when =
      models.catalogFetchedAt === null
        ? "never"
        : `${new Date(models.catalogFetchedAt * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC`;
    lines.push(
      `  catalogue ${when}, ${models.candidates} candidates, ${models.listed.length} listed, ${models.probesToday} probe(s) today`,
    );
    if (models.catalogError !== null) lines.push(`  catalogue error: ${models.catalogError}`);
    for (const model of models.listed) {
      lines.push(`  + ${model.id}${model.ttftMs === null ? "" : `  (TTFT ${Math.round(model.ttftMs)} ms)`}`);
    }
    for (const model of models.hidden) lines.push(`  - ${model.id}  ${model.reason}`);
    if (models.lastRound?.stopReason) lines.push(`  last round stopped: ${models.lastRound.stopReason}`);
  }
  lines.push(`state: ${report.statePath}${report.stateExists ? "" : " (not created yet)"}`);
  return lines.join("\n");
}

function summary(report: StatusReport): string {
  return report.channels
    .map((channel) => {
      if (!channel.enabled) return `${channel.id}: off`;
      if (channel.blocked !== undefined) return `${channel.id}: ${channel.blocked}`;
      return `${channel.id}: ${channel.models.listed.length} listed, ${channel.models.hidden.length} hidden`;
    })
    .join("; ");
}

function testText(outcome: ManualTestOutcome): string {
  const { channel, model, result } = outcome;
  if (result.ok) {
    const ttft = result.ttftMs === null ? "" : `, TTFT ${Math.round(result.ttftMs)} ms`;
    return `test ${channel}/${model.id}: ok${ttft}`;
  }
  const status = result.statusCode === null ? "" : ` (HTTP ${result.statusCode})`;
  const kind = result.failureKind === null ? "" : ` [${result.failureKind}]`;
  return `test ${channel}/${model.id}: failed${status}${kind}: ${result.error ?? "unknown error"}`;
}

/**
 * Build the `/freemodel` command definition.
 * @param deps - status/refresh/test callbacks from the service.
 */
export function createFreemodelCommand(deps: FreemodelCommandDeps): FreemodelCommand {
  return {
    name: "freemodel",
    description: "Show free-model status, refresh catalogues/probes, or test one model.",
    input: { hint: "status | refresh | test <channel> <model>" },
    async handler(invocation) {
      const input = invocation.rawInput.trim();
      const [verb = "", ...rest] = input === "" ? [] : input.split(/\s+/);
      try {
        if (verb === "" || verb === "status") {
          if (rest.length > 0) return { kind: "error", text: `status takes no arguments. ${USAGE}` };
          return { kind: "success", text: formatStatus(await deps.status()) };
        }
        if (verb === "refresh") {
          if (rest.length > 0) return { kind: "error", text: `refresh takes no arguments. ${USAGE}` };
          await deps.refresh();
          return { kind: "success", text: `refresh complete — ${summary(await deps.status())}` };
        }
        if (verb === "test") {
          const [channel, model, ...extra] = rest;
          if (extra.length > 0 || channel === undefined || model === undefined) {
            return { kind: "error", text: `test needs exactly a channel and a model id. ${USAGE}` };
          }
          if (!(CHANNEL_IDS as readonly string[]).includes(channel)) {
            return { kind: "error", text: `unknown channel ${channel}; use one of: ${CHANNEL_IDS.join(", ")}` };
          }
          return { kind: "success", text: testText(await deps.testModel(channel as ChannelId, model)) };
        }
        return { kind: "error", text: `unknown subcommand ${verb}. ${USAGE}` };
      } catch (error) {
        const code = error instanceof ManualTestError ? `${error.code}: ` : "";
        return { kind: "error", text: `${verb === "" ? "freemodel" : verb} failed — ${code}${error instanceof Error ? error.message : String(error)}` };
      }
    },
  };
}