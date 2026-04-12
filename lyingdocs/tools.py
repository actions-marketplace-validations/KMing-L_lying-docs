"""Tool implementations and OpenAI function schemas for HermesAgent."""

import json
import logging
import re
from pathlib import Path

from .argus import ArgusDispatcher
from .workspace import CATEGORIES, SEVERITIES, Workspace

logger = logging.getLogger("lyingdocs")


# ---------------------------------------------------------------------------
# Tool Schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_docs",
            "description": (
                "List documentation files and subdirectories under a given path. "
                "Returns file names, sizes, and types. Use to explore the doc tree."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Relative path within the doc root. Use '.' for the root.",
                        "default": ".",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_doc",
            "description": (
                "Read a documentation file's content. Supports optional line ranges "
                "for large files. Returns content with line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the doc file within doc root.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start reading from this line (1-indexed). Default: 1.",
                        "default": 1,
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Stop reading at this line (inclusive). Default: read all.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search across documentation files for a pattern (regex or substring). "
                "Returns matching lines with file paths and line numbers. Max 50 results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (regex supported).",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Glob pattern to filter files. Default: '*.md'.",
                        "default": "*.md",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_argus",
            "description": (
                "Dispatch an atomic code analysis task to Argus (the deep code analyst). "
                "The task should be specific and targeted — reference concrete doc claims "
                "and what to verify in the codebase. Each dispatch uses one unit of your "
                "budget."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": (
                            "Specific audit question. Must reference concrete doc claims "
                            "and what to verify in code. Example: 'The docs at "
                            "docs/api/auth.md:45-60 claim OAuth2 PKCE is used for "
                            "all public clients. Verify the auth middleware implements "
                            "PKCE validation.'"
                        ),
                    },
                    "focus_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of code paths to prioritize (relative to code root)."
                        ),
                    },
                },
                "required": ["task_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_finding",
            "description": (
                "Record a documentation-code misalignment finding. Call this after "
                "analyzing Codex output to save confirmed findings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": list(CATEGORIES),
                        "description": (
                            "LogicMismatch: code contradicts doc. "
                            "PhantomSpec: doc describes something absent from code. "
                            "ShadowLogic: important code logic not documented. "
                            "HardcodedDrift: important params hardcoded."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Short descriptive title for the finding.",
                    },
                    "doc_ref": {
                        "type": "string",
                        "description": "Doc file path + line/section reference.",
                    },
                    "code_ref": {
                        "type": "string",
                        "description": "Code file path + line number (from Codex output).",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed explanation of the misalignment.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": list(SEVERITIES),
                        "description": "Impact severity: high, medium, or low.",
                    },
                },
                "required": [
                    "category", "title", "doc_ref", "code_ref",
                    "description", "severity",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_progress",
            "description": (
                "Check current audit progress: sections completed, findings by category, "
                "Codex dispatch budget remaining."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_section_complete",
            "description": "Mark a documentation section/file as fully audited.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_path": {
                        "type": "string",
                        "description": "Path to the doc section/file that has been audited.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about what was found or not found.",
                        "default": "",
                    },
                },
                "required": ["section_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_report",
            "description": (
                "Signal that all auditing is complete. Triggers final report generation. "
                "Call this when you have audited all high-priority sections or the "
                "dispatch budget is running low."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool Executor
# ---------------------------------------------------------------------------


class ToolExecutor:
    """Executes tool calls from the agent and returns results."""

    def __init__(
        self,
        doc_root: Path,
        code_path: Path,
        output_dir: Path,
        workspace: Workspace,
        config: dict,
    ):
        self.doc_root = doc_root.resolve()
        self.code_path = code_path
        self.output_dir = output_dir
        self.workspace = workspace
        self.config = config
        self.argus = ArgusDispatcher(config)

    def execute(self, tool_name: str, arguments: dict) -> str:
        """Dispatch a tool call and return the result string."""
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return f"[ERROR] Unknown tool: {tool_name}"
        try:
            return handler(**arguments)
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return f"[ERROR] {tool_name} failed: {e}"

    # -- Tool implementations --

    def _tool_list_docs(self, directory: str = ".") -> str:
        target = (self.doc_root / directory).resolve()
        if not str(target).startswith(str(self.doc_root)):
            return "[ERROR] Path outside doc root."
        if not target.is_dir():
            return f"[ERROR] Not a directory: {directory}"

        lines = [f"Contents of {directory}/:\n"]

        # Directories first
        dirs = sorted(
            p for p in target.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
        for d in dirs:
            file_count = sum(1 for _ in d.rglob("*") if _.is_file())
            lines.append(f"  📁 {d.name}/ ({file_count} files)")

        # Then files
        files = sorted(p for p in target.iterdir() if p.is_file())
        for f in files:
            size = f.stat().st_size
            lines.append(f"  📄 {f.name} ({_human_size(size)})")

        return "\n".join(lines)

    def _tool_read_doc(
        self, path: str, start_line: int = 1, end_line: int | None = None
    ) -> str:
        target = (self.doc_root / path).resolve()
        if not str(target).startswith(str(self.doc_root)):
            return "[ERROR] Path outside doc root."
        if not target.is_file():
            return f"[ERROR] File not found: {path}"

        content = target.read_text(encoding="utf-8", errors="replace")
        all_lines = content.splitlines()

        start = max(0, start_line - 1)
        end = end_line if end_line else len(all_lines)
        selected = all_lines[start:end]

        numbered = [
            f"{i + start + 1:4d} | {line}" for i, line in enumerate(selected)
        ]

        header = f"File: {path} (lines {start + 1}-{start + len(selected)}/{len(all_lines)})\n"
        return header + "\n".join(numbered)

    def _tool_search_docs(self, pattern: str, glob: str = "*.md") -> str:
        results = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            # Fall back to literal search
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        for path in sorted(self.doc_root.rglob(glob)):
            if not path.is_file():
                continue
            # Skip hidden/non-doc dirs
            rel = path.relative_to(self.doc_root)
            if any(p.startswith(".") for p in rel.parts):
                continue

            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue

            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    results.append(f"{rel}:{i}: {line.strip()}")
                    if len(results) >= 50:
                        results.append("... (truncated at 50 results)")
                        return "\n".join(results)

        if not results:
            return f"No matches found for pattern: {pattern}"
        return "\n".join(results)

    def _tool_dispatch_argus(
        self, task_description: str, focus_paths: list[str] | None = None
    ) -> str:
        if self.workspace.is_budget_exhausted():
            return (
                "[ERROR] Argus dispatch budget exhausted. "
                "You should finalize the report with the findings collected so far."
            )

        self.workspace.increment_dispatch()
        task_id = f"{self.workspace.codex_dispatch_count:03d}"

        result = self.argus.run(
            task_description,
            self.code_path,
            self.output_dir,
            task_id,
            focus_paths,
        )

        remaining = self.workspace.dispatches_remaining()
        footer = f"\n\n[Argus dispatches remaining: {remaining}/{self.workspace.max_dispatches}]"
        return result + footer

    def _tool_record_finding(
        self,
        category: str,
        title: str,
        doc_ref: str,
        code_ref: str,
        description: str,
        severity: str,
    ) -> str:
        finding = self.workspace.add_finding(
            category=category,
            title=title,
            doc_ref=doc_ref,
            code_ref=code_ref,
            description=description,
            severity=severity,
        )
        return (
            f"Finding recorded: [{finding.category}] {finding.title} "
            f"(id: {finding.id}, severity: {finding.severity})"
        )

    def _tool_get_progress(self) -> str:
        return self.workspace.get_progress_summary()

    def _tool_mark_section_complete(
        self, section_path: str, notes: str = ""
    ) -> str:
        self.workspace.mark_section_complete(section_path, notes)
        return f"Section marked complete: {section_path}"

    def _tool_finalize_report(self) -> str:
        self.workspace.finalize()
        return (
            "Report finalization triggered. "
            f"Total findings: {len(self.workspace.findings)}. "
            "The final report will be generated now."
        )


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / (1024 * 1024):.1f}MB"
