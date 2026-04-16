# Argus Backends

Argus is the deep code analysis side of the system. It investigates the actual codebase against tasks dispatched by Hermes.

You can choose the backend that best fits your setup.

---

## `local`

No external CLI required. Uses a built-in agent loop with filesystem tools and an LLM API.

Good default for getting started. Supports both OpenAI and Anthropic as the LLM provider.

### With OpenAI (default)

```toml
[argus]
backend = "local"
provider = "openai"
model = "gpt-5.4"
base_url = "https://api.openai.com/v1"

[argus.local]
max_iterations = 25    # per-task agent loop cap
max_read_bytes = 200000
```

### With Anthropic

```toml
[argus]
backend = "local"
provider = "anthropic"
model = "claude-sonnet-4-6"

[argus.local]
max_iterations = 25
max_read_bytes = 200000
```

When `provider = "anthropic"`, the `api_key_env` automatically defaults to `ANTHROPIC_API_KEY` and `base_url` is not needed.

---

## `codex`

Uses [OpenAI Codex CLI](https://github.com/openai/codex).

```bash
npm install -g @openai/codex
```

```toml
[argus]
backend = "codex"

[argus.codex]
provider = "openai"
wire_api = "responses"
# path = "/usr/local/bin/codex"  # optional: explicit binary path
```

Binary resolution order:

1. Explicit path from config (`argus.codex.path`)
2. System `PATH`
3. Local `node_modules/.bin/codex`

---

## `claude_code`

Uses [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI subprocess.

```toml
[argus]
backend = "claude_code"
model = "claude-sonnet-4-6"

[argus.claude_code]
# path = "/usr/local/bin/claude"  # optional: explicit binary path
```

Invoked as:

```bash
claude -p <prompt> --model <argus_model> --output-format text
```

with `cwd` set to your code root.

---

## Hermes provider

Hermes (the planner agent) also supports both OpenAI and Anthropic as its LLM provider, independently from Argus:

```toml
[hermes]
provider = "anthropic"
model = "claude-sonnet-4-6"
```

This means you can run the entire LyingDocs pipeline using only an Anthropic API key:

```toml
[hermes]
provider = "anthropic"
model = "claude-sonnet-4-6"

[argus]
backend = "claude_code"
model = "claude-sonnet-4-6"
```

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
lyingdocs analyze --doc-path docs/ --code-path .
```

In CI, when `backend: claude_code` (without `--claude-oauth`), Hermes defaults to `anthropic` — so you only need one secret (`ANTHROPIC_API_KEY`). When using `--claude-oauth`, Hermes defaults to `openai` to avoid requiring an Anthropic API key alongside the OAuth token. You can override this with `--hermes-provider`.
