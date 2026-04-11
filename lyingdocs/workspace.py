"""Workspace state: findings, progress tracking, and persistence."""

import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("lyingdocs")

CATEGORIES = ("LogicMismatch", "PhantomSpec", "ShadowLogic", "HardcodedDrift")
SEVERITIES = ("high", "medium", "low")


@dataclass
class Finding:
    id: str
    category: str
    title: str
    doc_ref: str
    code_ref: str
    description: str
    severity: str
    timestamp: str


class Workspace:
    """Manages audit state: findings, completed sections, and dispatch budget."""

    def __init__(self, output_dir: Path, max_dispatches: int = 20):
        self.output_dir = output_dir
        self.max_dispatches = max_dispatches
        self.findings: list[Finding] = []
        self.completed_sections: set[str] = set()
        self.codex_dispatch_count: int = 0
        self._finalized: bool = False
        self._lock = threading.Lock()

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def add_finding(
        self,
        category: str,
        title: str,
        doc_ref: str,
        code_ref: str,
        description: str,
        severity: str,
    ) -> Finding:
        """Record a new misalignment finding."""
        if category not in CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Must be one of: {CATEGORIES}"
            )
        if severity not in SEVERITIES:
            raise ValueError(
                f"Invalid severity '{severity}'. Must be one of: {SEVERITIES}"
            )

        finding = Finding(
            id=str(uuid.uuid4())[:8],
            category=category,
            title=title,
            doc_ref=doc_ref,
            code_ref=code_ref,
            description=description,
            severity=severity,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self.findings.append(finding)

            # Append to JSONL for crash recovery
            with open(self.output_dir / "findings.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(finding)) + "\n")

        logger.info(
            "  Finding recorded: [%s] %s (%s)", category, title, severity
        )
        return finding

    def mark_section_complete(self, section_path: str, notes: str = "") -> None:
        with self._lock:
            self.completed_sections.add(section_path)
        logger.info("  Section completed: %s", section_path)

    def increment_dispatch(self) -> None:
        with self._lock:
            self.codex_dispatch_count += 1

    def dispatches_remaining(self) -> int:
        with self._lock:
            return max(0, self.max_dispatches - self.codex_dispatch_count)

    def finalize(self) -> None:
        with self._lock:
            self._finalized = True

    def is_complete(self) -> bool:
        with self._lock:
            return self._finalized

    def is_budget_exhausted(self) -> bool:
        with self._lock:
            return self.codex_dispatch_count >= self.max_dispatches

    def get_progress_summary(self) -> str:
        """Return a text summary of current audit progress."""
        by_cat = {c: [] for c in CATEGORIES}
        for f in self.findings:
            by_cat[f.category].append(f)

        lines = [
            "## Audit Progress",
            f"Codex dispatches: {self.codex_dispatch_count}/{self.max_dispatches}",
            f"Sections completed: {len(self.completed_sections)}",
            f"Total findings: {len(self.findings)}",
            "",
            "### Findings by Category",
        ]
        for cat in CATEGORIES:
            count = len(by_cat[cat])
            if count:
                lines.append(f"  {cat}: {count}")
                for f in by_cat[cat]:
                    lines.append(f"    - [{f.severity}] {f.title}")
            else:
                lines.append(f"  {cat}: 0")

        if self.completed_sections:
            lines.append("\n### Completed Sections")
            for s in sorted(self.completed_sections):
                lines.append(f"  - {s}")

        if self.is_budget_exhausted():
            lines.append("\n⚠️ Codex dispatch budget exhausted.")

        return "\n".join(lines)

    def save_state(self) -> None:
        """Persist workspace state to JSON for resume capability."""
        state = {
            "findings": [asdict(f) for f in self.findings],
            "completed_sections": sorted(self.completed_sections),
            "codex_dispatch_count": self.codex_dispatch_count,
            "finalized": self._finalized,
        }
        path = self.output_dir / "workspace_state.json"
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def load_state(self) -> bool:
        """Load workspace state from checkpoint. Returns True if loaded."""
        path = self.output_dir / "workspace_state.json"
        if not path.exists():
            return False

        state = json.loads(path.read_text(encoding="utf-8"))
        self.findings = [Finding(**f) for f in state.get("findings", [])]
        self.completed_sections = set(state.get("completed_sections", []))
        self.codex_dispatch_count = state.get("codex_dispatch_count", 0)
        self._finalized = state.get("finalized", False)
        logger.info(
            "  Resumed workspace: %d findings, %d sections, %d dispatches",
            len(self.findings),
            len(self.completed_sections),
            self.codex_dispatch_count,
        )
        return True
