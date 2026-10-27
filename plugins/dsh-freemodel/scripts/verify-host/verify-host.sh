#!/usr/bin/env bash
# Load dsh-freemodel into a real dsh host inside a THROWAWAY home and check
# what the settings page and the credential store see. Never touches
# ~/.dsh, any existing profile, or any default model. Makes no model call
# unless FMS_VERIFY_LIVE=1 (see below).
#
#   usage: scripts/verify-host/verify-host.sh [path/to/dsh]   (default: dsh on PATH)
#
# Live mode: FMS_VERIFY_LIVE=1 with OPENROUTER_API_KEY set passes that key
# (and only it) into the throwaway host. The plugin then reads the public
# catalogue, probes at most FMS_VERIFY_PROBES (default 2) free models, and the
# probe sends one short chat request through the freemodel-openrouter route.
#
# Result: $WORK/home/fm-verify-report.json, plus the composed config and host
# output under $WORK. See docs/dsh-plugin-verification.md.
set -euo pipefail

DSH="${1:-dsh}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$HERE/../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/fm-verify.XXXXXX")"
echo "work dir: $WORK"

(cd "$PLUGIN" && pnpm -s run build >/dev/null && pnpm pack --pack-destination "$WORK" >/dev/null)
TARBALL="$(ls "$WORK"/dsh-freemodel-*.tgz)"
mkdir -p "$WORK/home" "$WORK/fakehome" "$WORK/cwd"

# Clean environment: no API keys, no telemetry, a fake HOME and an empty cwd
# (dsh also reads <cwd>/.env and $DSH_HOME/.env as credential fallbacks).
# COREPACK_HOME (when set) keeps the machine's corepack cache, so the pnpm
# that dsh drives is not downloaded again into the fake HOME.
LIVE_ENV=()
if [ "${FMS_VERIFY_LIVE:-}" = "1" ]; then
  [ -n "${OPENROUTER_API_KEY:-}" ] || { echo "FMS_VERIFY_LIVE=1 needs OPENROUTER_API_KEY"; exit 2; }
  LIVE_ENV=(FMS_VERIFY_LIVE=1 OPENROUTER_API_KEY="$OPENROUTER_API_KEY")
fi
run() {
  env -i PATH="$PATH" HOME="$WORK/fakehome" DSH_HOME="$WORK/home" ${COREPACK_HOME:+COREPACK_HOME="$COREPACK_HOME"} "${LIVE_ENV[@]}" \
    DSH_TELEMETRY_DISABLED=1 DSH_TELEMETRY_MODE=DISABLED OTEL_SDK_DISABLED=true \
    DSH_TELEMETRY_OTLP_URL=http://127.0.0.1:9/disabled DSH_PRODUCT_ANALYTICS_OTLP_URL=http://127.0.0.1:9/disabled \
    npm_config_store_dir="$WORK/pnpm-store" \
    bash -c 'cd "$0" && exec "$@"' "$WORK/cwd" "$@"
}

run "$DSH" --version | tee "$WORK/dsh-version.txt"
run "$DSH" plugin --profile fm-dev add "$TARBALL" "$HERE/probe" >"$WORK/install.log" 2>&1 \
  || { tail -20 "$WORK/install.log"; exit 1; }
if [ "${FMS_VERIFY_LIVE:-}" = "1" ]; then
  # Keep the live run small: at most N probes in the round.
  cat >"$WORK/home/profiles/fm-dev/cordis.patch.yml" <<YAML
- id: dsh-freemodel
  name: dsh-freemodel
  config:
    refresh:
      probeTopN: ${FMS_VERIFY_PROBES:-2}
YAML
fi
run "$DSH" --profile fm-dev --dump-config >"$WORK/composed.yml"
grep -n -A2 "dsh-freemodel" "$WORK/composed.yml" || { echo "dsh-freemodel missing from the composed profile"; exit 1; }
run "$DSH" plugin --profile fm-dev exec dsh-freemodel doctor >"$WORK/doctor.txt" 2>&1 || true
set +e
run timeout 240 "$DSH" --profile fm-dev >"$WORK/host.log" 2>&1
echo "host exit: $?"
set -e
cat "$WORK/home/fm-verify-report.json"
node -e 'process.exit(JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).ok?0:1)' "$WORK/home/fm-verify-report.json"
