/**
 * Browser half of dsh-freemodel.
 *
 * It registers one read-only card on the plugin's own page in the settings
 * panel (and on its row, so a deployment that renders either seat shows it).
 * The card reads `/freemodel/api/status` and calls `/freemodel/api/test`; it
 * never renders a key, never edits the plugin configuration and never touches
 * the default model. React comes from the host loader via `entry.ts`.
 */
import { FreemodelApiClient } from "./api.ts";
import { FreemodelCard } from "./card.ts";
import { createTranslator, dictionaries, resolveLocale, type ClientLocale, type Translator } from "./i18n.ts";
import { installStyles } from "./styles.ts";

/** Stable browser-plugin name. */
export const name = "dsh-freemodel-client";

/** The host must declare `slots`; `locale` is optional and read through `ctx.get`. */
export const inject = ["slots"];

const PACKAGE_NAME = "dsh-freemodel";
const BUNDLE_SLOT = "plugins.bundle.config";
const ROW_SLOT = "plugins.row.config";
const LOCALE_NAMESPACE = "dsh-freemodel.client";

interface LocaleSnapshot {
  active?: string;
}

interface LocaleLike {
  getLocale?: () => LocaleSnapshot;
  register?: (namespace: string, dictionaries: { zh: unknown; en: unknown }) => () => void;
}

interface SlotEntryOptions {
  name: string;
  key?: string;
  id?: string;
  order?: number;
  locale?: string;
  inject?: () => Record<string, unknown>;
}

interface SlotsLike {
  inject(name: string, factory: () => unknown): () => void;
  register(options: SlotEntryOptions, component: unknown): () => void;
}

interface ClientContextLike {
  slots: SlotsLike;
  effect(fn: () => void | (() => void), label?: string): unknown;
  get?(name: string): unknown;
  on?(event: string, listener: (snapshot: LocaleSnapshot) => void): (() => void) | void;
}

function localeService(ctx: ClientContextLike): LocaleLike | undefined {
  const service = ctx.get?.("locale");
  return typeof service === "object" && service !== null ? (service as LocaleLike) : undefined;
}

/**
 * Register the card.
 * @param ctx - browser-side Cordis context; `slots` is required.
 */
export function apply(ctx: ClientContextLike): void {
  try {
    const locale = localeService(ctx);
    let active: ClientLocale = resolveLocale(locale?.getLocale?.().active);
    let t: Translator = createTranslator(active);

    ctx.effect(() => {
      try {
        return locale?.register?.(LOCALE_NAMESPACE, { zh: dictionaries.zh, en: dictionaries.en }) ?? (() => {});
      } catch {
        return () => {};
      }
    }, "dsh-freemodel: card copy");

    if (typeof ctx.on === "function") {
      ctx.effect(() => {
        const dispose = ctx.on?.("locale/change", (snapshot) => {
          const next = resolveLocale(snapshot.active);
          if (next === active) return;
          active = next;
          t = createTranslator(active);
        });
        return typeof dispose === "function" ? dispose : () => {};
      }, "dsh-freemodel: card language");
      // `on` may be present without an effect scope in a fake context; the
      // host always has both. Reading the current locale once is enough then.
    }

    ctx.effect(() => installStyles(), "dsh-freemodel: card styles");

    const api = new FreemodelApiClient();
    const injectFace = (): Record<string, unknown> => ({ t, api });

    const register = (slot: string, key: string): (() => void) | undefined => {
      try {
        return ctx.slots.inject(slot, () =>
          ctx.slots.register(
            {
              name: slot,
              key,
              order: 40,
              locale: LOCALE_NAMESPACE,
              inject: injectFace,
            },
            FreemodelCard,
          ),
        );
      } catch (error) {
        // A missing seat or a host slot API change must never take down the
        // model provider (the host side keeps serving).
        console.error(`[dsh-freemodel] card slot "${slot}" failed to register:`, error);
        return undefined;
      }
    };

    register(BUNDLE_SLOT, PACKAGE_NAME);
    register(ROW_SLOT, `${PACKAGE_NAME}#${PACKAGE_NAME}`);
  } catch (error) {
    console.error("[dsh-freemodel] client card failed to load (the model provider is unaffected):", error);
  }
}