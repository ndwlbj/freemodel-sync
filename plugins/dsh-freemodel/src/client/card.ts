/**
 * The read-only settings card: four tabs (overview, channels, models,
 * diagnostics), each rendered from the local API's status document. Editing
 * stays in the host's schema form; this file only shows state and offers the
 * per-model manual probe.
 */
import { API_PREFIX } from "../api-paths.ts";
import { type Translator } from "./i18n.ts";
import { getReact, type ReactElementLike } from "./react-runtime.ts";
import type { ChannelId, ChannelReport, ManualTestView, StatusReport } from "./types.ts";

export type Tab = "overview" | "channels" | "models" | "diagnostics";

export const TABS: readonly Tab[] = ["overview", "channels", "models", "diagnostics"];

export interface TestState {
  running: boolean;
  result?: ManualTestView;
  error?: string;
}

export interface CardState {
  phase: "loading" | "ready" | "error";
  status?: StatusReport;
  error?: string;
  loadedAt?: number;
}

export interface CardProps {
  t: Translator;
  tab: Tab;
  onTab: (tab: Tab) => void;
  state: CardState;
  testing: Record<string, TestState>;
  onRefresh: () => void;
  onTest: (channel: ChannelId, model: string) => void;
}

export interface FreemodelCardProps {
  t: Translator;
  api: {
    load(): Promise<StatusReport>;
    test(channel: ChannelId, model: string): Promise<ManualTestView>;
  };
}

const CLASS = "fm";

function h(type: unknown, props: Record<string, unknown> | null, ...children: unknown[]): ReactElementLike {
  return getReact().createElement(type, props, ...children);
}

