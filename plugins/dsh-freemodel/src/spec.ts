/**
 * The shared rule files from the repository's `spec/` directory, bundled into
 * the build so the installed plugin needs no Python and no network access to
 * read them. The Python package ships the same files; both sides run the
 * golden cases in `spec/conformance/` (see spec/README.md).
 */
import providersJson from "../../../spec/providers.json" with { type: "json" };
import rankingJson from "../../../spec/ranking.json" with { type: "json" };

/** The only spec_version this build understands. */
export const SUPPORTED_SPEC_VERSION = 1;

/** The channels the plugin knows about, in display order. */
export const CHANNEL_IDS = ["openrouter", "groq"] as const;
export type ChannelId = (typeof CHANNEL_IDS)[number];

export interface ProviderSpec {
  displayName: string;
  baseURL: string;
  modelsPath: string;
  apiKeyEnv: string;
  docs: Record<string, string>;
  [key: string]: unknown;
}

export interface ProvidersSpec {
  spec_version: number;
  providers: Record<ChannelId, ProviderSpec> & Record<string, ProviderSpec>;
  [key: string]: unknown;
}

export interface RankingSpec {
  spec_version: number;
  weights: Record<string, number>;
  [key: string]: unknown;
}

/** Thrown when the bundled spec is not one this build can read. */
export class SpecError extends Error {
  override name = "SpecError";
}

/**
 * Check a spec document's version.
 * @param doc - parsed spec file.
 * @param file - file name for the message.
 * @returns the same document.
 */
export function checkSpecVersion<T extends { spec_version: unknown }>(doc: T, file: string): T {
  if (doc.spec_version !== SUPPORTED_SPEC_VERSION) {
    throw new SpecError(
      `${file} has spec_version ${String(doc.spec_version)}; this build of dsh-freemodel supports ${SUPPORTED_SPEC_VERSION}`,
    );
  }
  return doc;
}

export const providersSpec: ProvidersSpec = checkSpecVersion(providersJson as unknown as ProvidersSpec, "providers.json");
export const rankingSpec: RankingSpec = checkSpecVersion(rankingJson as unknown as RankingSpec, "ranking.json");

/**
 * One channel's spec entry.
 * @param id - channel id.
 * @returns the entry.
 */
export function providerSpec(id: ChannelId): ProviderSpec {
  const entry = providersSpec.providers[id];
  if (entry === undefined) throw new SpecError(`providers.json has no entry for ${id}`);
  return entry;
}
