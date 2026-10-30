# dsh-freemodel

[English](README.md) | [简体中文](README.zh-CN.md)

用于 [dsh](https://www.npmjs.com/package/@deepseek-ai/dsh) 的多渠道免费模型插件，支持 OpenRouter（`:free` 免费模型）、Groq（需开启免费计划确认）、商汤日日新 SenseNova（Token Plan 公测）以及阿里云百炼（DashScope 北京地域）。本项目是 [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) 在 dsh 运行时侧的原生 TypeScript 插件实现，构建时直接打包本仓库 `spec/` 目录的共享规则。

> [!NOTE]
> - **发布状态**：版本 1.0.0（私有包；**未发布到 npm**）。
> - **界面截图**：真实截图（新建 dsh profile 上用 headless Chrome 截取，断网、未手动填写任何 key，详见[设置卡片](#设置卡片与管理界面)一节）。
> - **真机测试状态**：已在 Linux（dsh 0.2.1-rc.3）环境下验证；**未在 Windows / macOS 真实设备上运行测试**。
> - **Profile 文件布局**：当前 profile 的 patch 路径 `$DSH_HOME/profiles/<id>/cordis.patch.yml` 已在真实 dsh 0.2.1-rc.3 的 home 上核对（profile 目录及 `profileContext.patchPath`）；`autoDefaultModel` 的实际写盘流程未在真实 profile 上执行过。

---

## 功能特性

- **多渠道免费模型聚合**：将通过验证的 OpenRouter、Groq、SenseNova 和百炼免费模型分别注册为独立路由：`freemodel-openrouter`、`freemodel-groq`、`freemodel-sensenova` 和 `freemodel-bailian`。
- **选择器徽标清晰标注**：免费模型在 dsh 模型选择器中统一带有 `· 免费` 标签，并附带能力与额度徽标（如 `· 工具 · 视觉 · 余 90k tokens · 5小时`）；未知数据如实标明 `能力未知` / `额度未知`，绝不虚假显示为 false 或 0。
- **探测护栏与静默隐藏**：读取上游目录后，仅对候选模型发送轻量 probe 探测。探测失败的模型自动从选择器中隐藏，失败原因记录在 `$DSH_HOME/freemodel/state.json`（权限 0600，绝不含密钥）中，可通过命令查看。
- **容量/排队失败降级机制**：遇到排队或无容量错误（`capacity`）时，采用与临时错误一致的短重试 TTL，单独统计连续失败次数并执行排名扣分，连续失败达到阈值后自动移出可用列表。
- **可选 `freemodel-auto` 自动路由**：可自选开启的 `freemodel-auto`（模型 ID `best`）路由，始终指向探测通过的当前综合排名第 1 的免费模型；当遇到终端错误且**尚未产生任何可见文本**时，在进程内平滑故障转移到下一位候选模型。
- **可选 `autoDefaultModel` 默认模型切换**：可自选开启的 profile 默认模型（`agent-default-model`）自动切换，严格禁止修改 QQ/机器人 profile 和全局 home 层 patch。
- **第二层手动登记（Tier-2 Manual Registry）**：支持在 `manual[]` 中登记第三方插件（如 ZCode、Qoder、WorkBuddy）模型，仅保存公开事实；严格拒绝任何密钥/凭据；探测默认关闭，开启后每模型每天最多 1 次单点探测。
- **交互式设置卡片**：在 dsh 设置面板的插件页提供五栏只读卡片（概览、渠道、模型、手动登记、诊断），支持逐模型手动单点测试。
- **内置 CLI 与斜杠命令**：支持通过 `dsh-freemodel status` / `doctor` 进行环境与状态自检，支持在会话中使用 `/freemodel` 斜杠命令。

---

## 快速上手与安装

### 环境要求

- Node.js `^22.19.0 || >=24.0.0`
- pnpm `^10.0.0`
- dsh `>=0.2.1-rc.1 <0.3.0-0`

### 编译与打包

```bash
# 在插件目录内：plugins/dsh-freemodel
pnpm install --frozen-lockfile
pnpm run check            # 类型检查 + 单元测试 + 构建
pnpm run build && pnpm pack

# 安装到 dsh 测试 profile 中
dsh plugin --profile <测试profile名> add ./dsh-freemodel-1.0.0.tgz
dsh plugin --profile <测试profile名> exec dsh-freemodel doctor
```

`pnpm build` 会生成 `lib/index.js`（插件服务端入口）、`lib/bin.js`（CLI 工具）以及 `lib/client.js`（浏览器设置卡片）。

### 配置 API 密钥

提供商 API Key **绝不**存放在插件配置文件中。每个渠道仅声明一个环境变量名称（如 `OPENROUTER_API_KEY`）。配置方式有两种：
1. 在 dsh 设置面板的「凭据 / Credentials」页中输入（安全写入 `$DSH_HOME/.credentials.yaml`，权限 0600）；
2. 或者在启动 dsh 前通过终端环境变量导出：
   ```bash
   export OPENROUTER_API_KEY="your-openrouter-key"
   ```

#### 无头环境 / 无凭据存储服务（Headless profiles / no credential store）

部分无头环境（headless profile）模板不启用本地凭据服务（`@deepseek-ai/dsh-credentials-local`）。当凭据服务不存在或未配置对应密钥时，插件会自动回退读取启动 dsh 的进程环境变量（如 `OPENROUTER_API_KEY`、`GROQ_API_KEY`、`SENSENOVA_API_KEY`、`DASHSCOPE_API_KEY`）。若两处均有配置，凭据存储服务依然保持最高优先级；状态报告中密钥来源如实标明为 `env`，插件绝不在日志、状态或错误中打印或输出密钥明文。

---

## 支持的渠道

| 渠道 | 对应路由 | 默认状态 | 必需的确认项 / 规则 | 密钥环境变量 |
| --- | --- | --- | --- | --- |
| **OpenRouter** | `freemodel-openrouter` | **默认启用**（检测到 key 即生效） | 仅筛选目录中带有 `:free` 标记的真正免费模型。 | `OPENROUTER_API_KEY` |
| **Groq** | `freemodel-groq` | 默认关闭 | 必须勾选 `freePlanConfirmed: true`。因其免费计划属于账号属性而非模型属性。 | `GROQ_API_KEY` |
| **SenseNova** | `freemodel-sensenova` | 默认关闭 | 必须勾选 `tokenPlanConfirmed: true`（Token Plan 公测）。价格必须为 `"0"`。可选配置 `models` 白名单。 | `SENSENOVA_API_KEY` |
| **Bailian** | `freemodel-bailian` | 默认关闭 | 必须勾选 `freeQuotaGuardConfirmed: true`（控制台开启用完即停）且配置非空 `models` 列表。仅限北京地域。额度手填标明未核实；遇到 403 `FreeTierOnly` 停用当天。 | `DASHSCOPE_API_KEY` |

---

## 插件配置参考

可以在 dsh 的「设置 &rarr; 插件 &rarr; DSH FreeModel」配置面板中调整以下参数：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `providers.<channel>.enabled` | `boolean` | `true` (openrouter)<br>`false` (其他) | 渠道启用开关。 |
| `providers.<channel>.apiKeyEnv` | `string` | 各渠道默认名 | 存放该渠道 API Key 的环境变量名称。 |
| `providers.groq.freePlanConfirmed` | `boolean` | `false` | 确认 Groq 账号属于免费计划（必勾）。 |
| `providers.sensenova.tokenPlanConfirmed` | `boolean` | `false` | 确认处于商汤 SenseNova Token Plan 公测内（必勾）。 |
| `providers.sensenova.models` | `string[]` | `[]` | 模型允许列表。留空时与目录交集获取全部价格为 `"0"` 的模型。 |
| `providers.bailian.freeQuotaGuardConfirmed` | `boolean` | `false` | 确认已在阿里云百炼控制台开启「免费额度用完即停」（必勾）。 |
| `providers.bailian.models` | `array` | `[]` | 允许的模型对象列表 `{ id, quotaTokens }`。手填额度显示为未核实。 |
| `autoRoute.enabled` | `boolean` | `false` | 启用 `freemodel-auto` (`best`) 自动路由，支持进程内故障转移。 |
| `autoDefaultModel` | `boolean` | `false` | 启用自动同步当前 profile 默认模型（`agent-default-model`），带多重安全防护。 |
| `ranking.weights.*` | `number` | spec 默认值 | 排名权重配置（首字延迟、上下文长度、工具调用、视觉能力、推理思考）。 |
| `ranking.capacityPenalty` | `number` | `20` | 模型每次发生排队/无容量时扣减的分数。 |
| `ranking.capacityDowngradeAfter` | `number` | `3` | 连续排队失败达到此次数后自动移出候选。 |
| `refresh.intervalM` | `number` | `60` | 后台定时刷新目录与探测的时间间隔（分钟）。 |
| `refresh.maxTestsPerRound` | `number` | `5` | 单轮刷新每个渠道最多执行的主动探测次数。 |
| `refresh.dailyReserve` | `number` | `10` | 每日保留的免费请求底线余量，避免耗尽额度影响日常对话。 |
| `manual[]` | `array` | `[]` | 第二层手动登记列表（用于记录 ZCode、Qoder、WorkBuddy 模型）。 |
| `manualProbe.enabled` | `boolean` | `false` | 手动登记模型探测总开关，默认关闭。 |

---

## 安全规则与防护机制

1. **绝对不泄露密钥（Zero Secret Leakage）**：
   - 密钥仅在运行时由 dsh 核心凭据服务 `ctx.credentials` 按需解析。
   - 插件配置文件与状态文件（`$DSH_HOME/freemodel/state.json`）**绝不保存密钥明文**。
   - 发生错误时，所有错误日志和状态消息均对可能的密钥片段进行打码脱敏。
   - 在文档和测试中，假密钥禁止使用形如真实密钥的字符串（严禁出现 `sk-` 后跟 20 位以上字符）。

2. **默认模型切换护栏（`autoDefaultModel`）**：
   - **默认关闭**：必须在插件设置中显式勾选开启。
   - **QQ / 机器人 Profile 保护**：严禁修改任何 QQ 或聊天机器人 Profile 的默认模型。凡是名称命中正则 `/qq|bot|astrbot|napcat|onebot/i` 的 Profile，一律拒绝并跳过。
   - **禁止触碰全局 Home 层**：严禁修改全局 `$DSH_HOME/cordis.patch.yml`，插件仅针对具体 profile 的 patch 文件。
   - **环境变量二次确认**：即使设置中开启了该选项，也必须在环境变量中设置 `DSH_FREEMODEL_APPLY_DEFAULT=1` 才会真正写入磁盘；未设置时仅在日志中输出 `would-write`，不做任何磁盘更改。
   - **Profile 布局**：Profile patch 文件位于 `$DSH_HOME/profiles/<id>/cordis.patch.yml`（即 profile 目录加 `cordis.patch.yml`，与 `profileContext` 一致）。已在 Linux 上真实 dsh 0.2.1-rc.3 的 home 中核对；其他平台未测试。

3. **自动路由故障转移规则（`freemodel-auto`）**：
   - 自动路由目标始终指向主动探测通过的渠道模型中排名最高的第 1 位模型。
   - **输出前平滑切换**：若候选模型在返回流中发生终端错误，且**尚未向调用方吐出任何可见字符**，适配器将在进程内自动切换至排名第 2 的候选模型重新发起。
   - **禁止输出中途切换**：一旦有任何可见字符 token 已经吐出，严禁中途切换模型，以避免输出内容前后矛盾错乱。中途发生的流中断将作为终端错误抛出。
   - 手动登记（Tier-2）模型**绝不**进入 `freemodel-auto` 自动路由候选池。

4. **本地回环与接口安全隔离**：
   - 插件内置 HTTP 接口（`/freemodel/api/*`）严格绑定在本机回环地址（`127.0.0.1`、`::1`）。
   - 写操作（手动单点探测、缓存失效）必须通过凭证校验：CLI 调用方使用磁盘上的 secret 文件（权限 0600），前端卡片使用回环状态数据分发的进程内临时令牌。

---

## 第二层手动登记（Tier-2 Manual Registry）

`manual[]` 配置允许用户在不进行逆向工程、不架设反向代理的前提下，集中登记第三方插件引入的模型（如 ZCode、Qoder、WorkBuddy）：

- **仅记录公开元数据**：接收 `provider`、`model`、`displayName`、`quotaNotes` 和 `expiresAt`。
- **强制拒绝敏感信息**：数据模型校验严格拒绝 `token`、`apiKey`、`password`、`cookie`、`secret`、`pat` 等凭据字段及疑似密钥格式的字符串。
- **不参与自动模型调度**：手动登记条目不会进入 `freemodel-auto` 或自动排名挑选流程。
- **极其克制的探测策略**：仅在同时打开 `manualProbe.enabled` 和单个条目的 `probe: true` 时，才经由 `ctx.llm` 发送单条 `ping` 测试；硬性限制每个模型每个 UTC 自然日最多探测 1 次；若返回账号类封锁错误（如 WorkBuddy `11140`），当天立即停止对该平台的探测。

---

## 设置卡片与管理界面

插件附带的浏览器卡片扩展（`lib/client.js`）在 dsh 设置面板的 FreeModel 页面上挂载包含五个标签栏的可视化卡片：

1. **概览（Overview）**：展示插件版本号（`1.0.0`）、规则版本、状态文件路径、各渠道启用数、已列出/隐藏模型数及今日已消耗探测次数。
2. **渠道（Channels）**：各渠道开启状态、密钥来源（`file`、`env` 等，绝不显示密钥）、接口地址、目录同步时间及限流暂停倒计时。
3. **模型（Models）**：已列出的可用模型及其能力徽标、额度信息与响应延迟；未列出的隐藏模型及其具体失败原因；每个模型右侧均有「立即测试」按钮。
4. **手动登记（Manual）**：展示已配置的手动条目、对应 dsh 路由是否已检测到、到期状态以及最近一次六字段探测结果。
5. **诊断（Diagnostics）**：数据格式版本号、本地 API 前缀、目录加载错误、提前中止记录以及 `dsh-freemodel doctor` 建议。

> [!NOTE]
**界面截图**（中文界面，按栏目顺序）：在新建的 dsh profile 上安装插件后，用 headless Chrome **断网**截取，且没有手动填写任何 key。"已配置"仅表示环境变量或 dsh 凭据库里已有对应 key；因为没有网络，目录为空并显示目录获取失败。图片只保留在仓库里，不在 npm 包内（`screenshots.json` 登记了英文和中文共 10 张）。

| 概览 | 渠道 |
| --- | --- |
| ![概览](https://raw.githubusercontent.com/ndwlbj/freemodel-sync/main/plugins/dsh-freemodel/docs/assets/dsh-freemodel-card-zh-overview.png) | ![渠道](https://raw.githubusercontent.com/ndwlbj/freemodel-sync/main/plugins/dsh-freemodel/docs/assets/dsh-freemodel-card-zh-channels.png) |

| 模型 | 手动登记 | 诊断 |
| --- | --- | --- |
| ![模型](https://raw.githubusercontent.com/ndwlbj/freemodel-sync/main/plugins/dsh-freemodel/docs/assets/dsh-freemodel-card-zh-models.png) | ![手动登记](https://raw.githubusercontent.com/ndwlbj/freemodel-sync/main/plugins/dsh-freemodel/docs/assets/dsh-freemodel-card-zh-manual.png) | ![诊断](https://raw.githubusercontent.com/ndwlbj/freemodel-sync/main/plugins/dsh-freemodel/docs/assets/dsh-freemodel-card-zh-diagnostics.png) |

---

## 命令行与会话斜杠命令

### 命令行工具

通过 `dsh plugin exec` 调用：

```bash
# 查看插件完整状态摘要（渠道、模型、密钥状态、状态文件）
dsh plugin --profile <profile> exec dsh-freemodel status

# 输出机器可读的 JSON 状态格式
dsh plugin --profile <profile> exec dsh-freemodel status --json

# 运行环境诊断（Node 版本、dsh 宿主版本兼容性、spec 规则校验）
dsh plugin --profile <profile> exec dsh-freemodel doctor
```

### 会话内斜杠命令

在任意 dsh 会话输入框中：

- `/freemodel`：查看当前渠道与可用模型概况。
- `/freemodel refresh`：立即触发一次目录重载与模型探测轮次。
- `/freemodel test <channel> <model>`：对指定渠道的模型发起单次手动测试。

---

## 故障排查与说明

- **选择器中未显示免费模型**：
  - 运行 `dsh-freemodel status` 检查对应渠道的密钥是否已被检测到；
  - 在设置卡片的「模型」栏中查看该模型被隐藏的具体原因（如超时、未在白名单、容量降级等）；
  - 确认 Groq 是否已勾选 `freePlanConfirmed`；
  - 确认 SenseNova 是否已勾选 `tokenPlanConfirmed`；
  - 确认百炼是否已勾选 `freeQuotaGuardConfirmed` 且 `models` 白名单非空。
- **探测提前停止**：
  - 插件遵守 `refresh.maxTestsPerRound`（默认 5 次）与 `refresh.dailyReserve`（默认保留 10 次额度给用户对话）。
- **默认模型未自动切换**：
  - 检查设置中是否开启了 `autoDefaultModel`；
  - 确认目标 profile 名称未命中机器人关键字（如 `qq`、`bot`、`astrbot` 等）；
  - 确认宿主环境中已导出 `DSH_FREEMODEL_APPLY_DEFAULT=1`。
- **真实设备测试情况**：
  - 已在 Linux (dsh 0.2.1-rc.3) 上验证；未在 Windows / macOS 真实设备上运行测试。
- **发布状态**：
  - 当前版本 1.0.0 处于内部测试阶段，未发布至 npm 仓库。

---

## 开源协议

MIT
