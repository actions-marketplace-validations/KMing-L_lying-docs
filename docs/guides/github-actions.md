# GitHub Actions Integration

Run LyingDocs automatically in your CI pipeline to catch documentation-code misalignment as it's introduced.

---

## Quick start

### 1. Generate a workflow

```bash
lyingdocs init-ci --doc-path docs/ --code-path .
```

This creates `.github/workflows/lyingdocs.yml` configured to run on every PR and tag push.

### 2. Add your API key as a repository secret

Go to **Settings > Secrets and variables > Actions > New repository secret** and add the key for your chosen backend.

### 3. Commit and push

```bash
git add .github/workflows/lyingdocs.yml
git commit -m "ci: add LyingDocs trust audit"
git push
```

LyingDocs will now run automatically based on your configured triggers.

---

## Authentication

All credentials are stored in [GitHub Encrypted Secrets](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions) — never in your workflow file. The workflow references them via `${{ secrets.NAME }}`.

### By backend

| Backend | Secret(s) needed | How to get them |
| --- | --- | --- |
| `local` | `OPENAI_API_KEY` | [OpenAI API keys](https://platform.openai.com/api-keys) |
| `codex` | `OPENAI_API_KEY` | [OpenAI API keys](https://platform.openai.com/api-keys) |
| `claude_code` | `ANTHROPIC_API_KEY` | [Anthropic Console](https://console.anthropic.com/) |
| `claude_code` + OAuth | `OPENAI_API_KEY` + `CLAUDE_CODE_OAUTH_TOKEN` | [OpenAI API keys](https://platform.openai.com/api-keys); OAuth token from `claude setup-token` |

### Custom base URLs

For users with custom OpenAI-compatible endpoints (proxies, private deployments, etc.), set `OPENAI_BASE_URL` as a **repository variable** (Settings > Variables, not Secrets — it's not sensitive):

- When set, Hermes uses this URL instead of the official `https://api.openai.com/v1`
- When empty, the official default is used

### Claude Code: API Key vs OAuth Token

Claude Code supports two authentication methods in CI:

**API Key** (`ANTHROPIC_API_KEY`) — billed per API call. Only one key needed: both Hermes (planner) and Argus (code analyzer) use the Anthropic API automatically.

```bash
lyingdocs init-ci --doc-path docs/ --backend claude_code
```

**OAuth Token** (`CLAUDE_CODE_OAUTH_TOKEN`) — Argus (Claude Code CLI) uses your Pro/Max subscription quota for code analysis. Hermes defaults to OpenAI in this mode.

```bash
# Generate the token locally first
claude setup-token

# Then generate the workflow with --claude-oauth
lyingdocs init-ci --doc-path docs/ --backend claude_code --claude-oauth
```

Store the generated token as `CLAUDE_CODE_OAUTH_TOKEN` in your repo secrets.

> **How credentials and models map in each mode:**
>
> | Mode | Hermes | Argus | Secrets needed |
> | --- | --- | --- | --- |
> | `claude_code` | Anthropic (`claude-sonnet-4-6`) | Claude CLI (`claude-sonnet-4-6`) | `ANTHROPIC_API_KEY` |
> | `claude_code --claude-oauth` | OpenAI (`gpt-5.4`) | Claude CLI OAuth (`claude-sonnet-4-6`) | `OPENAI_API_KEY` + `CLAUDE_CODE_OAUTH_TOKEN` |
> | `claude_code --claude-oauth --hermes-provider anthropic` | Anthropic (`claude-sonnet-4-6`) | Claude CLI OAuth (`claude-sonnet-4-6`) | `ANTHROPIC_API_KEY` + `CLAUDE_CODE_OAUTH_TOKEN` |
> | `local` (default) | OpenAI (`gpt-5.4`) | OpenAI (`gpt-5.4`) | `OPENAI_API_KEY` |
> | `codex` | OpenAI (`gpt-5.4`) | Codex CLI (`gpt-5.4`) | `OPENAI_API_KEY` |
>
> Models are auto-selected based on the provider/backend. Override with `--hermes-model` and `--argus-model`.
> OAuth tokens only work with the Claude Code CLI — the Anthropic SDK requires an API key.
> Use `--hermes-provider` to override which provider Hermes uses.

---

## Controlling when LyingDocs runs

Use `--trigger` to control execution granularity:

```bash
# Every PR to main + every version tag (default)
lyingdocs init-ci --doc-path docs/ --trigger pr,tag

# Only on version tags (cheapest — good for large repos)
lyingdocs init-ci --doc-path docs/ --trigger tag

# Manual button only (full control)
lyingdocs init-ci --doc-path docs/ --trigger manual

# Tag + manual button
lyingdocs init-ci --doc-path docs/ --trigger tag,manual

# Weekly scheduled audit
lyingdocs init-ci --doc-path docs/ --trigger schedule --cron "0 9 * * 1"
```

### Available triggers

| Trigger | Description |
| --- | --- |
| `pr` | Runs on pull requests to the target branch |
| `tag` | Runs when a version tag (`v*`) is pushed |
| `manual` | Adds a "Run workflow" button in GitHub Actions UI |
| `schedule` | Runs on a cron schedule (configure with `--cron`) |

You can combine triggers with commas: `--trigger pr,tag,manual`.

### For large repositories

If your repo has many PRs and you don't want every one to trigger an audit:

- Use `--trigger tag` to only audit at release time
- Use `--trigger manual` to run on-demand
- Use `--trigger tag,manual` to get both

You can always edit the generated YAML later — the file includes commented-out trigger examples for reference.

---

## Manual approval

Add `--approval` to require human sign-off before findings are accepted:

```bash
lyingdocs init-ci --doc-path docs/ --trigger pr,tag --approval
```

This adds a `review` job that pauses and waits for approval. To configure it:

1. Go to **Settings > Environments > New environment**
2. Create an environment named `lyingdocs-review`
3. Under **Environment protection rules**, add **Required reviewers**
4. Add the team members who should approve findings

When the audit completes, the workflow pauses at the review step. Reviewers can see the full report in the GitHub Actions **Summary** tab before clicking Approve or Reject.

---

## PR comments

By default, LyingDocs posts findings as a PR comment when triggered by a `pull_request` event. The comment includes:

- Finding count with a status icon
- Full report in a collapsible `<details>` block
- Automatic update on re-runs (no comment spam)

To disable:

```bash
lyingdocs init-ci --doc-path docs/ --no-comment
```

---

## Backend setup

### `local` (default)

No extra setup needed. Uses the built-in agent loop with any OpenAI-compatible API.

```bash
lyingdocs init-ci --doc-path docs/ --backend local
# Secret needed: OPENAI_API_KEY
```

### `claude_code`

Uses [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI as the Argus backend. The workflow includes a setup step for `anthropics/claude-code-action@v1`.

```bash
# With API key (single key for both Hermes + Argus)
lyingdocs init-ci --doc-path docs/ --backend claude_code
# Secret needed: ANTHROPIC_API_KEY

# With OAuth token (Argus uses subscription, Hermes uses OpenAI)
lyingdocs init-ci --doc-path docs/ --backend claude_code --claude-oauth
# Secrets needed: OPENAI_API_KEY + CLAUDE_CODE_OAUTH_TOKEN
```

### `codex`

Uses [OpenAI Codex CLI](https://github.com/openai/codex). The workflow includes a setup step to install the CLI globally.

```bash
lyingdocs init-ci --doc-path docs/ --backend codex
# Secret needed: OPENAI_API_KEY
```

---

## Using the Action directly

If you prefer to write your workflow by hand instead of using `init-ci`, reference the action directly:

```yaml
name: LyingDocs Audit
on:
  push:
    tags: ['v*']

permissions:
  contents: read
  pull-requests: write

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run LyingDocs
        uses: KMing-L/lyingdocs@v1
        with:
          doc-path: "docs/"
          code-path: "."
          backend: "claude_code"
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

### Action inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `doc-path` | yes | `docs` | Documentation root directory |
| `code-path` | no | `.` | Code repository root |
| `backend` | no | `local` | Argus backend: `local`, `claude_code`, `codex` |
| `config` | no | | Path to `lyingdocs.toml` config file |
| `hermes-provider` | no | | LLM provider for Hermes: `openai` or `anthropic` |
| `argus-provider` | no | | LLM provider for Argus local backend: `openai` or `anthropic` |
| `openai-api-key` | no | | OpenAI API key (for `local`/`codex`) |
| `anthropic-api-key` | no | | Anthropic API key (for `claude_code`) |
| `claude-oauth-token` | no | | Claude OAuth token (for `claude_code`, Pro/Max subscription) |
| `hermes-model` | no | | Override Hermes LLM model |
| `hermes-base-url` | no | | Override Hermes API base URL |
| `argus-model` | no | | Override Argus LLM model |
| `argus-base-url` | no | | Override Argus API base URL |
| `max-dispatches` | no | | Max Argus dispatches |
| `max-iterations` | no | | Max Hermes loop iterations |
| `gen-issue` | no | `false` | Generate GitHub issue drafts |
| `comment-on-pr` | no | `true` | Post findings as PR comment |
| `python-version` | no | `3.12` | Python version |

### Action outputs

| Output | Description |
| --- | --- |
| `report-path` | Path to the generated report |
| `findings-count` | Number of misalignment findings |
| `has-findings` | `true` if any misalignments found |

---

## Examples

### Claude Code with OAuth + manual approval

```bash
lyingdocs init-ci \
  --doc-path docs/ \
  --backend claude_code \
  --claude-oauth \
  --trigger tag,manual \
  --approval
```

### Minimal — only on tags

```bash
lyingdocs init-ci --doc-path docs/ --trigger tag
```

### Full CI — PR + tag + scheduled + approval

```bash
lyingdocs init-ci \
  --doc-path docs/ \
  --trigger pr,tag,schedule \
  --cron "0 9 * * 1" \
  --approval
```
