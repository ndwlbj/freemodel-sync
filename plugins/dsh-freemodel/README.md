# dsh-freemodel

A [dsh](https://www.npmjs.com/package/@deepseek-ai/dsh) plugin for free models
from OpenRouter (`:free` models) and, opt-in, Groq's free plan. It is the dsh
side of [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) and reads the
same rules from the repository's `spec/` (bundled at build time).

Once a channel has a key it reads the provider's catalogue, keeps the models
that are free by the shared rules, probes the best-ranked ones and lists those
that answered in dsh's model picker, labelled `· 免费`, under the routes
`freemodel-openrouter` and `freemodel-groq`. Models that fail a probe are
hidden; the reason is in the settings card and `dsh-freemodel status`. Results
are kept in `$DSH_HOME/freemodel/state.json` (mode 600, never a key) and
refreshed on a schedule (`refresh.*`). It never changes dsh's default model.
Not published to npm.

- **Keys** are never stored in the plugin's settings. Each channel has a
  credential reference (`apiKeyEnv`, default `OPENROUTER_API_KEY` /
  `GROQ_API_KEY`); the key itself goes into dsh's credential store from the
  settings page, or comes from the environment.
- **Groq** is off by default and stays blocked until `freePlanConfirmed` is
  set, because its free plan is a property of the account, not of the model.
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
| **Models** | Every listed model with its last probe result and TTFT, plus every model that is **not** listed with the reason (failed, transient, not probed yet, expiry, …). Every entry has a **Test now** button. |
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

dsh 插件：OpenRouter 的 `:free` 免费模型，以及需手动开启的 Groq 免费计划。
渠道配好 key 后，插件读取目录、按共享规则筛出免费模型、探测排名靠前的几个，把通过的
模型以「· 免费」标签列进 dsh 的模型选择器（路由 `freemodel-openrouter` /
`freemodel-groq`）。未通过探测的模型会隐藏，原因可在设置卡片和
`dsh-freemodel status` 中查看。结果存于 `$DSH_HOME/freemodel/state.json`
（权限 600，不含 key），按 `refresh.*` 定时刷新。绝不改 dsh 的默认模型；不发布到
npm。key 只保存在 dsh 凭据库（设置页里填）或环境变量中，插件设置里只存变量名。
Groq 默认关闭，且须打开 `freePlanConfirmed` 才会启用。`dsh-freemodel status` /
`doctor` 用于自检，不会输出 key；会话里也可以用 `/freemodel` 查看状态、立即刷新或
用 `/freemodel test <channel> <model>` 测试单个模型。

### 设置卡片

浏览器端（`lib/client.js`，通过 `./client` 导出）会在插件设置页注册一张只读卡片，
分为四栏：

| 栏 | 内容 |
| --- | --- |
| **概览** | 插件/规则版本、状态文件路径及是否已创建、启用渠道数、已列出/未列出模型数、今日探测次数。 |
| **渠道** | 是否启用、key 是否已配置及来源（`file`、`env` 等，绝不显示值）、路由、目录读取时间/错误、今日探测、上一轮结果、受限/暂停信息。 |
| **模型** | 每个已列出模型的最近探测结果与首字延迟；每个**未列出**的模型及原因（失败、临时不可用、尚未探测、即将过期等）。每一项都有「手动测试」按钮。 |
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