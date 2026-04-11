"""Codex CLI wrapper for atomic code analysis task dispatch."""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("lyingdocs")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def find_codex_binary(config: dict) -> str | None:
    """Locate the codex CLI binary. Returns path string or None."""
    # 1. Explicit path from config
    explicit = config.get("codex_path")
    if explicit:
        p = Path(explicit)
        if p.is_file() and os.access(str(p), os.X_OK):
            return str(p)
        logger.warning("Configured codex_path not found or not executable: %s", p)

    # 2. System PATH (globally installed via npm install -g @openai/codex)
    system_codex = shutil.which("codex")
    if system_codex:
        return system_codex

    # 3. Local node_modules (dev setup / legacy)
    for root in (Path.cwd(), Path(__file__).resolve().parent.parent):
        local = root / "node_modules" / ".bin" / "codex"
        if local.is_file():
            return str(local)

    return None


def codex_provider_flags(config: dict) -> list[str]:
    """Return the CLI flags that configure the model provider for codex."""
    p = config.get("codex_provider", "openai")

    # For the default OpenAI provider, codex knows it natively — just set model
    if p == "openai":
        return ["-m", config["model"]]

    # Custom provider: inject full provider config
    return [
        "-m", config["model"],
        "-c", f'model_provider="{p}"',
        "-c", f'model_providers.{p}.name="{p}"',
        "-c", f'model_providers.{p}.base_url="{config["base_url"]}"',
        "-c", f'model_providers.{p}.env_key="OPENAI_API_KEY"',
        "-c", f'model_providers.{p}.wire_api="{config.get("wire_api", "responses")}"',
        "-c", 'model_reasoning_effort="high"',
    ]


def _load_codex_task_template() -> str:
    return (PROMPTS_DIR / "codex_task.txt").read_text(encoding="utf-8")


def run_codex_task(
    config: dict,
    task_description: str,
    code_path: Path,
    output_dir: Path,
    task_id: str,
    focus_paths: list[str] | None = None,
    codex_bin: str | None = None,
) -> str:
    """Run a single atomic Codex analysis task.

    Returns the Codex output text, or an error message if codex is unavailable.
    """
    if not codex_bin:
        return (
            "[UNAVAILABLE] Codex CLI binary not found. "
            "Install it via 'npm install -g @openai/codex' to enable code analysis. "
            "You can also set codex.path in your config file."
        )

    template = _load_codex_task_template()

    focus_section = ""
    if focus_paths:
        paths_str = "\n".join(f"  - {p}" for p in focus_paths)
        focus_section = f"\nPriority files/directories to examine:\n{paths_str}\n"

    full_prompt = template.format(
        task_description=task_description,
        focus_paths_section=focus_section,
    )

    output_file = output_dir / f"codex_task_{task_id}.txt"
    stderr_file = output_dir / f"codex_stderr_{task_id}.txt"

    cmd = [
        codex_bin, "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C", str(code_path.resolve()),
        "--skip-git-repo-check",
        "-o", str(output_file.resolve()),
        *codex_provider_flags(config),
        "-",  # read prompt from stdin
    ]

    logger.info("  Codex task %s: dispatching ...", task_id)
    logger.debug("  Command: %s", " ".join(cmd[:7]) + " ...")

    try:
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=config.get("codex_task_timeout", 1200),
            env=os.environ.copy(),
        )

        # Save stderr for debugging
        stderr_file.write_text(result.stderr, encoding="utf-8")

        if result.returncode != 0:
            logger.warning(
                "  Codex task %s exited with code %d", task_id, result.returncode
            )

        # Read output: -o file first, fallback to stdout
        output = ""
        if output_file.exists() and output_file.stat().st_size > 0:
            output = output_file.read_text(encoding="utf-8")
        elif result.stdout.strip():
            output = result.stdout.strip()
            output_file.write_text(output, encoding="utf-8")

        if output:
            logger.info(
                "  Codex task %s: completed (%d chars)", task_id, len(output)
            )
        else:
            logger.warning("  Codex task %s: no output produced", task_id)

        return output

    except subprocess.TimeoutExpired:
        logger.error(
            "  Codex task %s timed out after %ds",
            task_id, config.get("codex_task_timeout", 1200),
        )
        return "[ERROR] Codex task timed out."
