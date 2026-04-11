"""Documentation hierarchy discovery and indexing."""

import json
import logging
from pathlib import Path

logger = logging.getLogger("lyingdocs")

# File extensions considered documentation
DOC_EXTENSIONS = {".md", ".rst", ".txt", ".yaml", ".yml", ".json", ".toml"}

# Known TOC / navigation files
TOC_FILES = {
    "_toc.yml", "mkdocs.yml", "SUMMARY.md", "sidebar.json",
    "docs.json", "mint.json", "docusaurus.config.js",
}

# Classification heuristics by filename/path patterns
PRIORITY_KEYWORDS = {
    "high": ["readme", "architecture", "design", "api", "config", "setup", "install",
             "getting-started", "quickstart", "overview", "reference", "guide"],
    "medium": ["tutorial", "example", "usage", "faq", "troubleshoot", "concepts",
               "plugin", "provider", "channel", "command"],
    "low": ["changelog", "contributing", "license", "security", "roadmap",
            "incident", "vision", "legal"],
}


class DocFile:
    """Metadata about a single documentation file."""

    __slots__ = ("rel_path", "abs_path", "size", "priority")

    def __init__(self, rel_path: str, abs_path: Path, size: int, priority: str):
        self.rel_path = rel_path
        self.abs_path = abs_path
        self.size = size
        self.priority = priority

    def to_dict(self) -> dict:
        return {
            "path": self.rel_path,
            "size": self.size,
            "priority": self.priority,
        }


class DocTree:
    """Discovers and indexes a documentation directory tree."""

    def __init__(self, doc_root: Path):
        self.doc_root = doc_root.resolve()
        self.files: list[DocFile] = []
        self.toc_file: str | None = None

    def build_index(self) -> None:
        """Scan doc_root for documentation files and classify them."""
        logger.info("Building doc tree index from %s", self.doc_root)

        # Detect TOC file
        for toc_name in TOC_FILES:
            toc_path = self.doc_root / toc_name
            if toc_path.exists():
                self.toc_file = toc_name
                logger.info("  Found TOC file: %s", toc_name)
                break

        # Walk and index
        for path in sorted(self.doc_root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in DOC_EXTENSIONS:
                continue
            # Skip hidden dirs and common non-doc dirs
            parts = path.relative_to(self.doc_root).parts
            if any(p.startswith(".") or p in ("node_modules", "__pycache__", "dist", ".git") for p in parts):
                continue

            rel = str(path.relative_to(self.doc_root))
            size = path.stat().st_size
            priority = self._classify_priority(rel)
            self.files.append(DocFile(rel, path, size, priority))

        logger.info("  Indexed %d documentation files", len(self.files))

    def _classify_priority(self, rel_path: str) -> str:
        """Classify file priority based on path/name heuristics."""
        lower = rel_path.lower()
        for level, keywords in PRIORITY_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return level
        return "medium"

    def get_overview(self, max_depth: int = 3) -> str:
        """Return a text overview of the doc tree for the agent's kickoff message."""
        lines = [
            f"# Documentation Tree: {self.doc_root.name}",
            f"Total files: {len(self.files)}",
            f"Total size: {sum(f.size for f in self.files):,} bytes",
        ]

        if self.toc_file:
            lines.append(f"TOC file: {self.toc_file}")

        # Count by priority
        by_priority = {"high": [], "medium": [], "low": []}
        for f in self.files:
            by_priority[f.priority].append(f)

        lines.append(f"\nHigh priority ({len(by_priority['high'])} files):")
        for f in by_priority["high"]:
            lines.append(f"  [{_human_size(f.size):>7s}] {f.rel_path}")

        lines.append(f"\nMedium priority ({len(by_priority['medium'])} files):")
        for f in by_priority["medium"][:30]:
            lines.append(f"  [{_human_size(f.size):>7s}] {f.rel_path}")
        if len(by_priority["medium"]) > 30:
            lines.append(f"  ... and {len(by_priority['medium']) - 30} more")

        lines.append(f"\nLow priority ({len(by_priority['low'])} files):")
        for f in by_priority["low"][:10]:
            lines.append(f"  [{_human_size(f.size):>7s}] {f.rel_path}")
        if len(by_priority["low"]) > 10:
            lines.append(f"  ... and {len(by_priority['low']) - 10} more")

        # Directory tree (compact)
        lines.append("\n## Directory Structure")
        dirs_seen: set[str] = set()
        for f in self.files:
            parts = Path(f.rel_path).parts
            for depth in range(min(len(parts) - 1, max_depth)):
                d = "/".join(parts[: depth + 1])
                if d not in dirs_seen:
                    dirs_seen.add(d)
                    indent = "  " * depth
                    lines.append(f"{indent}{parts[depth]}/")

        return "\n".join(lines)

    def save_index(self, output_dir: Path) -> None:
        """Save the index to a JSON file for reference."""
        data = {
            "doc_root": str(self.doc_root),
            "toc_file": self.toc_file,
            "files": [f.to_dict() for f in self.files],
        }
        out_path = output_dir / "doc_index.json"
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("  Saved doc index to %s", out_path)


def _human_size(size: int) -> str:
    """Format byte size for display."""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / (1024 * 1024):.1f}MB"
