# CLI Reference

## Commands

### `lyingdocs analyze`

Run a full documentation-code audit.

```bash
lyingdocs analyze --doc-path <docs> --code-path <code> [options]
```

**Examples:**

```bash
# Full analysis
lyingdocs analyze --doc-path docs/ --code-path . -o output/audit

# Choose Argus backend
lyingdocs analyze --doc-path docs/ --code-path . --argus-backend=local

# Different models for Hermes and Argus
lyingdocs analyze --doc-path docs/ --code-path . \
  --hermes-model gpt-5.4 \
  --argus-model gpt-5.4

# Resume interrupted analysis
lyingdocs analyze --doc-path docs/ --code-path . --resume

# Use an explicit config file
lyingdocs analyze --doc-path docs/ --code-path . --config myconfig.toml

# Generate GitHub issue drafts after analysis
lyingdocs analyze --doc-path docs/ --code-path . --gen-issue
```

### `lyingdocs init-ci`

Generate a GitHub Actions workflow for LyingDocs CI integration.

```bash
lyingdocs init-ci [options]
```

**Examples:**

```bash
# Default: PR + tag triggers, local backend
lyingdocs init-ci --doc-path docs/ --code-path .

# Claude Code backend with OAuth token
lyingdocs init-ci --doc-path docs/ --backend claude_code --claude-oauth

# Only on tags + manual trigger, with approval gate
lyingdocs init-ci --doc-path docs/ --trigger tag,manual --approval

# Custom output path
lyingdocs init-ci --doc-path docs/ --trigger tag -o my-project/
```

See [GitHub Actions Integration](guides/github-actions.md) for the full setup guide.

### `lyingdocs version`

Display the installed version.

```bash
lyingdocs version
```

---

## Flags

### `analyze` flags

| Flag | Description |
| --- | --- |
| `--doc-path` | Path to documentation root |
| `--code-path` | Path to code root |
| `-o`, `--output` | Output directory for report artifacts |
| `--config` | Explicit path to a config file |
| `--resume` | Resume a previously interrupted analysis |
| `--gen-issue` | Generate a GitHub issue draft from findings |
| `--hermes-model` | Model name for Hermes |
| `--hermes-base-url` | API base URL for Hermes |
| `--argus-backend` | Argus backend: `codex`, `claude_code`, or `local` |
| `--argus-model` | Model name for Argus |
| `--argus-base-url` | API base URL for Argus |
| `--argus-codex-provider` | Provider flag passed to Codex CLI |
| `--argus-codex-wire-api` | Wire API for Codex backend (`responses` or `chat`) |
| `--max-dispatches` | Max number of Argus tasks per run |
| `--max-iterations` | Max Hermes agent loop iterations |

### `init-ci` flags

| Flag | Description |
| --- | --- |
| `--doc-path` | Documentation root directory (default: `docs/`) |
| `--code-path` | Code repository root (default: `.`) |
| `--backend` | Argus backend: `local`, `codex`, or `claude_code` |
| `--trigger` | Comma-separated triggers: `pr`, `tag`, `manual`, `schedule` (default: `pr,tag`) |
| `--branch` | Target branch for PR trigger (default: `main`) |
| `--cron` | Cron expression for schedule trigger (default: `0 9 * * 1`) |
| `--approval` | Add a manual approval step via GitHub Environments |
| `--no-comment` | Disable automatic PR comment with findings |
| `--claude-oauth` | Use Claude OAuth token instead of API key (Pro/Max subscription) |
| `--gen-issue` | Generate GitHub issue drafts from findings |
| `--hermes-provider` | LLM provider for Hermes: `openai` or `anthropic` (default: `anthropic` for `claude_code`, `openai` otherwise) |
| `--hermes-model` | Override Hermes LLM model |
| `--argus-model` | Override Argus LLM model |
| `--action-ref` | GitHub Action reference (default: `KMing-L/lyingdocs@v1`) |
| `-o`, `--output` | Output path (default: `.` — writes to `.github/workflows/lyingdocs.yml`) |

---

## Output artifacts

Each analysis run produces the following files in the output directory:

| File | Description |
| --- | --- |
| `Misalignment_Report.md` | Structured report of all findings |
| `findings.jsonl` | Per-finding records (one JSON object per line) |
| `doc_index.json` | Documentation inventory built during audit |
| `argus_task_NNN.txt` | Raw output from each Argus task |
| `workspace_state.json` | Resume checkpoint |
| `pipeline.log` | Full execution log |
| `issue.json` | GitHub issue draft (only with `--gen-issue`) |
