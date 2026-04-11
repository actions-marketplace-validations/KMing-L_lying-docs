"""Configuration loading for LyingDocs."""

import argparse
import os
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

DEFAULTS = {
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o",
    "codex_provider": "openai",
    "wire_api": "responses",
    "codex_enabled": True,
    "codex_path": None,
    "max_dispatches": 20,
    "max_iterations": 50,
    "codex_task_timeout": 1200,
    "token_budget": 524_288,
}

CONFIG_FILE_SEARCH = [
    Path("lyingdocs.toml"),
    Path.home() / ".config" / "lyingdocs" / "config.toml",
]


def _find_config_file(explicit: str | None = None) -> Path | None:
    """Locate the config file. Explicit path > local > user-level."""
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        sys.exit(f"ERROR: Config file not found: {p}")
    for candidate in CONFIG_FILE_SEARCH:
        if candidate.is_file():
            return candidate
    return None


def _load_config_file(path: Path) -> dict:
    """Parse a TOML config file and flatten into a config dict."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    flat = {}
    # Top-level keys
    for key in ("base_url", "model"):
        if key in raw:
            flat[key] = raw[key]

    # [codex] section
    codex = raw.get("codex", {})
    if "enabled" in codex:
        flat["codex_enabled"] = codex["enabled"]
    if "provider" in codex:
        flat["codex_provider"] = codex["provider"]
        flat["wire_api"] = codex.get("wire_api", "responses")
    if "path" in codex and codex["path"]:
        flat["codex_path"] = codex["path"]

    # [limits] section
    limits = raw.get("limits", {})
    for key in ("max_dispatches", "max_iterations", "codex_task_timeout", "token_budget"):
        if key in limits:
            flat[key] = int(limits[key])

    return flat


def load_config(args: argparse.Namespace) -> dict:
    """Merge defaults <- config file <- .env <- CLI args into a single config dict."""
    load_dotenv()

    # Start with defaults
    config = dict(DEFAULTS)

    # Layer: config file
    config_file = _find_config_file(getattr(args, "config", None))
    if config_file:
        config.update(_load_config_file(config_file))

    # Layer: environment variables
    env_map = {
        "BASE_URL": "base_url",
        "MODEL": "model",
        "CODEX_PROVIDER": "codex_provider",
        "CODEX_WIRE_API": "wire_api",
        "CODEX_PATH": "codex_path",
        "CODEX_TASK_TIMEOUT": "codex_task_timeout",
        "TOKEN_BUDGET": "token_budget",
    }
    for env_key, config_key in env_map.items():
        val = os.getenv(env_key)
        if val:
            if config_key in ("codex_task_timeout", "token_budget"):
                config[config_key] = int(val)
            else:
                config[config_key] = val

    # Layer: CLI args (only override if explicitly provided / non-None)
    if getattr(args, "base_url", None):
        config["base_url"] = args.base_url
    if getattr(args, "model", None):
        config["model"] = args.model
    if getattr(args, "codex_provider", None):
        config["codex_provider"] = args.codex_provider
    if getattr(args, "wire_api", None):
        config["wire_api"] = args.wire_api
    if hasattr(args, "max_dispatches") and args.max_dispatches is not None:
        config["max_dispatches"] = args.max_dispatches
    if hasattr(args, "max_iterations") and args.max_iterations is not None:
        config["max_iterations"] = args.max_iterations
    if getattr(args, "no_codex", False):
        config["codex_enabled"] = False

    # Always from args / context
    config["api_key"] = os.getenv("OPENAI_API_KEY", "")
    config["doc_path"] = Path(args.doc_path)
    config["code_path"] = Path(args.code_path)
    config["output_dir"] = Path(args.output_dir)
    config["resume"] = getattr(args, "resume", False)

    if not config["api_key"]:
        sys.exit("ERROR: OPENAI_API_KEY not set. Export it or add to .env file.")

    return config
