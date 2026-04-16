"""Local Argus backend: in-process code analysis agent loop.

A minimal stateless agent that investigates a single task using filesystem tools
and an OpenAI-compatible chat completions API.
"""

import json
import logging
import re
from pathlib import Path

from .llm import LLMResponse, call_llm_with_tools, make_client

logger = logging.getLogger("lyingdocs")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__",
    ".venv", "venv", "dist", "build", ".mypy_cache", ".pytest_cache",
}


ARGUS_LOCAL_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": (
                "List files and subdirectories under a path within the code root. "
                "Returns names, sizes, and a file/dir indicator."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path within the code root. Use '.' for root.",
                        "default": ".",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a file's content with numbered lines. Use start_line/end_line "
                "for large files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path within the code root.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start line (1-indexed). Default 1.",
                        "default": 1,
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line (inclusive). Default: read to end.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Regex search across the code tree. Returns matching lines with "
                "file paths and line numbers. Max 50 results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern (case-insensitive).",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Glob filter for file names. Default '*'.",
                        "default": "*",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": (
                "Submit the final investigation report and terminate. Call this "
                "once you have a concrete, evidence-backed answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "report": {
                        "type": "string",
                        "description": "Full report with file:line references.",
                    },
                },
                "required": ["report"],
            },
        },
    },
]


