# freemodel-sync

[English](README.md) | [简体中文](README.zh-CN.md)

**自动发现、测试、排名免费大模型，再把最好的那个（加上备用列表）写进你正在用的工具配置里。**

免费模型变化很快：新增、限流、下线，或者悄悄开始收费。`freemodel-sync` 让你的机器人和脚本始终指向一个今天真的能用的免费模型。

> **不是代理。** freemodel-sync 不经手、不转发你的任何请求，只负责修改配置文件（先备份），然后就退出。你的工具仍然直接连接模型服务商。

## 工作流程

```
发现 ──► 过滤 ──► 探测（极小请求、带缓存、有额度预算）──► 排名 ──► 选择 ──► 写配置 ──► 通知
```

1. **发现**：从 OpenRouter 公开模型列表（`GET /api/v1/models`，无需 key）拉取。只有同时满足以下条件才算免费：id 以 `:free` 结尾、输入和输出价格都是 `0`、支持文本输入输出。排除 `openrouter/free` 这类路由器。
2. **过滤**：按是否支持工具调用、最小上下文长度、id 通配符、到期时间过滤。`expiration_date` 在 N 天内的模型直接排除，30 天内到期的会被扣分。
3. **探测**：用**你自己的** OpenRouter key 给每个候选发一条极小的流式请求（`max_tokens: 8`），测可用性和首字延迟。非常节省：按潜力从高到低测；结果默认缓存 6 小时；每次最多新测 `max_tests` 个；每日计数器会参考 `GET /api/v1/key` 返回的免费额度（每天 50 次，购买过 ≥10 credits 后为 1000 次）并预留一部分给你的日常使用。
4. **排名**：可解释的打分（可用性 ≫ 延迟、上下文、工具支持、到期时间）。
5. **写入**：把主模型和备用列表写进每个配置目标。每次写入都是幂等的（没变化就不动文件），支持 `--dry-run` 显示 diff，写前生成带时间戳的 `*.bak-*` 备份，并原子替换文件。如果没有任何模型通过探测，**不会写任何文件**。
6. **通知**（可选）：主模型变化时通过 Telegram 或通用 webhook 通知。

## 安装

```bash
pipx install git+https://github.com/ghwghw19/freemodel-sync
# 或者免安装直接运行
uvx --from git+https://github.com/ghwghw19/freemodel-sync freemodel-sync --help
# 本地源码
pipx install .
```

需要 Python 3.9+，运行依赖只有 `httpx` 和 `PyYAML`。

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

可以用 cron 或 systemd timer 定时运行，例如每 3 小时一次：

```cron
0 */3 * * * OPENROUTER_API_KEY=... freemodel-sync sync >> ~/.cache/freemodel-sync/sync.log 2>&1
```

退出码：`0` 成功；`1` 出错（配置错误、某个目标写入失败）；`2` 没有可用模型（不写任何文件）。

## 配置

默认路径 `~/.config/freemodel-sync/config.yml`（可用 `-c FILE` 或 `$FREEMODEL_SYNC_CONFIG` 指定）。所有字段都是可选的，完整带注释的示例见 [`examples/config.example.yml`](examples/config.example.yml)。

## 配置目标（适配器）

| 适配器 | 文件 | 写入内容 |
| --- | --- | --- |
| `openai-env` | `KEY=VALUE` 环境变量文件 | `OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_FALLBACK_MODELS`（变量名可配置）。其他行、注释和你的 API key 都不动。 |
| `openai-yaml` | 任意 YAML 文件 | 在点分路径 `key_path`（默认 `llm`）下写 `base_url`、`model`、`fallback_models`。 |
| `dsh` | dsh（DeepSeek Harness）`cordis.patch.yml` 风格的列表 | 只替换 `agent-default-model` 这一项为 `config: {provider: <p>, model: '<m>'}`，其他条目和注释原样保留。用 `provider_map` 把 `openrouter` 映射成你 dsh 里的 provider id。可选 `fallback_entry_id` 把备用列表写成单独一项。 |
| `astrbot`（实验性） | AstrBot 的 `data/cmd_config.json` | 只更新**已存在**的 provider（`provider_id`）的 `model_config.model`，不会新建 provider，也不碰 key。 |

`dsh` 写入效果示例：

```yaml
- id: agent-default-model
  config: {provider: openrouter, model: 'vendor/some-model:free'}
```

### 已知限制

- **AstrBot**：按照文档中 `data/cmd_config.json` 的 `provider` 列表格式实现（`type: openai_chat_completion`、`model_config.model`）。新版 AstrBot（v4.x）通过 WebUI 管理 provider，存储方式可能不同，请在你的版本上确认，修改后需要重启 AstrBot。AstrBot 的 provider 没有备用模型列表，所以只写主模型。
- **YAML 注释**：`openai-yaml` 使用 PyYAML，值发生变化时注释会丢失（值没变时不会重写文件）。`dsh` 适配器会保留注释。
- **免费档判断**：OpenRouter 的 `is_free_tier` 无法区分是否购买过 ≥10 credits；如果判断不准，请设置 `testing.daily_free_limit`。
- 本版本只实现了 OpenRouter（见下文）。

## 通知

- **Telegram**：配置 `notify.telegram`，并设置环境变量 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`。
- **Webhook**（例如 QQ 机器人桥接）：配置 `notify.webhook.url_env`（默认 `FREEMODEL_SYNC_WEBHOOK_URL`）。POST 内容为 `{"event": "primary_changed", "old", "new", "fallbacks", "text"}`。

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

计划支持：硅基流动、智谱 GLM Flash、Groq、Google Gemini。适配器也是同样的插件方式（`freemodel_sync.adapters.base.Adapter` + `register_adapter`）。

## 开发

```bash
python -m pip install -e ".[dev]"
ruff check src tests
pytest
```

测试完全不联网（HTTP 用 `httpx.MockTransport` 模拟）。

## 安全

- key 只从环境变量读取，绝不写入、记录或打印。
- 不要提交你的 `config.yml`、`.env`、备份文件或缓存；`.gitignore` 已覆盖默认文件名。

## 许可证

[MIT](LICENSE) © freemodel-sync contributors
