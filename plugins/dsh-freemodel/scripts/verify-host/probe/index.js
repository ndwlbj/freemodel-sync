// Verification probe for dsh-freemodel (see ../verify-host.sh and
// docs/dsh-plugin-verification.md). It runs inside a throwaway DSH_HOME:
//  1. reads the settings service the way the web settings page does
//     (describe({ redactSecrets: true })) and finds the dsh-freemodel form;
//  2. edits a credential-ref field through the same service;
//  3. saves a FAKE key through the credential service, checks it is
//     reported as configured and where it was stored, then removes it;
//  4. writes a JSON report (no key value in it) and stops the host.
import { randomBytes } from "node:crypto";
import { readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export const name = "dsh-freemodel-verify-probe";
export const inject = ["settings", "credentials"];

const NS = "dsh-freemodel";
const REF = "FMS_VERIFY_OPENROUTER_KEY";

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
    writeFileSync(join(home, "fm-verify-report.json"), `${JSON.stringify(report, null, 2)}\n`);
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
    } catch (error) {
      step("exception", false, { error: String(error?.stack ?? error) });
    }
    finish();
  }, 1500);
}
