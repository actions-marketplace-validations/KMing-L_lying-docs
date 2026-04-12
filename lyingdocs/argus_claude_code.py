"""Claude Code CLI wrapper for Argus code analysis tasks."""

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("lyingdocs")


def find_claude_binary(config: dict) -> str | None:
    """Locate the claude CLI binary. Returns path string or None."""
    explicit = config.get("argus_claude_code_path")
    if explicit:
        p = Path(explicit)
        if p.is_file() and os.access(str(p), os.X_OK):
            return str(p)
        logger.warning(
            "Configured argus.claude_code.path not found or not executable: %s", p
        )

    system = shutil.which("claude")
    if system:
        return system

    return None


def run_claude_code_task(
    config: dict,
    task_description: str,
    code_path: Path,
    output_dir: Path,
    task_id: str,
    focus_paths: list[str] | None = None,
    claude_bin: str | None = None,
) -> str:
    """Run a single Argus analysis task via `claude -p`."""
    if not claude_bin:
        return (
            "[UNAVAILABLE] Claude Code CLI binary not found. "
            "Install it and/or set argus.claude_code.path in your config."
        )

    focus_section = ""
    if focus_paths:
        paths_str = "\n".join(f"  - {p}" for p in focus_paths)
        focus_section = f"\nPriority files/directories:\n{paths_str}\n"

    full_prompt = (
        f"You are Argus, a code analyst.\n\n"
        f"Task: {task_description}\n"
        f"{focus_section}\n"
        f"Investigate the code at {code_path.resolve()} and return a report with "
        f"a verdict (confirmed / contradicted / not-found / partial) plus concrete "
        f"file:line references and short quoted snippets."
    )

    output_file = output_dir / f"argus_task_{task_id}.txt"
    stderr_file = output_dir / f"argus_stderr_{task_id}.txt"

    cmd = [
        claude_bin,
        "-p", full_prompt,
        "--model", config["argus_model"],
        "--output-format", "text",
    ]

    logger.info("  Argus(claude_code) task %s: dispatching ...", task_id)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.get("argus_task_timeout", 1200),
            cwd=str(code_path.resolve()),
            env=os.environ.copy(),
        )

        stderr_file.write_text(result.stderr, encoding="utf-8")

        if result.returncode != 0:
            logger.warning(
                "  Argus(claude_code) task %s exited with code %d",
                task_id, result.returncode,
            )

        output = result.stdout.strip()
        if output:
            output_file.write_text(output, encoding="utf-8")
            logger.info(
                "  Argus(claude_code) task %s: completed (%d chars)", task_id, len(output)
            )
        else:
            logger.warning("  Argus(claude_code) task %s: no output produced", task_id)

        return output or "[ERROR] Claude Code produced no output."

    except subprocess.TimeoutExpired:
        logger.error(
            "  Argus(claude_code) task %s timed out after %ds",
            task_id, config.get("argus_task_timeout", 1200),
        )
        return "[ERROR] Claude Code task timed out."
