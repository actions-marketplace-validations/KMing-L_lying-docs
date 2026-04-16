"""Generate a GitHub Actions workflow for LyingDocs CI integration."""

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Trigger snippets (indented for YAML nesting under `on:`)
# ---------------------------------------------------------------------------

TRIGGER_PR = """\
  pull_request:
    branches: [{branch}]"""

TRIGGER_TAG = """\
  push:
    tags: ['v*']"""

TRIGGER_MANUAL = """\
  workflow_dispatch:"""

TRIGGER_SCHEDULE = """\
  schedule:
    - cron: '{cron}'"""

# ---------------------------------------------------------------------------
# Backend-specific setup steps
# ---------------------------------------------------------------------------

SETUP_CLAUDE_CODE = """\
      - name: Set up Claude Code
        uses: anthropics/claude-code-action@v1
        # Claude Code Action handles authentication via ANTHROPIC_API_KEY
"""

SETUP_CODEX = """\
      - name: Set up Codex CLI
        run: npm install -g @openai/codex
"""

# ---------------------------------------------------------------------------
# Approval job (uses GitHub Environment protection rules)
# ---------------------------------------------------------------------------

APPROVAL_JOB = """\

  review:
    name: Manual Review
    needs: audit
    runs-on: ubuntu-latest
    environment: lyingdocs-review   # Configure required reviewers in repo Settings > Environments
    steps:
      - name: Download report
        uses: actions/download-artifact@v4
        with:
          name: lyingdocs-report

      - name: Display report
        run: |
          echo "## LyingDocs findings approved by reviewer" >> "$GITHUB_STEP_SUMMARY"
          if [ -f Misalignment_Report.md ]; then
            cat Misalignment_Report.md >> "$GITHUB_STEP_SUMMARY"
          fi
"""


def _build_triggers(triggers: list[str], branch: str, cron: str) -> str:
    """Build the `on:` trigger block."""
    parts = []
    for t in triggers:
        if t == "pr":
            parts.append(TRIGGER_PR.format(branch=branch))
        elif t == "tag":
            parts.append(TRIGGER_TAG)
        elif t == "manual":
            parts.append(TRIGGER_MANUAL)
        elif t == "schedule":
            parts.append(TRIGGER_SCHEDULE.format(cron=cron))
    return "\n".join(parts)


def _build_backend_setup(backend: str) -> str:
    """Return extra setup steps for the chosen backend."""
    if backend == "claude_code":
        return SETUP_CLAUDE_CODE
    if backend == "codex":
        return SETUP_CODEX
    return ""


def _build_action_inputs(
    backend: str,
    hermes_provider: str,
    comment_on_pr: bool,
    gen_issue: bool,
    hermes_model: str,
    argus_model: str,
    claude_oauth: bool = False,
) -> str:
    """Build the `with:` block entries beyond doc-path/code-path/backend."""
    lines = []

    # Hermes provider (explicit when not the default for this backend)
    if hermes_provider == "openai" and backend == "claude_code":
        lines.append('          hermes-provider: "openai"')
    elif hermes_provider == "anthropic" and backend not in ("claude_code",):
        lines.append('          hermes-provider: "anthropic"')

    # Determine which providers are actually in use
    # Hermes uses hermes_provider; Argus(claude_code) uses Claude CLI (oauth or api key)
    hermes_needs_openai = hermes_provider == "openai"
    hermes_needs_anthropic = hermes_provider == "anthropic"

    # Argus needs: claude_code → CLI auth (oauth token OR anthropic key);
    #              local/codex → same provider as config (always openai for these backends)
    argus_needs_anthropic_key = (
        backend == "claude_code" and not claude_oauth
    )

    needs_openai = hermes_needs_openai or backend in ("local", "codex")
    needs_anthropic = hermes_needs_anthropic or argus_needs_anthropic_key

    if needs_openai:
        lines.append('          openai-api-key: ${{ secrets.OPENAI_API_KEY }}')
        # Optional: set OPENAI_BASE_URL in repo Variables for custom endpoints
        if hermes_needs_openai:
            lines.append('          hermes-base-url: ${{ vars.OPENAI_BASE_URL }}')
    if needs_anthropic:
        lines.append('          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}')
    if claude_oauth:
        lines.append('          claude-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}')
        lines.append('          # OAuth token for Argus (Claude Code CLI, Pro/Max subscription quota)')
        lines.append('          # Generate with: claude setup-token')

    # PR comment toggle
    if comment_on_pr:
        lines.append('          comment-on-pr: "true"')
    else:
        lines.append('          comment-on-pr: "false"')

    # Issue generation
    if gen_issue:
        lines.append('          gen-issue: "true"')

    # Model overrides
    if hermes_model:
        lines.append(f'          hermes-model: "{hermes_model}"')
    if argus_model:
        lines.append(f'          argus-model: "{argus_model}"')

    return "\n".join(lines)


