# dsh-freemodel

A [dsh](https://www.npmjs.com/package/@deepseek-ai/dsh) plugin for free models
from OpenRouter (`:free` models) and, opt-in, Groq's free plan, the
SenseNova Token Plan public beta and Alibaba Cloud Bailian. It is the dsh side of
[freemodel-sync](https://github.com/ndwlbj/freemodel-sync) and reads the same
rules from the repository's `spec/` (bundled at build time).

Once a channel has a key it reads the provider's catalogue, keeps the models
that are free by the shared rules, probes the best-ranked ones and lists those
that answered in dsh's model picker, labelled `· 免费`, under the routes
`freemodel-openrouter`, `freemodel-groq`, `freemodel-sensenova` and
`freemodel-bailian`. Each label also carries compact
capability and quota badges from the shared `spec/` vocabulary — for example
`· 工具 · 视觉 · 余 90k tokens · 5小时`. Unknown catalogue data is shown as
`能力未知` / `额度未知`, never as false or zero; old state files without the
new fields load the same way. Models that fail a probe are
hidden; the reason is in the settings card and `dsh-freemodel status`. Results
are kept in `$DSH_HOME/freemodel/state.json` (mode 600, never a key) and
refreshed on a schedule (`refresh.*`). It never changes dsh's default model.
Not published to npm.

- **Keys** are never stored in the plugin's settings. Each channel has a
  credential reference (`apiKeyEnv`, default `OPENROUTER_API_KEY` /
  `GROQ_API_KEY` / `SENSENOVA_API_KEY` / `DASHSCOPE_API_KEY`); the key itself goes into dsh's
  credential store from the settings page, or comes from the environment.
- **Groq** is off by default and stays blocked until `freePlanConfirmed` is
  set, because its free plan is a property of the account, not of the model.
- **SenseNova** is off by default too. The Token Plan is a public beta with no
  quota API, so it stays blocked until `tokenPlanConfirmed` is set (the plugin
  equivalent of `plan: token-plan`). Its optional `models` allowlist is
  intersected with the catalogue when it can be read; an empty list means every
  catalogue model whose `pricing` is the string `"0"`. Models whose price
  changes are removed and logged. SenseNova is not part of the public daily
  snapshot.
- **Bailian** is off by default and only supports the Beijing region. It stays
  blocked until `freeQuotaGuardConfirmed` is ticked (the console's "stop when
  the free quota is used up" switch) **and** `models` is non-empty. Its
  per-model allowances are entered by hand (`models[].quotaTokens`) and shown
  as `手动，未核实`; they are never deducted from the local probe budget.
  Distilled models (`id` contains `distill`) are marked `tools=false`. A 403
  `AllocationQuota.FreeTierOnly` is a `quota` failure and stops that channel
  until the next UTC day. Not part of the public daily snapshot.
- **`capacity` failures** (queue / no capacity) get their own consecutive
  counter, the same short retry TTL as transient failures, a ranking penalty,
  and become unselectable after `ranking.capacityDowngradeAfter` (default 3).
- `dsh-freemodel status` and `dsh-freemodel doctor [--json]` print the state
  and check Node.js, the dsh version, the bundled spec and whether the key
  variables are set; `status` also shows each channel's listed and hidden
  models. They never print a key.
- **`/freemodel`** shows the same status in a conversation, can refresh now,
  and can test one model: `/freemodel test <channel> <model>`.

## Settings card

The browser half (`lib/client.js`, exported as `./client`) registers a
read-only card on the plugin's page in the settings panel. It has four tabs:

| Tab | Shows |
| --- | --- |
| **Overview** | Plugin/spec version, state file path and whether it exists, enabled channels, listed/hidden model counts and probes used today. |
| **Channels** | Enabled state, key presence and source (`file`, `env`, …; never the value), route, catalogue time/error, probes today, last round and any block/rate-limit pause. |
| **Models** | Every listed model with its capability/quota badges, last probe result and TTFT, plus every model that is **not** listed with the reason (failed, transient, not probed yet, expiry, …). Every entry has a **Test now** button. |
| **Diagnostics** | Status schema, local API prefix, catalogue errors, stopped rounds, pauses, and the `dsh-freemodel doctor` hint. |

The card only displays state and performs the per-model manual test. Channel
switches, key references and the ranking/refresh options stay in the host's
schema form below it; the card does not duplicate that editor.

A manual test sends one tiny probe through the host process
(`POST /freemodel/api/test`) and uses one free request from today's budget. It
needs a configured key and an enabled channel; Groq additionally needs
`freePlanConfirmed`. The browser never sees a provider key. The host's
`/freemodel/api` routes are loopback-only; writes are authorized by the
on-disk secret for CLI/API callers and by a separate process-local token that
the loopback status document hands to this card. That token is not the secret
on disk and is never logged. React is required from the host runtime
(`window.__ModuleLoader__`), so the plugin adds no React dependency.

```bash
# from this directory (needs pnpm 10; npm 10 cannot install these peers)
pnpm install --frozen-lockfile
pnpm run check            # typecheck + tests + build
pnpm run build && pnpm pack
dsh plugin --profile <test profile> add ./dsh-freemodel-0.1.0.tgz
dsh plugin --profile <test profile> exec dsh-freemodel doctor
```

`pnpm build` writes `lib/index.js`, `lib/bin.js` and the browser bundle
`lib/client.js`. Requires Node.js `^22.19.0 || >=24.0.0` and dsh
`>=0.2.1-rc.1 <0.3.0-0`. `scripts/verify-host/verify-host.sh` checks the plugin
inside a real dsh in a throwaway home; see `docs/dsh-plugin-verification.md` in
the repository.

## 中文

dsh 插件：OpenRouter 的 `:free` 免费模型，以及需手动开启的 Groq 免费计划、
SenseNova Token Plan 公测和阿里云百炼。渠道配好 key 后，插件读取目录、按共享规则筛出免费模型、探测
排名靠前的几个，把通过的模型以「· 免费」标签列进 dsh 的模型选择器（路由
`freemodel-openrouter` / `freemodel-groq` / `freemodel-sensenova` / `freemodel-bailian`），并显示能力/额度徽标（如「· 工具 · 余 90k tokens · 5小时」；未知时显示「能力未知」/「额度未知」，手填额度显示「手动，未核实」）。未通过探测的模型会隐藏，原因可在设置卡片和
`dsh-freemodel status` 中查看。结果存于 `$DSH_HOME/freemodel/state.json`
（权限 600，不含 key），按 `refresh.*` 定时刷新。绝不改 dsh 的默认模型；不发布到
npm。key 只保存在 dsh 凭据库（设置页里填）或环境变量中，插件设置里只存变量名。
Groq 默认关闭，且须打开 `freePlanConfirmed` 才会启用。SenseNova 也默认关闭，公测期没有
额度 API，须打开 `tokenPlanConfirmed`（等同 Python 的 `plan: token-plan`）才会列出/探测；
可选 `models` 允许列表会与目录取交集（留空表示目录里 `pricing` 为字符串 `"0"` 的模型），
价格变化会移出并记录日志。SenseNova 不进入公开的每日快照。百炼也默认关闭，只支持北京地域；
必须同时打开 `freeQuotaGuardConfirmed`（控制台「免费额度用完即停」）并配置非空 `models` 才会
列出/探测；每个模型的额度手填为 `models[].quotaTokens`，显示「手动，未核实」，不参与本地预算
扣减；`id` 含 `distill` 的蒸馏模型标记 `tools=false`；403 `AllocationQuota.FreeTierOnly`
记为 `quota` 并当天停该渠道。百炼也不进入公开快照。`capacity`（排队/无容量）与 transient
一样短 TTL 重试，但单独计数、排名扣分，连续 `capacityDowngradeAfter` 次（默认 3）后不可选。
`dsh-freemodel status` /
`doctor` 用于自检，不会输出 key；会话里也可以用 `/freemodel` 查看状态、立即刷新或
用 `/freemodel test <channel> <model>` 测试单个模型。

### 设置卡片

浏览器端（`lib/client.js`，通过 `./client` 导出）会在插件设置页注册一张只读卡片，
分为四栏：

| 栏 | 内容 |
| --- | --- |
| **概览** | 插件/规则版本、状态文件路径及是否已创建、启用渠道数、已列出/未列出模型数、今日探测次数。 |
| **渠道** | 是否启用、key 是否已配置及来源（`file`、`env` 等，绝不显示值）、路由、目录读取时间/错误、今日探测、上一轮结果、受限/暂停信息。 |
| **模型** | 每个已列出模型的能力/额度徽标、最近探测结果与首字延迟；每个**未列出**的模型及原因（失败、临时不可用、尚未探测、即将过期等）。每一项都有「手动测试」按钮。 |
| **诊断** | 状态格式版本、本地接口前缀、目录错误、提前停止的轮次、限流暂停，以及 `dsh-freemodel doctor` 提示。 |

卡片只显示状态并提供逐模型手动测试；渠道开关、key 引用、排序/刷新参数仍在卡片下方的
宿主 schema 表单里编辑，卡片不重复实现编辑器。

手动测试通过宿主进程（`POST /freemodel/api/test`）只发一个很小的探测请求，会占用
今天的 1 次免费额度；需要已配置的 key 和已启用的渠道，Groq 还需要
`freePlanConfirmed`。浏览器端永远拿不到 provider key。`/freemodel/api` 只接受回环
请求；写操作对 CLI/API 调用方校验磁盘上的 secret，对本卡片则使用状态文档在回环内下发
的、仅在当前进程有效的独立 token——它不是磁盘上的 secret，也不会写日志。React 从宿主
运行时（`window.__ModuleLoader__`）`require`，插件不新增 React 依赖。

### 开发与打包

```bash
pnpm install --frozen-lockfile
pnpm run check            # 类型检查 + 测试 + 构建
pnpm run build && pnpm pack
```

`pnpm build` 会同时生成 `lib/index.js`、`lib/bin.js` 和浏览器包 `lib/client.js`。
需要 Node.js `^22.19.0 || >=24.0.0`、dsh `>=0.2.1-rc.1 <0.3.0-0`。

MIT licensed.