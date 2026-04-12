<p align="center">
  <img src="assets/logo.png" alt="lyingdocs" width="200" />
</p>

<h1 align="center">LyingDocs</h1>

<p align="center">
  Your docs are lying. Here's how to find out.
</p>

---

Every codebase has them: features documented but never shipped, behavior that quietly diverged from the spec, values claimed to be configurable that are hardcoded deep in a function nobody reads. In the age of Vibe Coding, developers ship both code and docs through LLMs — fast, fluid, and increasingly misaligned.

LyingDocs deploys two autonomous agents against your repository to surface these inconsistencies before your users do.

---

## How it works

**Hermes** autonomously traverses your documentation, plans an audit strategy, and dispatches targeted analysis tasks.

**Argus** executes each task against your actual codebase, reporting what the code *really* does. You choose how Argus investigates the code — pick the backend that fits your setup:

- **`codex`** — [OpenAI Codex CLI](https://github.com/openai/codex) subprocess
- **`claude_code`** — [Claude Code](https://docs.anthropic.com/claude/docs/claude-code) CLI subprocess (`claude -p`)
- **`local`** — a built-in minimal agent loop that uses filesystem tools and calls any OpenAI-compatible API directly (no external CLI required)

Hermes reconciles the two — and writes you a report.

---

## Installation

```bash
pip install lyingdocs
```

## Quick Start

```bash
export OPENAI_API_KEY="sk-..."

lyingdocs analyze --doc-path docs/ --code-path . -o output/audit
```

## Configuration

LyingDocs loads configuration from multiple sources (later overrides earlier):

1. **Built-in defaults** (OpenAI API, gpt-4o)
2. **Config file** — `lyingdocs.toml` in project root, or `~/.config/lyingdocs/config.toml`
3. **Environment variables** / `.env` file
4. **CLI arguments**

Hermes and Argus are configured independently, so you can run a cheaper planner model for Hermes and a stronger coder model for Argus (or point them at entirely different API endpoints).

### Config File Example

```toml
[hermes]
model = "gpt-5.4"
base_url = "https://api.openai.com/v1"
# api_key_env = "OPENAI_API_KEY"  # optional — defaults to OPENAI_API_KEY

[argus]
backend = "local"           # "codex" | "claude_code" | "local"
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

> **Note:** The previous flat format (top-level `model` / `base_url` and a `[codex]` section) is no longer supported. LyingDocs will exit with a clear migration error if it sees the old shape — move to `[hermes]` / `[argus]` as shown above.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | **Required.** API key used by both agents unless overridden via `api_key_env` |
| `HERMES_MODEL` | Hermes LLM model name |
| `HERMES_BASE_URL` | Hermes API base URL |
| `ARGUS_BACKEND` | `codex`, `claude_code`, or `local` |
| `ARGUS_MODEL` | Argus LLM model name |
| `ARGUS_BASE_URL` | Argus API base URL |
| `ARGUS_CODEX_PROVIDER` | Codex backend: provider name |
| `ARGUS_CODEX_WIRE_API` | Codex backend: provider wire_api (`responses` or `chat`) |
| `ARGUS_CODEX_PATH` | Codex backend: explicit path to the `codex` binary |
| `ARGUS_CLAUDE_CODE_PATH` | Claude Code backend: explicit path to the `claude` binary |
| `ARGUS_TASK_TIMEOUT` | Timeout per Argus task (seconds, used by codex / claude_code backends) |
| `TOKEN_BUDGET` | Hermes context tokens before compression |

---

## Argus Backends

Argus is the "deep code analysis" side of the pipeline. Pick one backend in `lyingdocs.toml` (or via `--argus-backend`):

### `local` (no external CLI required)

A built-in agent loop that uses `list_directory` / `read_file` / `search_code` / `finish` tools and calls any OpenAI-compatible chat completions API directly. Best for getting started — only needs an API key.

```toml
[argus]
backend = "local"
model = "gpt-5.4"
base_url = "https://api.openai.com/v1"
```

### `codex` ([OpenAI Codex CLI](https://github.com/openai/codex))

```bash
npm install -g @openai/codex
```

```toml
[argus]
backend = "codex"

[argus.codex]
provider = "openai"
wire_api = "responses"
# path = "/usr/local/bin/codex"  # optional
```

Codex is auto-detected in this order:
1. Explicit path from config (`argus.codex.path`)
2. System `PATH` (`which codex`)
3. Local `node_modules/.bin/codex`

### `claude_code` ([Claude Code](https://docs.anthropic.com/claude/docs/claude-code))

```toml
[argus]
backend = "claude_code"
model = "claude-sonnet-4-6"

[argus.claude_code]
# path = "/usr/local/bin/claude"  # optional; else resolved via PATH
```

Invoked as `claude -p <prompt> --model <argus_model> --output-format text` with `cwd` set to your code root.

---

## CLI Reference

```bash
# Full analysis
lyingdocs analyze --doc-path docs/ --code-path . -o output/audit

# Pick the Argus backend on the command line
lyingdocs analyze --doc-path docs/ --code-path . --argus-backend=local

# Different models for Hermes and Argus
lyingdocs analyze --doc-path docs/ --code-path . \
  --hermes-model gpt-4o-mini \
  --argus-model gpt-5.4

# Resume interrupted analysis
lyingdocs analyze --doc-path docs/ --code-path . --resume

# With explicit config file
lyingdocs analyze --doc-path docs/ --code-path . --config myconfig.toml

# Show version
lyingdocs version
```

Available flags: `--hermes-model`, `--hermes-base-url`, `--argus-backend {codex,claude_code,local}`, `--argus-model`, `--argus-base-url`, `--argus-codex-provider`, `--argus-codex-wire-api`, `--max-dispatches`, `--max-iterations`, `--config`, `--resume`.

---

## Misalignment Categories

| Category | Description |
|----------|-------------|
| **LogicMismatch** | Code contradicts documentation |
| **PhantomSpec** | Documentation describes non-existent features |
| **ShadowLogic** | Important undocumented code logic |
| **HardcodedDrift** | Supposedly configurable values that are hardcoded |

---

## Roadmap

- [x] **Multi-harness support** — Argus now runs on Codex, Claude Code, or a built-in local agent
- [ ] **Deeper analysis** — multi-hop reasoning across doc hierarchies; version-aware diffing to catch when code changed but docs didn't
- [ ] **Customization for papers** — a "paper mode" that treats academic papers as documentation and surfaces misalignments between paper claims and code behavior
- [ ] **Auto-fix mode** — Hermes proposes doc patches; you review and apply

---

## For Researchers 🔬

A paper is just another kind of documentation — a translation of code into human language, written under deadline, reviewed long after the implementation settled.

If you've ever wondered whether your repo can be used by other researchers, or whether there are misalignments between your paper and your code, LyingDocs can help you find out.

The problem is the same. Paper is documentation for code. LyingDocs is for papers too.

---

## License

MIT