import manifest from "../package.json" with { type: "json" };

/** This plugin's own version (independent of the Python package). */
export const PLUGIN_VERSION: string = manifest.version;
/** The dsh runtime range this build declares in `engines.dsh`. */
export const DSH_RANGE: string = manifest.engines.dsh;
/** The Node.js range this build declares in `engines.node`. */
export const NODE_RANGE: string = manifest.engines.node;
