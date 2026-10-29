/**
 * The card's own copy. Deliberately small and local: the host locale decides
 * whether Chinese or English is shown, and no key or technical string leaks
 * into the translations.
 */

export type ClientLocale = "zh" | "en";

const EN = {
  title: "FreeModel",
  subtitle: "Free OpenRouter, Groq, SenseNova and Bailian models that passed a probe. Read-only status; edit channels below in the settings form.",
  loading: "Reading status…",
  loadFailed: "Could not read status",
  refresh: "Refresh status",
  retry: "Retry",
  lastLoaded: "Updated {when}",
  tabOverview: "Overview",
  tabChannels: "Channels",
  tabModels: "Models",
  tabDiagnostics: "Diagnostics",
  overviewTitle: "At a glance",
  overviewActive: "Active channels",
  overviewListed: "Listed models",
  overviewHidden: "Not listed",
  overviewProbes: "Probes today",
  version: "Plugin",
  spec: "Spec",
  statePath: "State file",
  stateExists: "created",
  stateMissing: "not created yet",
  overviewChannels: "Channel summary",
  channelsTitle: "Channels",
  enabled: "enabled",
  disabled: "disabled",
  active: "active",
  inactive: "inactive",
  key: "Key",
  keyConfigured: "configured",
  keyMissing: "not set",
  keyUnknown: "unknown",
  keySource: "source {source}",
  route: "Route",
  catalog: "Catalogue",
  never: "never",
  catalogError: "Catalogue error",
  blocked: "Blocked",
  probesToday: "Probes today",
  lastRound: "Last round",
  roundProbes: "{count} probe(s)",
  roundStopped: "stopped: {reason}",
  blockedUntil: "Paused until {when}",
  modelsTitle: "Models and probe results",
  listed: "Listed",
  hidden: "Not listed",
  noListed: "No model has passed a probe yet.",
  noHidden: "Every catalogue model is listed.",
  ttft: "TTFT {ms} ms",
  testedAt: "tested {when}",
  reason: "Reason",
  test: "Test now",
  testing: "Testing…",
  testOk: "Probe passed",
  testFailed: "Probe failed",
  testResult: "{result}: {detail}",
  modelsNote: "A manual test sends one tiny request and uses one free request from today's budget.",
  diagnosticsTitle: "Diagnostics",
  diagnosticsOk: "No blocking problem found in the status document.",
  diagnosticsIssues: "Problems reported by the state file",
  diagnosticsApi: "Local API",
  diagnosticsSchema: "Status schema",
  diagnosticsDoctor: "For a full check run: dsh-freemodel doctor",
  diagnosticsChannelHint: "Keys are never shown here; only whether one is configured.",
  none: "none",
  unknown: "unknown",
  channelOpenRouter: "OpenRouter",
  channelGroq: "Groq",
  channelSenseNova: "SenseNova",
  channelBailian: "Bailian",
} as const;

export type MessageKey = keyof typeof EN;

const ZH: Record<MessageKey, string> = {
  title: "免费模型",
  subtitle: "已通过探测的 OpenRouter / Groq / SenseNova / 百炼免费模型。此处只读状态；渠道开关与密钥请在下方设置表单里编辑。",
  loading: "正在读取状态…",
  loadFailed: "读取状态失败",
  refresh: "刷新状态",
  retry: "重试",
  lastLoaded: "更新于 {when}",
  tabOverview: "概览",
  tabChannels: "渠道",
  tabModels: "模型",
  tabDiagnostics: "诊断",
  overviewTitle: "一览",
  overviewActive: "启用渠道",
  overviewListed: "已列出模型",
  overviewHidden: "未列出",
  overviewProbes: "今日探测",
  version: "插件",
  spec: "规则版本",
  statePath: "状态文件",
  stateExists: "已创建",
  stateMissing: "尚未创建",
  overviewChannels: "渠道摘要",
  channelsTitle: "渠道",
  enabled: "已启用",
  disabled: "已关闭",
  active: "生效中",
  inactive: "未生效",
  key: "密钥",
  keyConfigured: "已配置",
  keyMissing: "未设置",
  keyUnknown: "未知",
  keySource: "来源 {source}",
  route: "路由",
  catalog: "目录",
  never: "从未",
  catalogError: "目录错误",
  blocked: "受阻",
  probesToday: "今日探测",
  lastRound: "上一轮",
  roundProbes: "{count} 次探测",
  roundStopped: "停止原因：{reason}",
  blockedUntil: "暂停至 {when}",
  modelsTitle: "模型与探测状态",
  listed: "已列出",
  hidden: "未列出",
  noListed: "还没有模型通过探测。",
  noHidden: "目录里的模型均已列出。",
  ttft: "首字 {ms} 毫秒",
  testedAt: "探测于 {when}",
  reason: "原因",
  test: "手动测试",
  testing: "测试中…",
  testOk: "探测通过",
  testFailed: "探测失败",
  testResult: "{result}：{detail}",
  modelsNote: "手动测试只发一个很小的请求，会占用今天的 1 次免费额度。",
  diagnosticsTitle: "诊断",
  diagnosticsOk: "状态文档里没有发现阻塞问题。",
  diagnosticsIssues: "状态文件报告的问题",
  diagnosticsApi: "本地接口",
  diagnosticsSchema: "状态格式",
  diagnosticsDoctor: "完整检查请运行：dsh-freemodel doctor",
  diagnosticsChannelHint: "这里不会显示密钥，只会说明是否已配置。",
  none: "无",
  unknown: "未知",
  channelOpenRouter: "OpenRouter",
  channelGroq: "Groq",
  channelSenseNova: "SenseNova",
  channelBailian: "百炼",
};

const MESSAGES: Record<ClientLocale, Record<MessageKey, string>> = { en: EN, zh: ZH };

export type Translator = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Pick Chinese only for a `zh`-prefixed active locale; English otherwise. */
export function resolveLocale(active: string | undefined): ClientLocale {
  return active !== undefined && active.toLowerCase().startsWith("zh") ? "zh" : "en";
}

/** Build a translator for one language. */
export function createTranslator(locale: ClientLocale): Translator {
  const messages = MESSAGES[locale];
  return (key, vars) => {
    const template = messages[key] ?? EN[key];
    if (vars === undefined) return template;
    return template.replace(/\{(\w+)\}/g, (_match, name: string) => (name in vars ? String(vars[name]) : `{${name}}`));
  };
}

/** The two dictionaries, exported for tests and for the host locale registration. */
export const dictionaries = { en: EN, zh: ZH } as const;