function when(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds <= 0) return "—";
  return `${new Date(seconds * 1000).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

function ms(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : String(Math.round(value));
}

function channelName(t: Translator, id: ChannelId): string {
  return id === "openrouter" ? t("channelOpenRouter") : t("channelGroq");
}

function modelKey(channel: ChannelId, model: string): string {
  return `${channel}:${model}`;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function keyText(t: Translator, channel: ChannelReport): string {
  if (channel.key === "unknown") return t("keyUnknown");
  if (!channel.key.configured) return t("keyMissing");
  return channel.key.source === undefined
    ? t("keyConfigured")
    : `${t("keyConfigured")} · ${t("keySource", { source: channel.key.source })}`;
}

function channelsOf(status: StatusReport | undefined): ChannelReport[] {
  if (status === undefined || !Array.isArray(status.channels)) return [];
  return status.channels;
}

function badge(text: string, tone: "ok" | "warn" | "bad" | "muted"): ReactElementLike {
  return h("span", { className: `${CLASS}-badge ${CLASS}-badge-${tone}` }, text);
}

function kv(label: string, value: unknown, key?: string): ReactElementLike {
  return h(
    "div",
    { className: `${CLASS}-kv`, ...(key === undefined ? {} : { key }) },
    h("dt", { className: `${CLASS}-kv-label` }, label),
    h("dd", { className: `${CLASS}-kv-value` }, value),
  );
}

function stat(t: Translator, label: string, value: string | number, key?: string): ReactElementLike {
  return h(
    "div",
    { className: `${CLASS}-stat`, ...(key === undefined ? {} : { key }) },
    h("span", { className: `${CLASS}-stat-value` }, String(value)),
    h("span", { className: `${CLASS}-stat-label` }, label),
  );
}

function tabBar(props: CardProps): ReactElementLike {
  return h(
    "nav",
    { className: `${CLASS}-tabs`, role: "tablist", "aria-label": props.t("title") },
    ...TABS.map((tab) =>
      h(
        "button",
        {
          key: tab,
          type: "button",
          role: "tab",
          "aria-selected": props.tab === tab,
          className: `${CLASS}-tab${props.tab === tab ? ` ${CLASS}-tab-active` : ""}`,
          onClick: () => props.onTab(tab),
        },
        props.t(`tab${tab[0]?.toUpperCase() ?? ""}${tab.slice(1)}` as Parameters<Translator>[0]),
      ),
    ),
  );
}

function overview(props: CardProps): ReactElementLike {
  const { t, state } = props;
  const status = state.status;
  const channels = channelsOf(status);
  const listed = channels.reduce((sum, channel) => sum + channel.models.listed.length, 0);
  const hidden = channels.reduce((sum, channel) => sum + channel.models.hidden.length, 0);
  const probes = channels.reduce((sum, channel) => sum + channel.models.probesToday, 0);
  const enabled = channels.filter((channel) => channel.enabled).length;

  return h(
    "div",
    { className: `${CLASS}-panel`, role: "tabpanel" },
    h("h3", { className: `${CLASS}-section-title` }, t("overviewTitle")),
    h(
      "div",
      { className: `${CLASS}-stats` },
      stat(t, t("overviewActive"), `${enabled}/${channels.length}`),
      stat(t, t("overviewListed"), listed),
      stat(t, t("overviewHidden"), hidden),
      stat(t, t("overviewProbes"), probes),
    ),
    h(
      "dl",
      { className: `${CLASS}-kv-list` },
      kv(t("version"), status === undefined ? "—" : `${status.plugin} ${status.version}`),
      kv(t("spec"), status === undefined ? "—" : `v${status.specVersion}`),
      kv(
        t("statePath"),
        status === undefined
          ? "—"
          : h("span", { className: `${CLASS}-path` }, status.statePath, " ", badge(status.stateExists ? t("stateExists") : t("stateMissing"), status.stateExists ? "ok" : "warn")),
      ),
    ),
    h("h4", { className: `${CLASS}-subtitle` }, t("overviewChannels")),
    channels.length === 0
      ? h("p", { className: `${CLASS}-empty` }, t("none"))
      : h(
          "ul",
          { className: `${CLASS}-channel-summary` },
          ...channels.map((channel) =>
            h(
              "li",
              { key: channel.id, className: `${CLASS}-channel-summary-row` },
              h("strong", null, channelName(t, channel.id)),
              h("span", { className: `${CLASS}-muted` }, channel.route),
              badge(channel.enabled ? t("enabled") : t("disabled"), channel.enabled ? "ok" : "muted"),
              badge(`${channel.models.listed.length} ${t("listed")}`, "ok"),
              badge(`${channel.models.hidden.length} ${t("hidden")}`, "warn"),
            ),
          ),
        ),
    h("p", { className: `${CLASS}-note` }, t("subtitle")),
  );
}

function channelCard(t: Translator, channel: ChannelReport): ReactElementLike {
  const models = channel.models;
  const last = models.lastRound;
  const rows: ReactElementLike[] = [
    kv(t("key"), `${channel.apiKeyEnv}: ${keyText(t, channel)}`, "key"),
    kv(t("route"), channel.route, "route"),
    kv(
      t("catalog"),
      `${models.catalogFetchedAt === null ? t("never") : when(models.catalogFetchedAt)} · ${models.candidates} ${t("listed")}`,
      "catalog",
    ),
    kv(t("probesToday"), String(models.probesToday), "probes"),
  ];
  if (last !== null) {
    rows.push(
      kv(
        t("lastRound"),
        `${when(last.at)} · ${t("roundProbes", { count: last.probes })}${last.stopReason === null ? "" : ` · ${t("roundStopped", { reason: last.stopReason })}`}`,
        "last",
      ),
    );
  }
  if (models.blockedUntil !== null && models.blockedUntil > Date.now() / 1000) {
    rows.push(kv(t("blockedUntil"), when(models.blockedUntil), "blocked-until"));
  }
  if (models.catalogError !== null) rows.push(kv(t("catalogError"), models.catalogError, "catalog-error"));

  return h(
    "article",
    { key: channel.id, className: `${CLASS}-channel` },
    h(
      "header",
      { className: `${CLASS}-channel-header` },
      h("h4", { className: `${CLASS}-channel-name` }, channelName(t, channel.id)),
      badge(channel.enabled ? t("enabled") : t("disabled"), channel.enabled ? "ok" : "muted"),
      badge(channel.key === "unknown" ? t("keyUnknown") : channel.key.configured ? t("keyConfigured") : t("keyMissing"), channel.key === "unknown" ? "warn" : channel.key.configured ? "ok" : "bad"),
    ),
    channel.blocked === undefined ? null : h("p", { className: `${CLASS}-warn` }, `${t("blocked")}: ${channel.blocked}`),
    h("dl", { className: `${CLASS}-kv-list` }, ...rows),
  );
}

function channelsTab(props: CardProps): ReactElementLike {
  const channels = channelsOf(props.state.status);
  return h(
    "div",
    { className: `${CLASS}-panel`, role: "tabpanel" },
    h("h3", { className: `${CLASS}-section-title` }, props.t("channelsTitle")),
    channels.length === 0
      ? h("p", { className: `${CLASS}-empty` }, props.t("none"))
      : h("div", { className: `${CLASS}-channels` }, ...channels.map((channel) => channelCard(props.t, channel))),
    h("p", { className: `${CLASS}-note` }, props.t("diagnosticsChannelHint")),
  );
}

function testLine(t: Translator, state: TestState | undefined): ReactElementLike | null {
  if (state === undefined) return null;
  if (state.error !== undefined) {
    return h("p", { className: `${CLASS}-test ${CLASS}-test-bad` }, t("testResult", { result: t("testFailed"), detail: state.error }));
  }
  if (state.result !== undefined) {
    const result = state.result.result;
    if (result.ok) {
      return h(
        "p",
        { className: `${CLASS}-test ${CLASS}-test-ok` },
        t("testResult", { result: t("testOk"), detail: result.ttftMs === null ? "—" : t("ttft", { ms: ms(result.ttftMs) }) }),
      );
    }
    const detail = result.error ?? (result.statusCode === null || result.statusCode === undefined ? t("unknown") : `HTTP ${result.statusCode}`);
    return h("p", { className: `${CLASS}-test ${CLASS}-test-bad` }, t("testResult", { result: t("testFailed"), detail }));
  }
  return null;
}

function modelRow(
  props: CardProps,
  channel: ChannelId,
  model: string,
  details: ReactElementLike[],
): ReactElementLike {
  const t = props.t;
  const key = modelKey(channel, model);
  const test = props.testing[key];
  const running = test?.running === true;
  return h(
    "li",
    { key, className: `${CLASS}-model` },
    h(
      "div",
      { className: `${CLASS}-model-main` },
      h("code", { className: `${CLASS}-model-id` }, model),
      ...details,
    ),
    h(
      "button",
      {
        type: "button",
        className: `${CLASS}-button ${CLASS}-test-button`,
        disabled: running,
        onClick: () => props.onTest(channel, model),
      },
      running ? t("testing") : t("test"),
    ),
    testLine(t, test),
  );
}

function modelsTab(props: CardProps): ReactElementLike {
  const t = props.t;
  const channels = channelsOf(props.state.status);
  const sections = channels.map((channel) => {
    const model = channel.models;
    const listed = model.listed.map((entry) =>
      modelRow(props, channel.id, entry.id, [
        badge(t("testOk"), "ok"),
        h("span", { className: `${CLASS}-muted` }, t("ttft", { ms: ms(entry.ttftMs) })),
        h("span", { className: `${CLASS}-muted` }, t("testedAt", { when: when(entry.testedAt) })),
      ]),
    );
    const hidden = model.hidden.map((entry) =>
      modelRow(props, channel.id, entry.id, [
        badge(t("hidden"), "warn"),
        h("span", { className: `${CLASS}-reason` }, `${t("reason")}: ${entry.reason}`),
      ]),
    );
    return h(
      "section",
      { key: channel.id, className: `${CLASS}-model-group` },
      h(
        "header",
        { className: `${CLASS}-model-group-header` },
        h("h4", null, channelName(t, channel.id)),
        badge(`${model.listed.length} ${t("listed")}`, "ok"),
        badge(`${model.hidden.length} ${t("hidden")}`, "warn"),
      ),
      h("h5", { className: `${CLASS}-model-list-title` }, t("listed")),
      listed.length === 0 ? h("p", { className: `${CLASS}-empty` }, t("noListed")) : h("ul", { className: `${CLASS}-model-list` }, ...listed),
      h("h5", { className: `${CLASS}-model-list-title` }, t("hidden")),
      hidden.length === 0 ? h("p", { className: `${CLASS}-empty` }, t("noHidden")) : h("ul", { className: `${CLASS}-model-list` }, ...hidden),
    );
  });

  return h(
    "div",
    { className: `${CLASS}-panel`, role: "tabpanel" },
    h("h3", { className: `${CLASS}-section-title` }, t("modelsTitle")),
    h("p", { className: `${CLASS}-note` }, t("modelsNote")),
    sections.length === 0 ? h("p", { className: `${CLASS}-empty` }, t("none")) : h("div", { className: `${CLASS}-model-groups` }, ...sections),
  );
}

function diagnosticsTab(props: CardProps): ReactElementLike {
  const { t, state } = props;
  const status = state.status;
  const channels = channelsOf(status);
  const issues: ReactElementLike[] = [];
  for (const channel of channels) {
    if (channel.blocked !== undefined) {
      issues.push(h("li", { key: `${channel.id}-blocked` }, `${channelName(t, channel.id)}: ${t("blocked")} — ${channel.blocked}`));
    }
    if (channel.models.catalogError !== null) {
      issues.push(h("li", { key: `${channel.id}-catalog` }, `${channelName(t, channel.id)}: ${t("catalogError")} — ${channel.models.catalogError}`));
    }
    const stop = channel.models.lastRound?.stopReason;
    if (stop !== undefined && stop !== null) {
      issues.push(h("li", { key: `${channel.id}-stop` }, `${channelName(t, channel.id)}: ${t("roundStopped", { reason: stop })}`));
    }
    if (channel.models.blockedUntil !== null && channel.models.blockedUntil > Date.now() / 1000) {
      issues.push(h("li", { key: `${channel.id}-until` }, `${channelName(t, channel.id)}: ${t("blockedUntil", { when: when(channel.models.blockedUntil) })}`));
    }
  }
  return h(
    "div",
    { className: `${CLASS}-panel`, role: "tabpanel" },
    h("h3", { className: `${CLASS}-section-title` }, t("diagnosticsTitle")),
    h(
      "dl",
      { className: `${CLASS}-kv-list` },
      kv(t("version"), status === undefined ? "—" : `${status.plugin} ${status.version}`),
      kv(t("spec"), status === undefined ? "—" : `v${status.specVersion}`),
      kv(t("diagnosticsSchema"), status === undefined ? "—" : String(status.schemaVersion)),
      kv(t("diagnosticsApi"), API_PREFIX),
      kv(
        t("statePath"),
        status === undefined
          ? "—"
          : h("span", { className: `${CLASS}-path` }, status.statePath, " ", badge(status.stateExists ? t("stateExists") : t("stateMissing"), status.stateExists ? "ok" : "warn")),
      ),
    ),
    issues.length === 0
      ? h("p", { className: `${CLASS}-ok` }, t("diagnosticsOk"))
      : h("div", null, h("h4", { className: `${CLASS}-subtitle` }, t("diagnosticsIssues")), h("ul", { className: `${CLASS}-issues` }, ...issues)),
    h("p", { className: `${CLASS}-note` }, t("diagnosticsChannelHint")),
    h("p", { className: `${CLASS}-note` }, t("diagnosticsDoctor")),
  );
}

function body(props: CardProps): ReactElementLike {
  if (props.state.phase === "loading" && props.state.status === undefined) {
    return h("p", { className: `${CLASS}-loading`, role: "status" }, props.t("loading"));
  }
  if (props.state.phase === "error" && props.state.status === undefined) {
    return h(
      "div",
      { className: `${CLASS}-error`, role: "alert" },
      h("p", null, `${props.t("loadFailed")}: ${props.state.error ?? props.t("unknown")}`),
      h("button", { type: "button", className: `${CLASS}-button`, onClick: props.onRefresh }, props.t("retry")),
    );
  }
  switch (props.tab) {
    case "channels":
      return channelsTab(props);
    case "models":
      return modelsTab(props);
    case "diagnostics":
      return diagnosticsTab(props);
    default:
      return overview(props);
  }
}

/** The controlled card body; exported so tests can render each tab without hooks. */
export function renderCard(props: CardProps): ReactElementLike {
  const { t, state } = props;
  const status = state.status;
  return h(
    "section",
    { className: `${CLASS}-card`, "data-dsh-freemodel-card": "true" },
    h(
      "header",
      { className: `${CLASS}-header` },
      h(
        "div",
        { className: `${CLASS}-heading` },
        h("h2", { className: `${CLASS}-title` }, t("title")),
        h("p", { className: `${CLASS}-subtitle-text` }, t("subtitle")),
      ),
      h(
        "div",
        { className: `${CLASS}-actions` },
        state.phase === "loading"
          ? badge(t("loading"), "muted")
          : state.phase === "error"
            ? badge(t("loadFailed"), "bad")
            : badge(status === undefined ? t("unknown") : `v${status.version}`, "ok"),
        state.loadedAt === undefined ? null : h("span", { className: `${CLASS}-muted` }, t("lastLoaded", { when: when(state.loadedAt) })),
        h("button", { type: "button", className: `${CLASS}-button`, onClick: props.onRefresh, disabled: state.phase === "loading" }, t("refresh")),
      ),
    ),
    tabBar(props),
    state.phase === "error" && state.status !== undefined
      ? h("p", { className: `${CLASS}-error ${CLASS}-error-inline`, role: "alert" }, `${t("loadFailed")}: ${state.error ?? t("unknown")}`)
      : null,
    body(props),
  );
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * The component the host slot renders. It owns the tab, the status fetch and
 * the manual-test bookkeeping; `renderCard` stays pure.
 */
export function FreemodelCard({ t, api }: FreemodelCardProps): ReactElementLike {
  const React = getReact();
  const [tab, setTab] = React.useState<Tab>("overview");
  const [state, setState] = React.useState<CardState>({ phase: "loading" });
  const [testing, setTesting] = React.useState<Record<string, TestState>>({});
  const [revision, setRevision] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setState((previous) => (previous.status === undefined ? { phase: "loading" } : { ...previous, phase: "loading" }));
    void api
      .load()
      .then((status) => {
        if (!cancelled) setState({ phase: "ready", status, loadedAt: Date.now() / 1000 });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState((previous) => ({
            phase: "error",
            ...(previous.status === undefined ? {} : { status: previous.status }),
            error: message(error),
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, revision]);

  const onRefresh = React.useCallback(() => setRevision((value) => value + 1), []);
  const onTest = React.useCallback(
    (channel: ChannelId, model: string) => {
      const key = modelKey(channel, model);
      setTesting((previous) => ({ ...previous, [key]: { running: true } }));
      void api
        .test(channel, model)
        .then((result) => {
          setTesting((previous) => ({ ...previous, [key]: { running: false, result } }));
          setRevision((value) => value + 1);
        })
        .catch((error: unknown) => {
          setTesting((previous) => ({ ...previous, [key]: { running: false, error: message(error) } }));
        });
    },
    [api],
  );

  return renderCard({ t, tab, onTab: setTab, state, testing, onRefresh, onTest });
}

/** Exported for the client test's error-path check. */
export { errorText };