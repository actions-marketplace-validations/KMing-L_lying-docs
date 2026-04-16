# Configuration

LyingDocs loads configuration from multiple sources in the following order, with later sources overriding earlier ones:

1. **Built-in defaults** (OpenAI API, gpt-5.4)
2. **Config file** — `lyingdocs.toml` in the project root, or `~/.config/lyingdocs/config.toml`
3. **Environment variables** / `.env`
4. **CLI arguments**

Hermes and Argus are configured independently, so you can use:

- a cheaper planning model for Hermes
- a stronger coding / investigation model for Argus
- different providers or endpoints for each agent

---

## Config file

Example configs live in [tests/configs](../tests/configs).

```toml
[hermes]
provider = "openai"         # "openai" | "anthropic"
model = "gpt-5.4"
base_url = "https://api.openai.com/v1"
# api_key_env = "OPENAI_API_KEY"  # optional — auto-set to ANTHROPIC_API_KEY when provider = "anthropic"

[argus]
backend = "local"           # "codex" | "claude_code" | "local"
provider = "openai"         # "openai" | "anthropic" (only used when backend = "local")
model = "gpt-5.4"
base_url = "https://api.openai.com/v1"
# api_key_env = "OPENAI_API_KEY"

# Only read when argus.backend = "codex"
[argus.codex]
provider = "openai"
wire_api = "responses"
# path = "/usr/local/bin/codex"   # optional: explicit codex binary path

# Only read when argus.backend = "claude_code"
[argus.claude_code]
# path = "/usr/local/bin/claude"  # optional: explicit claude binary path

# Only read when argus.backend = "local"
[argus.local]
max_iterations = 25         # per-task agent loop cap
max_read_bytes = 200000     # per read_file call

[limits]
max_dispatches = 20         # max Argus dispatches per Hermes run
max_iterations = 50         # max Hermes loop iterations
argus_task_timeout = 1200   # seconds per Argus task (codex / claude_code backends)
token_budget = 524288       # Hermes context budget before compression
```

---

## Environment variables

| Variable                 | Description                                    |
| ------------------------ | ---------------------------------------------- |
| `OPENAI_API_KEY`         | Required for OpenAI provider                   |
| `ANTHROPIC_API_KEY`      | Required for Anthropic provider                |
| `HERMES_PROVIDER`        | `openai` or `anthropic`                        |
| `HERMES_MODEL`           | Hermes model name                              |
| `HERMES_BASE_URL`        | Hermes API base URL                            |
| `ARGUS_PROVIDER`         | `openai` or `anthropic` (local backend only)   |
| `ARGUS_BACKEND`          | `codex`, `claude_code`, or `local`             |
| `ARGUS_MODEL`            | Argus model name                               |
| `ARGUS_BASE_URL`         | Argus API base URL                             |
| `ARGUS_CODEX_PROVIDER`   | Codex backend provider                         |
| `ARGUS_CODEX_WIRE_API`   | Codex backend wire API (`responses` or `chat`) |
| `ARGUS_CODEX_PATH`       | Explicit path to `codex`                       |
| `ARGUS_CLAUDE_CODE_PATH` | Explicit path to `claude`                      |
| `ARGUS_TASK_TIMEOUT`     | Timeout per Argus task in seconds              |
| `TOKEN_BUDGET`           | Hermes context budget before compression       |
