// Verification probe for dsh-freemodel (see ../verify-host.sh and
// docs/dsh-plugin-verification.md). It runs inside a throwaway DSH_HOME:
//  1. reads the settings service the way the web settings page does
//     (describe({ redactSecrets: true })) and finds the dsh-freemodel form;
//  2. edits a credential-ref field through the same service;
//  3. saves a FAKE key through the credential service, checks it is
//     reported as configured and where it was stored, then removes it;
//  4. checks the model registry: both freemodel-* routes are in the
//     configurable-provider directory, and a route is registered only for a
//     channel with a key (OpenRouter) and never for Groq before
//     freePlanConfirmed;
//  5. live mode only (FMS_VERIFY_LIVE=1 with a real free key in the host's
//     environment): waits for the first probe round, lists the route's models
//     and sends ONE short chat request to the top listed free model;
//  6. writes a JSON report (no key value in it) and stops the host.
import { randomBytes } from "node:crypto";
import { readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export const name = "dsh-freemodel-verify-probe";
export const inject = ["settings", "credentials", "llm"];

const NS = "dsh-freemodel";
const REF = "FMS_VERIFY_OPENROUTER_KEY";
const LIVE = process.env.FMS_VERIFY_LIVE === "1";
const ROUTES = ["freemodel-openrouter", "freemodel-groq"];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function readState(home) {
  try {
    return JSON.parse(readFileSync(join(home, "freemodel", "state.json"), "utf8"));
  } catch {
    return null;
  }
}

async function registry(ctx) {
  const llm = ctx.llm;
  const directory = llm.listConfigurableProviders().filter((p) => ROUTES.includes(p.provider));
  const registered = llm.listProviders().map((p) => p.provider ?? p.id).filter((p) => ROUTES.includes(p));
  return { directory, registered };
}

function find(settings) {
  return settings.describe({ redactSecrets: true }).find((d) => d.ns === NS);
}

function fieldsOf(schema, path = []) {
  // Flatten a serialized schemastery form into [path, type, role] rows.
  const rows = [];
  const node = schema.refs ? schema.refs[schema.uid] : schema;
  const walk = (n, p) => {
    const resolved = typeof n === "number" ? schema.refs[n] : n;
    if (resolved === undefined) return;
    if (resolved.type === "object") {
      for (const [k, child] of Object.entries(resolved.dict ?? {})) walk(child, [...p, k]);
    } else {
      rows.push({ path: p.join("."), type: resolved.type, role: resolved.meta?.role ?? null, default: resolved.meta?.default });
    }
  };
  walk(node, path);
  return rows;
}

export function apply(ctx) {
  const home = process.env.DSH_HOME;
  const report = { ok: false, steps: [] };
  const step = (id, ok, detail) => report.steps.push({ id, ok, ...detail });
  const finish = () => {
    report.ok = report.steps.length > 0 && report.steps.every((s) => s.ok);
    let text = `${JSON.stringify(report, null, 2)}\n`;
    // A real key must never reach the report; if one did, keep only the verdict.
    const leaked = ["OPENROUTER_API_KEY", "GROQ_API_KEY"].filter((n) => process.env[n] && text.includes(process.env[n]));
    if (leaked.length > 0) text = `${JSON.stringify({ ok: false, leaked, steps: report.steps.map((s) => ({ id: s.id })) })}\n`;
    writeFileSync(join(home, "fm-verify-report.json"), text);
    process.kill(process.pid, "SIGTERM");
  };
  setTimeout(async () => {
    try {
      const settings = ctx.settings;
      const credentials = ctx.credentials;
      const before = find(settings);
      step("settings-form", before !== undefined, {
        namespaces: settings.describe({ redactSecrets: true }).map((d) => d.ns).filter((ns) => ns === NS || ns === "fm-verify-probe"),
        applies: before?.applies,
        fields: before === undefined ? [] : fieldsOf(before.schema),
        value: before?.value,
        secrets: before?.secrets,
      });
      if (before === undefined) return finish();

      const updated = await settings.update(NS, { providers: { openrouter: { apiKeyEnv: REF } } }, before.revision);
      const after = find(settings);
      step("settings-edit-credential-ref", after?.value?.providers?.openrouter?.apiKeyEnv === REF, {
        revisionBefore: before.revision,
        revisionAfter: after?.revision,
        valueAfter: after?.value,
        returned: updated === undefined ? null : typeof updated,
      });

      const unset = await credentials.describe(REF);
      const fake = `fms-verify-fake-${randomBytes(12).toString("hex")}`;
      await credentials.set(REF, fake);
      const set = await credentials.describe(REF);
      const resolved = await credentials.resolve(REF);
      const file = join(home, ".credentials.yaml");
      let fileInfo = { exists: false };
      try {
        const text = readFileSync(file, "utf8");
        fileInfo = {
          exists: true,
          mode: (statSync(file).mode & 0o777).toString(8),
          mentionsRef: text.includes(REF),
          holdsFakeValue: text.includes(fake),
        };
      } catch {
        // stays { exists: false }
      }
      const pluginCfg = find(settings);
      step("credential-ref-save", unset.configured === false && set.configured === true && resolved?.value === fake, {
        describeBefore: unset,
        describeAfter: set,
        resolvedSource: resolved?.source,
        resolvedMatches: resolved?.value === fake,
        storeFile: fileInfo,
        settingsSecretsAfter: pluginCfg?.secrets,
        settingsValueLeaksKey: JSON.stringify(pluginCfg ?? {}).includes(fake),
      });
      await credentials.unset(REF);
      const removed = await credentials.describe(REF);
      step("credential-ref-remove", removed.configured === false, { describeAfterUnset: removed });
      // Put the plugin's own reference back for the registry checks.
      await settings.update(NS, { providers: { openrouter: { apiKeyEnv: "OPENROUTER_API_KEY" } } }, find(settings).revision);

      const orKey = await credentials.describe("OPENROUTER_API_KEY");
      const groqKey = await credentials.describe("GROQ_API_KEY");
      let reg = await registry(ctx);
      for (let i = 0; i < 20 && orKey.configured && !reg.registered.includes("freemodel-openrouter"); i++) {
        await sleep(500);
        reg = await registry(ctx);
      }
      step(
        "llm-routes",
        reg.directory.map((d) => d.provider).join() === ROUTES.join() &&
          reg.registered.includes("freemodel-openrouter") === orKey.configured &&
          !reg.registered.includes("freemodel-groq"),
        {
          openrouterKeyConfigured: orKey.configured,
          openrouterKeySource: orKey.source,
          groqKeyConfigured: groqKey.configured,
          directory: reg.directory.map((d) => ({ provider: d.provider, settingsNs: d.settingsNs, settingsPath: d.settingsPath, error: d.error })),
          registered: reg.registered,
        },
      );

      if (LIVE && orKey.configured) {
        let state = readState(home);
        for (let i = 0; i < 120 && !state?.channels?.openrouter?.lastRound; i++) {
          await sleep(1000);
          state = readState(home);
        }
        const channel = state?.channels?.openrouter;
        const routes = (await registry(ctx)).registered;
        const models = routes.includes("freemodel-openrouter") ? await ctx.llm.listModels("freemodel-openrouter") : [];
        const probes = Object.values(channel?.results ?? {}).map((r) => ({
          key: r.key,
          ok: r.ok,
          ttftMs: r.ttftMs === null ? null : Math.round(r.ttftMs),
          failureKind: r.failureKind,
          statusCode: r.statusCode,
          error: r.error,
        }));
        step("live-listing", models.length > 0 && models.every((m) => m.name.endsWith(" · 免费")), {
          catalogModels: channel?.catalog?.models?.length ?? 0,
          catalogError: channel?.catalog?.error ?? null,
          lastRound: channel?.lastRound ?? null,
          probesToday: channel?.daily ?? null,
          probes,
          listed: models.map((m) => ({ id: m.id, name: m.name, description: m.description })),
        });
        if (models.length > 0) {
          const target = models[0];
          let text = "";
          let reasoning = 0;
          let finish = null;
          const started = Date.now();
          for await (const chunk of ctx.llm.stream({
            provider: "freemodel-openrouter",
            model: target.id,
            messages: [{ role: "user", content: [{ type: "text", text: "Reply with the single word OK." }] }],
            maxTokens: 256,
          })) {
            if (chunk.type === "text-delta") text += chunk.text;
            if (chunk.type === "reasoning-delta") reasoning += chunk.text.length;
            if (chunk.type === "finish") finish = chunk;
          }
          const kind = finish?.reason?.kind ?? finish?.reason ?? null;
          step("live-chat", text.length + reasoning > 0 && kind !== "error" && kind !== "aborted", {
            model: target.id,
            ms: Date.now() - started,
            reply: text.slice(0, 80),
            reasoningChars: reasoning,
            finish: kind,
          });
        }
      }
    } catch (error) {
      step("exception", false, { error: String(error?.stack ?? error) });
    }
    finish();
  }, 1500);
}
