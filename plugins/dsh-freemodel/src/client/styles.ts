/**
 * The card's styles, injected once into the host page. Everything is scoped
 * under `.fm-` so the plugin never restyles the surrounding settings page.
 */

const STYLE_ID = "dsh-freemodel-card-style";

const CSS = `
.fm-card {
  --fm-bg: var(--semi-color-bg-1, #fff);
  --fm-bg-2: var(--semi-color-fill-0, #f5f6f7);
  --fm-text: var(--semi-color-text-0, #1f2329);
  --fm-muted: var(--semi-color-text-2, #646a73);
  --fm-border: var(--semi-color-border, #dee0e3);
  --fm-primary: var(--semi-color-primary, #0064fa);
  --fm-ok: var(--semi-color-success, #2ea121);
  --fm-warn: var(--semi-color-warning, #d67900);
  --fm-bad: var(--semi-color-danger, #d83931);
  box-sizing: border-box;
  border: 1px solid var(--fm-border);
  border-radius: 10px;
  background: var(--fm-bg);
  color: var(--fm-text);
  font-size: 13px;
  line-height: 1.5;
  margin: 8px 0 16px;
  overflow: hidden;
}
.fm-card *, .fm-card *::before, .fm-card *::after { box-sizing: border-box; }
.fm-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 14px 16px 10px; }
.fm-heading { min-width: 0; }
.fm-title { margin: 0; font-size: 16px; font-weight: 600; }
.fm-subtitle-text { margin: 2px 0 0; color: var(--fm-muted); font-size: 12px; }
.fm-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.fm-tabs { display: flex; gap: 2px; padding: 0 12px; border-bottom: 1px solid var(--fm-border); overflow-x: auto; }
.fm-tab { appearance: none; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--fm-muted); padding: 8px 10px; cursor: pointer; font: inherit; white-space: nowrap; }
.fm-tab:hover { color: var(--fm-text); }
.fm-tab-active { color: var(--fm-primary); border-bottom-color: var(--fm-primary); font-weight: 600; }
.fm-panel { padding: 14px 16px 16px; }
.fm-section-title { margin: 0 0 10px; font-size: 14px; font-weight: 600; }
.fm-subtitle { margin: 14px 0 8px; font-size: 13px; font-weight: 600; }
.fm-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; margin-bottom: 12px; }
.fm-stat { display: flex; flex-direction: column; gap: 2px; padding: 10px; border-radius: 8px; background: var(--fm-bg-2); }
.fm-stat-value { font-size: 20px; font-weight: 600; line-height: 1.2; }
.fm-stat-label { color: var(--fm-muted); font-size: 12px; }
.fm-kv-list { margin: 0; display: grid; grid-template-columns: minmax(110px, max-content) 1fr; gap: 6px 12px; }
.fm-kv { display: contents; }
.fm-kv-label { color: var(--fm-muted); }
.fm-kv-value { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.fm-path { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.fm-channel-summary { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.fm-channel-summary-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.fm-channels { display: flex; flex-direction: column; gap: 12px; }
.fm-channel { border: 1px solid var(--fm-border); border-radius: 8px; padding: 12px; }
.fm-channel-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.fm-channel-name { margin: 0; font-size: 14px; }
.fm-model-groups { display: flex; flex-direction: column; gap: 16px; }
.fm-model-group { border-top: 1px solid var(--fm-border); padding-top: 12px; }
.fm-model-group:first-child { border-top: 0; padding-top: 0; }
.fm-model-group-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.fm-model-group-header h4 { margin: 0; font-size: 14px; }
.fm-model-list-title { margin: 10px 0 6px; font-size: 12px; color: var(--fm-muted); text-transform: uppercase; letter-spacing: .04em; }
.fm-model-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.fm-model { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; align-items: start; border: 1px solid var(--fm-border); border-radius: 8px; padding: 8px 10px; }
.fm-model-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
.fm-model-id { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; overflow-wrap: anywhere; }
.fm-reason { color: var(--fm-muted); overflow-wrap: anywhere; }
.fm-test { grid-column: 1 / -1; margin: 2px 0 0; }
.fm-test-ok { color: var(--fm-ok); }
.fm-test-bad { color: var(--fm-bad); }
.fm-badge { display: inline-flex; align-items: center; border-radius: 999px; padding: 0 8px; font-size: 11px; line-height: 20px; white-space: nowrap; background: var(--fm-bg-2); color: var(--fm-muted); }
.fm-badge-ok { color: var(--fm-ok); background: color-mix(in srgb, var(--fm-ok) 12%, transparent); }
.fm-badge-warn { color: var(--fm-warn); background: color-mix(in srgb, var(--fm-warn) 12%, transparent); }
.fm-badge-bad { color: var(--fm-bad); background: color-mix(in srgb, var(--fm-bad) 12%, transparent); }
.fm-button { appearance: none; border: 1px solid var(--fm-border); background: var(--fm-bg); color: var(--fm-text); border-radius: 6px; padding: 4px 10px; font: inherit; font-size: 12px; cursor: pointer; }
.fm-button:hover:not(:disabled) { border-color: var(--fm-primary); color: var(--fm-primary); }
.fm-button:disabled { opacity: .55; cursor: default; }
.fm-muted { color: var(--fm-muted); font-size: 12px; }
.fm-note { margin: 10px 0 0; color: var(--fm-muted); font-size: 12px; }
.fm-empty { margin: 6px 0; color: var(--fm-muted); }
.fm-loading { margin: 0; padding: 16px; color: var(--fm-muted); }
.fm-error { margin: 0; padding: 12px 16px; color: var(--fm-bad); background: color-mix(in srgb, var(--fm-bad) 8%, transparent); }
.fm-error-inline { margin: 10px 16px 0; border-radius: 6px; }
.fm-ok { color: var(--fm-ok); }
.fm-warn { color: var(--fm-warn); }
.fm-issues { margin: 0; padding-left: 18px; color: var(--fm-warn); }
@media (max-width: 560px) {
  .fm-header { flex-direction: column; }
  .fm-actions { justify-content: flex-start; }
  .fm-kv-list { grid-template-columns: 1fr; }
  .fm-model { grid-template-columns: 1fr; }
}
`;

interface StyleLike {
  textContent: string | null;
  setAttribute(name: string, value: string): void;
}

interface DocumentLike {
  head?: { appendChild(node: unknown): void } | null;
  createElement(tag: string): StyleLike;
  querySelector(selector: string): unknown;
}

/**
 * Install the stylesheet once.
 * @returns a disposer that removes it, or a no-op outside a browser.
 */
export function installStyles(): () => void {
  const doc = (globalThis as { document?: DocumentLike }).document;
  if (doc === undefined) return () => {};
  if (doc.querySelector(`style[data-dsh-freemodel="${STYLE_ID}"]`) !== null) return () => {};
  const style = doc.createElement("style");
  style.setAttribute("data-dsh-freemodel", STYLE_ID);
  style.textContent = CSS;
  doc.head?.appendChild(style);
  return () => {
    // The host may re-evaluate the bundle on reload; leaving the shared sheet
    // in place avoids a flash and keeps duplicate registrations harmless.
  };
}