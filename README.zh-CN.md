# freemodel-sync

[![CI](https://github.com/ghwghw19/freemodel-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/ghwghw19/freemodel-sync/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

[English](https://github.com/ghwghw19/freemodel-sync/blob/main/README.md) | [简体中文](https://github.com/ghwghw19/freemodel-sync/blob/main/README.zh-CN.md)

**自动发现、测试、排名免费大模型，再把排名最高且能用的那个（加上备用列表）写进你正在用的工具配置里。**

免费模型变化很快：新增、限流、下线，或者悄悄开始收费。`freemodel-sync` 把你的机器人和脚本指向一个最近探测通过的免费模型，但无法保证两次运行之间它一直可用。

> **不是代理。** freemodel-sync 不经手、不转发你的任何请求，只负责修改配置文件（先备份），然后就退出。你的工具仍然直接连接模型服务商。

## 工作流程

```
发现 ──► 过滤 ──► 探测（极小请求、带缓存、有额度预算）──► 排名 ──► 选择 ──► 写配置 ──► 通知
```

1. **发现**：从 OpenRouter 公开模型列表（`GET /api/v1/models`，无需 key）拉取。只有同时满足以下条件才算免费：id 以 `:free` 结尾、输入和输出价格都是 `0`、支持文本输入输出。排除 `openrouter/free` 这类路由器。
2. **过滤**：按是否支持工具调用、最小上下文长度、id 通配符、到期时间过滤。`expiration_date` 在 N 天内的模型直接排除，30 天内到期的会被扣分。
3. **探测**：用**你自己的** OpenRouter key 给每个候选发一条极小的流式请求（默认 `max_tokens: 16`，可用 `providers.openrouter.probe_max_tokens` 修改），测可用性和首字延迟。非常节省：按潜力从高到低测；结果默认缓存 6 小时；每次最多新测 `max_tests` 个；额度以 `GET /api/v1/key` 返回的 `free_model_daily_requests.remaining`（按 UTC 日计；按撰写时 OpenRouter 文档，累计购买不足 10 credits 每天 50 次，以上 1000 次）为准，并预留 `reserve_requests` 次给你的日常使用。接口没返回额度时，按保守的每天 50 次、用本地 UTC 日计数。
   - **账号问题不算模型故障。** 遇到 401/402/403 或 OpenRouter 平台级 429（免费模型每分钟/每日上限），这一次请求后立即停止本轮，不会把模型记成失败；`Retry-After` / `X-RateLimit-Reset` 会让之后的运行等到重置时间再探测。上游服务商的 429、5xx 和超时算临时失败，`transient_ttl_minutes`（默认 30 分钟）后重试。
   - 没有 API key 时，`test`、`rank`、`sync` 直接报错退出，不发任何请求。
4. **排名**：可解释的打分（可用性 ≫ 延迟、上下文、工具支持、到期时间）。备用模型只取探测通过的；只有设置 `ranking.fallbacks_allow_untested: true` 才会用未测试的模型补位，并标注 `(untested)`。非对话模型（安全分类器、embedding、rerank、语音）默认排除。
5. **写入**：把主模型和备用列表写进每个配置目标。每次写入都是幂等的（没变化就不动文件），支持 `--dry-run` 显示 diff，写前生成带时间戳的 `*.bak-*` 备份（权限 0600 或更严，默认只保留最新 5 份，见 `backups`），并原子替换文件。如果没有任何模型通过探测，**不会写任何文件**。
6. **通知**（可选）：主模型变化时通过 Telegram 或通用 webhook 通知。只要有一个目标写入失败，就以退出码 `1` 结束，不更新记录的状态，也不发通知；下次运行会重试。

## 安装

```bash
pipx install freemodel-sync              # 从 PyPI 安装（需要已有版本发布到 PyPI）
pipx install git+https://github.com/ghwghw19/freemodel-sync
# 或者免安装直接运行
uvx --from git+https://github.com/ghwghw19/freemodel-sync freemodel-sync --help
# 本地源码
pipx install .
```

需要 Python 3.9+（Python 3.9 已停止维护，计划从 0.3.0 起要求 3.10+），运行依赖只有 `httpx` 和 `PyYAML`。

## 快速开始

```bash
export OPENROUTER_API_KEY=...            # 你自己的 key，只从环境变量读取
freemodel-sync discover                  # 列出免费模型（不需要 key）
freemodel-sync test --max-tests 3        # 探测最有潜力的 3 个
freemodel-sync rank --json               # 输出完整排名和选择结果（JSON）
cp examples/config.example.yml ~/.config/freemodel-sync/config.yml   # 然后编辑 targets
freemodel-sync sync --dry-run            # 只看 diff
freemodel-sync sync                      # 写配置，有变化时通知
```

可以用 cron 或 systemd timer 定时运行，例如每 3 小时一次。不要把 key 写进 crontab：把 `export OPENROUTER_API_KEY=...` 放进只有你能读的文件（`chmod 600 ~/.config/freemodel-sync/env`）再 source，或者在 systemd 里用 `EnvironmentFile=`。

```cron
0 */3 * * * . "$HOME/.config/freemodel-sync/env" && freemodel-sync sync >> "$HOME/.cache/freemodel-sync/sync.log" 2>&1
```

退出码：`0` 成功；`1` 出错（配置错误、没有 key、某个目标写入失败）；`2` 没有可用模型（不写任何文件）；`3` 探测因账号/额度问题被中止，例如平台限流或余额不足（不写任何文件，也不会把模型记成失败）；`4` 另一次运行还没结束（`test`、`rank`、`sync` 会在 state 文件旁加锁，cron 重叠时不会重复探测）。

`sync --dry-run` 不产生任何额度消耗：只使用之前 `test`/`sync` 留下的缓存探测结果，不发送聊天请求和 `/key` 请求，不需要 API key，也不写目标文件、state 或缓存（仍会获取公开的模型列表）。如果想在 dry run 时照常探测，加 `--probe`（会消耗免费额度并更新缓存）。`rank --no-probe` 和 `sync --no-probe` 同样只用缓存结果。

## 配置

默认路径 `~/.config/freemodel-sync/config.yml`（可用 `-c FILE` 或 `$FREEMODEL_SYNC_CONFIG` 指定）。所有字段都是可选的，完整带注释的示例见 [`examples/config.example.yml`](https://github.com/ghwghw19/freemodel-sync/blob/main/examples/config.example.yml)。

## 配置目标（适配器）

| 适配器 | 文件 | 写入内容 |
| --- | --- | --- |
| `openai-env` | `KEY=VALUE` 环境变量文件 | `OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_FALLBACK_MODELS`（变量名可配置）。`OPENAI_FALLBACK_MODELS` 不是通用变量，需要你的工具自己去读。其他行、注释和你的 API key 都不动。 |
| `openai-yaml` | 任意 YAML 文件 | 在点分路径 `key_path`（默认 `llm`）下写 `base_url`、`model`、`fallback_models`。 |
| `dsh` | dsh（DeepSeek Harness）`cordis.patch.yml` 风格的列表 | 只替换 `agent-default-model` 这一项为 `config: {provider: <p>, model: '<m>'}`，其他条目和注释原样保留。用 `provider_map` 把 `openrouter` 映射成你 dsh 里的 provider id。该条目 `config` 里已有的其他键（如 `reasoningEffort`）和 `name` 会保留；`entry_name` 可指定 name。dsh 没有备用列表条目，所以不写备用模型（`fallback_entry_id` 已废弃并被忽略）。 |
| `astrbot`（实验性） | AstrBot 的 `data/cmd_config.json` | 只更新**已存在**的 provider（`provider_id`）的模型：AstrBot ≥ 4.10（`provider_sources` 结构）写条目顶层的 `model`，旧版本写 `model_config.model`。不会新建 provider，也不碰 key 和 provider source。 |

`dsh` 写入效果示例：

```yaml
- id: agent-default-model
  config: {provider: openrouter, model: 'vendor/some-model:free'}
```

### 已知限制

- **AstrBot**：两种结构都对照 AstrBot 源码（v4.29.1）核对过；两种都不匹配时会直接报错，不会静默跳过。AstrBot 运行时把配置放在内存里，WebUI 保存时会覆盖文件，所以**同步后要重启 AstrBot**（也不要同时在 WebUI 里改）。provider 条目没有备用列表，只写主模型；对应到 AstrBot 的 `fallback_provider_ids` 还没实现。
- **YAML 注释**：`openai-yaml` 使用 PyYAML，值发生变化时注释会丢失（值没变时不会重写文件）。`dsh` 适配器会保留注释。
- **分时段价格**：`:free` 模型的 `pricing.overrides` 里只要有非零价格（比如高峰时段或长上下文），就会被跳过并给出警告。
- **免费额度**：每日预算来自 `free_model_daily_requests`，不再根据 `is_free_tier` 推断；可用 `testing.daily_free_limit` 覆盖（按 UTC 日计数）。
- 本版本只实现了 OpenRouter（见下文）。

## 通知

- **Telegram**：配置 `notify.telegram`，并设置环境变量 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`。
- **Webhook**（例如 QQ 机器人桥接）：配置 `notify.webhook.url_env`（默认 `FREEMODEL_SYNC_WEBHOOK_URL`）。webhook URL 通常带 token，请放在环境变量里：直接写 `notify.webhook.url` 也能用，但会给出警告；配置文件对其他用户可读时还会再警告一次。POST 内容为 `{"event": "primary_changed", "old", "new", "fallbacks", "text"}`。

通知失败只记日志（不含 token 和完整 URL），不会导致同步失败。

## 编写 provider 插件

继承 `Provider`，实现 `discover()` 和 `test()`（可选 `quota()`），然后注册：

```python
from freemodel_sync.providers import Provider, register_provider

@register_provider
class MyProvider(Provider):
    name = "myprovider"
    base_url = "https://api.example.com/v1"
    api_key_env = "MYPROVIDER_API_KEY"

    def discover(self): ...
    def test(self, model, timeout=30.0): ...
```

以后可能支持（尚未实现，没有时间表）：硅基流动、智谱 GLM Flash、Groq、Google Gemini。适配器也是同样的插件方式（`freemodel_sync.adapters.base.Adapter` + `register_adapter`）。

## 开发

```bash
python -m pip install -e ".[dev]"
ruff check src tests
pytest
```

测试完全不联网（HTTP 用 `httpx.MockTransport` 模拟）。贡献指南见 [CONTRIBUTING.md](https://github.com/ghwghw19/freemodel-sync/blob/main/CONTRIBUTING.md)。

## 安全

私下报告漏洞的方式见 [SECURITY.md](https://github.com/ghwghw19/freemodel-sync/blob/main/SECURITY.md)。

- key 只从环境变量读取，freemodel-sync 不会把它写进配置文件，也不会打印。日志（包括 `-v`）会遮蔽 Telegram bot token、Bearer token 和 `sk-` 形式的 key；HTTP 请求日志（`--debug-http`）默认关闭。
- 目标文件是符号链接时会写入真实文件（先备份），链接本身保留。
- 不要提交你的 `config.yml`、`.env`、备份文件或缓存；`.gitignore` 已覆盖默认文件名。

## 许可证

[MIT](https://github.com/ghwghw19/freemodel-sync/blob/main/LICENSE) © freemodel-sync contributors
