<p align="center">
  <img src="assets/logo.png" alt="LyingDocs" width="200" />
</p>

<h1 align="center">LyingDocs</h1>

<p align="center">
  A trust layer for your repository.
</p>

<p align="center">
  Detect when your docs, code, configs, and examples stop agreeing with each other.
</p>

---

Modern repositories are read by more than humans.

They are read by teammates, new contributors, users, reviewers, downstream integrators — and increasingly by AI agents.

That only works if the repository can be trusted.

But trust quietly erodes over time:

- documentation describes features that were never shipped
- code behavior drifts away from the spec
- examples stop matching reality
- values claimed to be configurable are hardcoded deep in the codebase
- papers and implementation tell different stories

**LyingDocs is a trust layer for your repository.**  
It audits the gap between what your repo *says* and what your code *actually does* — before your users, contributors, or agents learn the wrong thing.

---

## Why LyingDocs exists

Every codebase accumulates invisible trust debt.

In the age of fast iteration and LLM-assisted development, teams now ship code and documentation faster than ever — but not always in sync. A repo may still look polished while becoming progressively less reliable as a source of truth.

That is the problem LyingDocs is built to solve.

LyingDocs is not just a documentation checker. It is a system for surfacing **repository misalignment**:

- docs that overclaim
- code paths that are undocumented
- specs that no longer match implementation
- "configurable" behavior that is actually fixed
- claims in papers or READMEs that cannot be supported by the code

The goal is simple:

> Keep your repository trustworthy for humans and machines.

---

## What LyingDocs does

LyingDocs deploys two autonomous agents against your repository:

- **Hermes** reads your documentation, plans an audit strategy, and decides what needs to be verified
- **Argus** investigates the actual codebase and reports what the code really does

Hermes then reconciles the two and writes a structured report of the mismatches it finds.

This lets you catch cases where your repository is no longer telling the truth about itself.

---

## How it works

### 1. Hermes reads what the repo claims

Hermes traverses your documentation and extracts claims, assumptions, and implementation promises from sources such as:

- docs/
- README files
- setup guides
- usage examples
- configuration references
- papers and research writeups

It then plans an audit by turning those claims into targeted investigation tasks.

### 2. Argus checks what the code actually does

Argus executes each task against your real codebase.

You can choose the backend that best fits your setup:

- **`codex`** — [OpenAI Codex CLI](https://github.com/openai/codex) subprocess
- **`claude_code`** — [Claude Code](https://docs.anthropic.com/claude/docs/claude-code) CLI subprocess (`claude -p`)
- **`local`** — built-in minimal agent loop using filesystem tools and any OpenAI-compatible API directly

### 3. LyingDocs reports the trust gaps

Hermes reconciles documented claims with observed implementation behavior and outputs a report of misalignments.

These findings can then be reviewed by maintainers, turned into issues, and eventually enforced in CI.

---

## Positioning

LyingDocs is best thought of as:

- a **trust layer** for your repo
- a **docs-to-code alignment guard**
- a **pre-user warning system** for misleading documentation
- a future **CI / GitHub Action quality gate** for repository truthfulness

It is not meant to be a tool you manually open every day.

It is meant to become something your repository runs automatically:

- on pull requests
- before releases
- during scheduled audits
- before docs deployment
- as part of your GitHub Actions workflow

---

## Installation

```bash
pip install lyingdocs
````

---

## Quick Start

```bash
export OPENAI_API_KEY="sk-..."

lyingdocs analyze --doc-path docs/ --code-path . -o output/audit
```

This performs a full audit of your repository and produces a report describing where documentation and implementation no longer align.

---

## Documentation

| | |
| --- | --- |
| [Configuration](docs/configuration.md) | Config file schema, environment variables, layer resolution |
| [Argus Backends](docs/backends.md) | Setup for `local`, `codex`, and `claude_code` |
| [CLI Reference](docs/cli.md) | All flags, commands, and output artifacts |
| [GitHub Actions](docs/guides/github-actions.md) | CI integration, authentication, triggers, and approval gates |
| [GitHub Issues](docs/guides/github-issues.md) | Using `--gen-issue` to draft and post issues |

---

## Example use cases

Use LyingDocs when you want to answer questions like:

* Does the README still reflect the real behavior of the project?
* Are our examples and quickstarts still valid?
* Did code change without the docs changing with it?
* Are we claiming configuration that does not actually exist?
* Does our paper describe behavior the implementation does not support?
* Can an AI agent trust this repository as a source of truth?

---

## Misalignment categories

| Category           | Description                                           |
| ------------------ | ----------------------------------------------------- |
| **LogicMismatch**  | Code contradicts documentation                        |
| **PhantomSpec**    | Documentation describes non-existent features         |
| **ShadowLogic**    | Important code behavior exists but is undocumented    |
| **HardcodedDrift** | Supposedly configurable values are actually hardcoded |

These categories represent different ways repository trust breaks down.

---

## GitHub Actions

LyingDocs runs natively in GitHub Actions as a trust gate for your CI pipeline.

```bash
pip install lyingdocs
lyingdocs init-ci --doc-path docs/ --backend claude_code --claude-oauth --trigger tag,manual
```

This generates a workflow that:

* audits docs-vs-code alignment on every tag push (or on demand)
* posts findings as a PR comment
* optionally requires manual approval before merging

Supports all three backends (`local`, `codex`, `claude_code`) and both API key and OAuth token authentication for Claude Code.

See the [full setup guide](docs/guides/github-actions.md) for trigger options, approval gates, and backend configuration.

---

## Roadmap

* [x] **Multi-harness support** — Argus runs on Codex, Claude Code, or a built-in local agent
* [x] **Issue generation** — `--gen-issue` drafts GitHub issues from findings
* [x] **GitHub Action integration** — `lyingdocs init-ci` generates a ready-to-use workflow with configurable triggers, backend selection, PR comments, and manual approval gates
* [ ] **One-session memory support** — Argus backends retain state across tasks for deeper multi-step investigations
* [ ] **Deeper analysis** — multi-hop reasoning across doc hierarchies and version-aware diffing to detect when code changed but docs did not
* [ ] **Paper mode** — treat academic papers as documentation and detect paper-to-code misalignment
* [ ] **Auto-fix mode** — Hermes proposes doc patches for human review and application

---

## For researchers

A paper is also documentation.

It is a human-language description of code, behavior, claims, and expected results — often written under deadline, and often drifting away from the implementation over time.

If you want to know whether:

* your repo matches your paper
* your claims are supported by the code
* another researcher can trust your implementation

then LyingDocs can help.

The problem is the same.
Paper is documentation for code.
LyingDocs is for papers too.

---

## Why “trust layer”

Because the problem is bigger than stale docs.

A repository becomes untrustworthy whenever its outward description and inward behavior drift apart.

That harms:

* users trying to adopt the project
* contributors trying to extend it
* maintainers trying to review changes
* researchers trying to reproduce results
* AI agents trying to understand the repo

LyingDocs exists to make that gap visible.

Not after users complain.
Before.

---

## License

MIT