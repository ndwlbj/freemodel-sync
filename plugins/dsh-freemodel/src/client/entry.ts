/**
 * Browser entry point. The host loads `lib/client.js` as a classic script and
 * provides `window.__ModuleLoader__`; the build wraps this module in a CJS
 * factory whose `require` resolves React from the host runtime. No React
 * package is bundled.
 */
import * as React from "react";
import { setReact, type ReactLike } from "./react-runtime.ts";
import { apply, inject, name } from "./index.ts";

setReact(React as unknown as ReactLike);

export { apply, inject, name };
export { FreemodelCard, renderCard } from "./card.ts";
export { FreemodelApiClient, LocalApiError } from "./api.ts";
export { createTranslator, resolveLocale } from "./i18n.ts";
export { capabilityBadges, quotaBadge, modelBadges, quotaWindowLabel, quotaUnitLabel } from "./badges.ts";