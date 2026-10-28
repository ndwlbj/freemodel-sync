import { defineConfig } from "tsdown";

/** Host-provided packages: bundling them would give the plugin a second copy. */
const hostPackages = [/^@deepseek-ai\//, /^@earendil-works\//];

const clientBanner = [
  "window.__ModuleLoader__.load({",
  '  id: "dsh-freemodel",',
  "  factory: (require) => {",
  "    var module = { exports: {} };",
  "    var exports = module.exports;",
].join("\n");

const clientFooter = ["return module.exports;", "  }", "});"].join("\n");

export default defineConfig([
  {
    entry: { index: "src/index.ts", bin: "src/bin.ts" },
    outDir: "lib",
    format: "esm",
    platform: "node",
    target: "node22",
    fixedExtension: false,
    dts: true,
    clean: true,
    deps: { neverBundle: hostPackages },
  },
  {
    // The host serves this file as a classic script and reads the CJS factory
    // from window.__ModuleLoader__. React stays external and is required from
    // the host runtime; no React package is added to the plugin.
    entry: { client: "src/client/entry.ts" },
    outDir: "lib",
    format: "cjs",
    platform: "browser",
    target: "es2022",
    fixedExtension: false,
    outExtensions: () => ({ js: ".js" }),
    dts: false,
    clean: false,
    checks: { legacyCjs: false },
    banner: clientBanner,
    footer: clientFooter,
    deps: { neverBundle: [...hostPackages, /^react$/, /^react-dom$/, /^react\/jsx-runtime$/] },
  },
]);