class LocalArgus:
    """Single-task in-process code analysis agent."""

    def __init__(self, config: dict, code_path: Path):
        self.config = config
        self.code_root = code_path.resolve()
        self.provider = config.get("argus_provider", "openai")
        self.client = make_client(
            api_key=config["argus_api_key"],
            base_url=config["argus_base_url"],
            provider=self.provider,
        )
        self.model = config["argus_model"]
        self.max_iterations = int(config.get("argus_local_max_iterations", 25))
        self.max_read_bytes = int(config.get("argus_local_max_read_bytes", 200_000))
        self._finished: str | None = None

    def run(self, task_description: str, focus_paths: list[str] | None = None) -> str:
        system_prompt = (PROMPTS_DIR / "argus_local_system.txt").read_text(
            encoding="utf-8"
        )
        user_msg = self._build_user_message(task_description, focus_paths)

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        for iteration in range(1, self.max_iterations + 1):
            logger.info("  Argus(local) iter %d/%d", iteration, self.max_iterations)
            response = call_llm_with_tools(
                self.client, self.model, messages, ARGUS_LOCAL_TOOL_SCHEMAS,
                provider=self.provider,
            )
            messages.append(self._response_to_message(response))

            if not response.tool_calls:
                if response.content:
                    logger.info("  Argus(local): %s", _truncate(response.content, 160))
                messages.append({
                    "role": "user",
                    "content": "Use a tool to proceed, or call finish(report) if done.",
                })
                continue

            for tc in response.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                logger.info("  Argus tool: %s(%s)", name, _truncate(str(args), 100))
                result = self._dispatch_tool(name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                if self._finished is not None:
                    return self._finished

        logger.warning("Argus(local) hit max_iterations without finish()")
        return (
            "[INCOMPLETE] Argus reached max_iterations without calling finish(). "
            "Partial exploration only; no verdict available."
        )

    # --- internals ---

    def _build_user_message(
        self, task_description: str, focus_paths: list[str] | None
    ) -> str:
        parts = [
            f"## Code Root\n{self.code_root}\n",
            f"## Task\n{task_description}\n",
        ]
        if focus_paths:
            paths_str = "\n".join(f"  - {p}" for p in focus_paths)
            parts.append(f"## Priority paths\n{paths_str}\n")
        parts.append(
            "Investigate using the tools, then call finish(report) with a "
            "verdict grounded in file:line references."
        )
        return "\n".join(parts)

    def _response_to_message(self, response) -> dict:
        msg = {"role": "assistant"}
        if response.content:
            msg["content"] = response.content
        if response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in response.tool_calls
            ]
        return msg

    def _dispatch_tool(self, name: str, args: dict) -> str:
        try:
            if name == "list_directory":
                return self._tool_list_directory(**args)
            if name == "read_file":
                return self._tool_read_file(**args)
            if name == "search_code":
                return self._tool_search_code(**args)
            if name == "finish":
                self._finished = args.get("report", "").strip() or "[EMPTY REPORT]"
                return "Report submitted. Terminating."
            return f"[ERROR] Unknown tool: {name}"
        except TypeError as e:
            return f"[ERROR] Bad arguments for {name}: {e}"
        except Exception as e:
            logger.error("Argus tool %s failed: %s", name, e)
            return f"[ERROR] {name} failed: {e}"

    def _resolve_under_root(self, rel_path: str) -> Path | None:
        candidate = (self.code_root / rel_path).resolve()
        try:
            candidate.relative_to(self.code_root)
        except ValueError:
            return None
        return candidate

    def _tool_list_directory(self, path: str = ".") -> str:
        target = self._resolve_under_root(path)
        if target is None:
            return "[ERROR] Path outside code root."
        if not target.is_dir():
            return f"[ERROR] Not a directory: {path}"

        lines = [f"Contents of {path}/:"]
        try:
            entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

        for p in entries:
            if p.name.startswith(".") and p.name not in (".", ".."):
                continue
            if p.is_dir():
                if p.name in DEFAULT_EXCLUDE_DIRS:
                    lines.append(f"  [dir]  {p.name}/  (excluded)")
                else:
                    lines.append(f"  [dir]  {p.name}/")
            elif p.is_file():
                lines.append(f"  [file] {p.name}  ({_human_size(p.stat().st_size)})")
        if len(lines) == 1:
            lines.append("  (empty)")
        return "\n".join(lines)

    def _tool_read_file(
        self, path: str, start_line: int = 1, end_line: int | None = None
    ) -> str:
        target = self._resolve_under_root(path)
        if target is None:
            return "[ERROR] Path outside code root."
        if not target.is_file():
            return f"[ERROR] File not found: {path}"

        try:
            raw = target.read_bytes()
        except PermissionError:
            return f"[ERROR] Permission denied: {path}"

        truncated_note = ""
        if len(raw) > self.max_read_bytes:
            raw = raw[: self.max_read_bytes]
            truncated_note = (
                f"\n... (truncated at {self.max_read_bytes} bytes; "
                "re-read with start_line/end_line for more)"
            )
        text = raw.decode("utf-8", errors="replace")
        all_lines = text.splitlines()

        start = max(0, start_line - 1)
        end = end_line if end_line else len(all_lines)
        selected = all_lines[start:end]

        numbered = [
            f"{i + start + 1:5d} | {line}" for i, line in enumerate(selected)
        ]
        header = (
            f"File: {path} (lines {start + 1}-{start + len(selected)}/{len(all_lines)})\n"
        )
        return header + "\n".join(numbered) + truncated_note

    def _tool_search_code(self, pattern: str, glob: str = "*") -> str:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        results: list[str] = []
        for path in self.code_root.rglob(glob):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(self.code_root)
            except ValueError:
                continue
            if any(part in DEFAULT_EXCLUDE_DIRS or part.startswith(".") for part in rel.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    snippet = line.strip()
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."
                    results.append(f"{rel}:{i}: {snippet}")
                    if len(results) >= 50:
                        results.append("... (truncated at 50 results)")
                        return "\n".join(results)

        if not results:
            return f"No matches for pattern: {pattern}"
        return "\n".join(results)


def run_local_argus_task(
    config: dict,
    task_description: str,
    code_path: Path,
    output_dir: Path,
    task_id: str,
    focus_paths: list[str] | None = None,
) -> str:
    """Run a stateless local Argus task and persist its report. Returns the report text."""
    agent = LocalArgus(config, code_path)
    logger.info("  Argus(local) task %s: starting ...", task_id)
    report = agent.run(task_description, focus_paths)
    output_file = output_dir / f"argus_task_{task_id}.txt"
    try:
        output_file.write_text(report, encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to persist Argus task output: %s", e)
    logger.info("  Argus(local) task %s: completed (%d chars)", task_id, len(report))
    return report


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 3] + "..."
