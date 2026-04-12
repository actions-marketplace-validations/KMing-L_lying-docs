"""CLI entry point for LyingDocs."""

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .config import DEFAULTS


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("lyingdocs")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    logger.addHandler(console)

    fh = logging.FileHandler(output_dir / "pipeline.log", mode="a")
    fh.setFormatter(fmt)
    logger.addHandler(fh)


def cmd_analyze(args: argparse.Namespace) -> None:
    """Run the documentation-code misalignment analysis."""
    from .hermes_agent import HermesAgent
    from .config import load_config

    # Validate paths
    doc_path = Path(args.doc_path)
    code_path = Path(args.code_path)
    if not doc_path.is_dir():
        sys.exit(f"ERROR: Documentation directory not found: {doc_path}")
    if not code_path.is_dir():
        sys.exit(f"ERROR: Code repository not found: {code_path}")

    config = load_config(args)
    output_dir = config["output_dir"]

    setup_logging(output_dir)
    logger = logging.getLogger("lyingdocs")
    logger.info(
        "LyingDocs starting — doc=%s  code=%s  output=%s",
        doc_path, code_path, output_dir,
    )

    agent = HermesAgent(
        config=config,
        doc_path=doc_path,
        code_path=code_path,
        output_dir=output_dir,
    )

    report_path = agent.run()
    logger.info("Done. Report at: %s", report_path)
    print(f"\nReport generated: {report_path}")


def cmd_version(_args: argparse.Namespace) -> None:
    """Print version and exit."""
    print(f"lyingdocs {__version__}")


def main():
    parser = argparse.ArgumentParser(
        prog="lyingdocs",
        description="LyingDocs: Documentation-Code Misalignment Detection",
    )
    subparsers = parser.add_subparsers(dest="command")

    # -- analyze subcommand --
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze documentation against code for misalignments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  lyingdocs analyze --doc-path docs/ --code-path . -o output/audit
  lyingdocs analyze --doc-path docs/ --code-path . --argus-backend=local
  lyingdocs analyze --doc-path docs/ --code-path . --config lyingdocs.toml
""",
    )
    analyze_parser.add_argument(
        "--doc-path", required=True,
        help="Path to documentation root directory",
    )
    analyze_parser.add_argument(
        "--code-path", required=True,
        help="Path to code repository root",
    )
    analyze_parser.add_argument(
        "--output-dir", "-o", default="output",
        help="Output directory (default: output/)",
    )
    analyze_parser.add_argument(
        "--hermes-model", default=None,
        help="Hermes (planner) LLM model name (overrides config/env)",
    )
    analyze_parser.add_argument(
        "--hermes-base-url", default=None,
        help="Hermes API base URL (overrides config/env)",
    )
    analyze_parser.add_argument(
        "--argus-backend", choices=("codex", "claude_code", "local"), default=None,
        help="Argus (code analysis) backend: codex, claude_code, or local",
    )
    analyze_parser.add_argument(
        "--argus-model", default=None,
        help="Argus LLM model name (overrides config/env)",
    )
    analyze_parser.add_argument(
        "--argus-base-url", default=None,
        help="Argus API base URL (overrides config/env)",
    )
    analyze_parser.add_argument(
        "--argus-codex-provider", default=None,
        help="Argus/codex backend: provider name",
    )
    analyze_parser.add_argument(
        "--argus-codex-wire-api", default=None,
        help="Argus/codex backend: provider wire_api ('responses' or 'chat')",
    )
    analyze_parser.add_argument(
        "--max-dispatches", type=int, default=None,
        help=f"Max Argus dispatches (default: {DEFAULTS['max_dispatches']}, "
             "config file / env override this)",
    )
    analyze_parser.add_argument(
        "--max-iterations", type=int, default=None,
        help=f"Max Hermes loop iterations (default: {DEFAULTS['max_iterations']}, "
             "config file / env override this)",
    )
    analyze_parser.add_argument(
        "--config", default=None,
        help="Path to config file (default: auto-detect lyingdocs.toml)",
    )
    analyze_parser.add_argument(
        "--resume", action="store_true",
        help="Resume from workspace checkpoint if available",
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    # -- version subcommand --
    version_parser = subparsers.add_parser("version", help="Show version")
    version_parser.set_defaults(func=cmd_version)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)
