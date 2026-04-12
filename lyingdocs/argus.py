"""Argus dispatcher: routes code-analysis tasks to the configured backend."""

import logging
from pathlib import Path

from .argus_claude_code import find_claude_binary, run_claude_code_task
from .argus_local import run_local_argus_task
from .codex import find_codex_binary, run_codex_task

logger = logging.getLogger("lyingdocs")


class ArgusDispatcher:
    """Holds backend selection and cached binary resolution for Argus tasks."""

    def __init__(self, config: dict):
        self.config = config
        self.backend = config["argus_backend"]
        self._codex_bin: str | None = None
        self._claude_bin: str | None = None

        if self.backend == "codex":
            self._codex_bin = find_codex_binary(self.config)
            if self._codex_bin:
                logger.info("Argus backend=codex: %s", self._codex_bin)
            else:
                logger.warning(
                    "Argus backend=codex but codex CLI not found. "
                    "Dispatches will return [UNAVAILABLE]."
                )
        elif self.backend == "claude_code":
            self._claude_bin = find_claude_binary(self.config)
            if self._claude_bin:
                logger.info("Argus backend=claude_code: %s", self._claude_bin)
            else:
                logger.warning(
                    "Argus backend=claude_code but claude CLI not found. "
                    "Dispatches will return [UNAVAILABLE]."
                )
        elif self.backend == "local":
            logger.info(
                "Argus backend=local (model=%s, base_url=%s)",
                self.config["argus_model"], self.config["argus_base_url"],
            )

    def run(
        self,
        task_description: str,
        code_path: Path,
        output_dir: Path,
        task_id: str,
        focus_paths: list[str] | None = None,
    ) -> str:
        if self.backend == "codex":
            return run_codex_task(
                self.config,
                task_description,
                code_path,
                output_dir,
                task_id,
                focus_paths,
                codex_bin=self._codex_bin,
            )
        if self.backend == "claude_code":
            return run_claude_code_task(
                self.config,
                task_description,
                code_path,
                output_dir,
                task_id,
                focus_paths,
                claude_bin=self._claude_bin,
            )
        if self.backend == "local":
            return run_local_argus_task(
                self.config,
                task_description,
                code_path,
                output_dir,
                task_id,
                focus_paths,
            )
        return f"[ERROR] Unknown argus backend: {self.backend}"
