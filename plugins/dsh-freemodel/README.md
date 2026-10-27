# dsh-freemodel

A [dsh](https://www.npmjs.com/package/@deepseek-ai/dsh) plugin for free models
from OpenRouter (`:free` models) and, opt-in, Groq's free plan. It is the dsh
side of [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) and reads the
same rules from the repository's `spec/` (bundled at build time).

Once a channel has a key it reads the provider's catalogue, keeps the models
that are free by the shared rules, probes the best-ranked ones and lists those
that answered in dsh's model picker, labelled `· 免费`, under the routes
`freemodel-openrouter` and `freemodel-groq`. Models that fail a probe are
hidden; the reason is in `dsh-freemodel status`. Results are kept in
`$DSH_HOME/freemodel/state.json` (mode 600, never a key) and refreshed on a
schedule (`refresh.*`). It never changes dsh's default model. Not published to
npm.

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

```bash
# from this directory (needs pnpm 10; npm 10 cannot install these peers)
pnpm install --frozen-lockfile
pnpm run check            # typecheck + tests
pnpm run build && pnpm pack
dsh plugin --profile <test profile> add ./dsh-freemodel-0.1.0.tgz
dsh plugin --profile <test profile> exec dsh-freemodel doctor
```

Requires Node.js `^22.19.0 || >=24.0.0` and dsh `>=0.2.1-rc.1 <0.3.0-0`.
`scripts/verify-host/verify-host.sh` checks the plugin inside a real dsh in a
throwaway home; see `docs/dsh-plugin-verification.md` in the repository.

## 中文

dsh 插件：OpenRouter 的 `:free` 免费模型，以及需手动开启的 Groq 免费计划。
渠道配好 key 后，插件读取目录、按共享规则筛出免费模型、探测排名靠前的几个，把通过的
模型以「· 免费」标签列进 dsh 的模型选择器（路由 `freemodel-openrouter` / `freemodel-groq`）。
未通过探测的模型会隐藏，原因可用 `dsh-freemodel status` 查看。结果存于
`$DSH_HOME/freemodel/state.json`（权限 600，不含 key），按 `refresh.*` 定时刷新。
绝不改 dsh 的默认模型；不发布到 npm。key 只保存在
dsh 凭据库（设置页里填）或环境变量中，插件设置里只存变量名。Groq 默认关闭，且须打开
`freePlanConfirmed` 才会启用。`dsh-freemodel status` / `doctor` 用于自检，不会输出 key。

MIT licensed.
