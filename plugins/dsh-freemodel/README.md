# dsh-freemodel

A [dsh](https://www.npmjs.com/package/@deepseek-ai/dsh) plugin for free models
from OpenRouter (`:free` models) and, opt-in, Groq's free plan. It is the dsh
side of [freemodel-sync](https://github.com/ndwlbj/freemodel-sync) and reads the
same rules from the repository's `spec/` (bundled at build time).

**0.1.0 is a skeleton.** It loads in dsh, shows its settings (channels and the
names of the key variables) and reports their state. It does not list, probe or
route any model yet, and it never changes dsh's default model. Not published to
npm.

- **Keys** are never stored in the plugin's settings. Each channel has a
  credential reference (`apiKeyEnv`, default `OPENROUTER_API_KEY` /
  `GROQ_API_KEY`); the key itself goes into dsh's credential store from the
  settings page, or comes from the environment.
- **Groq** is off by default and stays blocked until `freePlanConfirmed` is
  set, because its free plan is a property of the account, not of the model.
- `dsh-freemodel status` and `dsh-freemodel doctor [--json]` print the state
  and check Node.js, the dsh version, the bundled spec and whether the key
  variables are set. They never print a key.

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
**0.1.0 只是骨架**：能在 dsh 里加载、显示设置（渠道开关和 key 变量名）并报告状态，
还不会列出、探测或路由模型，也绝不改 dsh 的默认模型；不发布到 npm。key 只保存在
dsh 凭据库（设置页里填）或环境变量中，插件设置里只存变量名。Groq 默认关闭，且须打开
`freePlanConfirmed` 才会启用。`dsh-freemodel status` / `doctor` 用于自检，不会输出 key。

MIT licensed.
