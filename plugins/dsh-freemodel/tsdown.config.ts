import { defineConfig } from "tsdown";

export default defineConfig({
  entry: { index: "src/index.ts", bin: "src/bin.ts" },
  outDir: "lib",
  format: "esm",
  platform: "node",
  target: "node22",
  fixedExtension: false,
  dts: true,
  clean: true,
  // The host provides these; bundling them would give the plugin a second copy.
  deps: { neverBundle: [/^@deepseek-ai\//] },
});