def generate_workflow(
    *,
    doc_path: str = "docs/",
    code_path: str = ".",
    backend: str = "local",
    hermes_provider: str = "",
    triggers: list[str] | None = None,
    branch: str = "main",
    cron: str = "0 9 * * 1",
    approval: bool = False,
    comment_on_pr: bool = True,
    gen_issue: bool = False,
    hermes_model: str = "",
    argus_model: str = "",
    claude_oauth: bool = False,
    action_ref: str = "KMing-L/lyingdocs@v1",
) -> str:
    """Generate a complete GitHub Actions workflow YAML string."""
    if triggers is None:
        triggers = ["pr", "tag"]

    trigger_block = _build_triggers(triggers, branch, cron)
    backend_setup = _build_backend_setup(backend)
    # Default hermes_provider:
    #  - claude_code without oauth → anthropic (single ANTHROPIC_API_KEY for both)
    #  - claude_code with oauth    → openai (avoids needing ANTHROPIC_API_KEY;
    #                                 oauth only works with CLI, not SDK)
    #  - local/codex               → openai
    effective_hermes_provider = hermes_provider
    if not effective_hermes_provider:
        if backend == "claude_code" and not claude_oauth:
            effective_hermes_provider = "anthropic"
        else:
            effective_hermes_provider = "openai"

    # Default models based on provider/backend when not explicitly set
    effective_hermes_model = hermes_model
    if not effective_hermes_model:
        effective_hermes_model = (
            "claude-sonnet-4-6" if effective_hermes_provider == "anthropic"
            else "gpt-5.4"
        )
    effective_argus_model = argus_model
    if not effective_argus_model:
        if backend == "claude_code":
            effective_argus_model = "claude-sonnet-4-6"
        elif backend == "codex":
            effective_argus_model = "gpt-5.4"
        else:
            # local backend: match hermes provider by default
            effective_argus_model = (
                "claude-sonnet-4-6" if effective_hermes_provider == "anthropic"
                else "gpt-5.4"
            )

    action_inputs = _build_action_inputs(
        backend, effective_hermes_provider, comment_on_pr, gen_issue,
        effective_hermes_model, effective_argus_model, claude_oauth=claude_oauth,
    )
    approval_block = APPROVAL_JOB if approval else ""

    # --- Assemble the workflow ---
    lines = [
        "# =============================================================================",
        "# LyingDocs CI — Documentation-Code Misalignment Detection",
        "#",
        "# Generated by: lyingdocs init-ci",
        "#",
        "# Customize the 'on:' triggers below to control when this runs.",
        "# See: https://github.com/KMing-L/lyingdocs",
        "# =============================================================================",
        "",
        "name: LyingDocs Audit",
        "",
        "on:",
        trigger_block,
        "",
        "# ---- Trigger reference (uncomment what you need) ----",
        "#",
        "#  pull_request:               # Every PR to main",
        "#    branches: [main]",
        "#",
        "#  push:                       # Only on new version tags",
        "#    tags: ['v*']",
        "#",
        "#  workflow_dispatch:           # Manual 'Run workflow' button",
        "#",
        "#  schedule:                    # Weekly scheduled audit",
        "#    - cron: '0 9 * * 1'       # Every Monday at 09:00 UTC",
        "",
        "permissions:",
        "  contents: read",
        "  pull-requests: write",
        "",
        "jobs:",
        "  audit:",
        "    name: LyingDocs Audit",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - name: Checkout repository",
        "        uses: actions/checkout@v4",
        "",
    ]

    if backend_setup:
        lines.append(backend_setup)

    lines += [
        "      - name: Run LyingDocs",
        f"        uses: {action_ref}",
        "        with:",
        f'          doc-path: "{doc_path}"',
        f'          code-path: "{code_path}"',
        f'          backend: "{backend}"',
    ]

    if action_inputs:
        lines.append(action_inputs)

    if approval_block:
        lines.append(approval_block)

    return "\n".join(lines) + "\n"


def cmd_init_ci(args: argparse.Namespace) -> None:
    """Handle the `lyingdocs init-ci` subcommand."""
    # Parse triggers
    triggers = [t.strip() for t in args.trigger.split(",")]
    valid = {"pr", "tag", "manual", "schedule"}
    for t in triggers:
        if t not in valid:
            sys.exit(
                f"ERROR: Unknown trigger '{t}'. "
                f"Valid triggers: {', '.join(sorted(valid))}"
            )

    workflow = generate_workflow(
        doc_path=args.doc_path,
        code_path=args.code_path,
        backend=args.backend,
        hermes_provider=args.hermes_provider or "",
        triggers=triggers,
        branch=args.branch,
        cron=args.cron,
        approval=args.approval,
        comment_on_pr=not args.no_comment,
        gen_issue=args.gen_issue,
        hermes_model=args.hermes_model or "",
        argus_model=args.argus_model or "",
        claude_oauth=args.claude_oauth,
        action_ref=args.action_ref,
    )

    # Determine output path
    out = Path(args.output)
    if out.is_dir() or not out.suffix:
        # Treat as a directory — write to <dir>/.github/workflows/lyingdocs.yml
        out = out / ".github" / "workflows" / "lyingdocs.yml"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(workflow)

    print(f"Workflow generated: {out}")
    print()

    # Determine effective hermes provider for display (same logic as generate_workflow)
    hp = args.hermes_provider
    if not hp:
        if args.backend == "claude_code" and not args.claude_oauth:
            hp = "anthropic"
        else:
            hp = "openai"

    needs_openai = args.backend in ("local", "codex") or hp == "openai"
    needs_anthropic = (
        hp == "anthropic"
        or (args.backend == "claude_code" and not args.claude_oauth)
    )

    step = 1
    print("Next steps:")
    step += 1
    print(f"  1. Review and commit {out}")
    secrets = []
    if needs_openai:
        secrets.append("OPENAI_API_KEY")
    if needs_anthropic:
        secrets.append("ANTHROPIC_API_KEY")
    if secrets:
        print(f"  {step}. Add {' and '.join(secrets)} to your repo secrets (Settings > Secrets)")
        step += 1
    if args.claude_oauth:
        print(f"  {step}. Run `claude setup-token` locally to generate an OAuth token")
        print(f"     Add CLAUDE_CODE_OAUTH_TOKEN to your repo secrets")
        print(f"     (Argus uses OAuth for Pro/Max subscription quota)")
        step += 1
    if args.approval:
        print(
            f"  {step}. Create a 'lyingdocs-review' environment with required reviewers "
            "(Settings > Environments)"
        )
    print()
    print("Done. LyingDocs will run automatically based on your configured triggers.")
