"""Configuration loading for LyingDocs."""

import argparse
import os
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

DEFAULTS = {
    # Hermes (planner agent)
    "hermes_model": "gpt-4o",
    "hermes_base_url": "https://api.openai.com/v1",
    "hermes_api_key_env": "OPENAI_API_KEY",

    # Argus (code analysis agent)
    "argus_backend": "local",  # "codex" | "claude_code" | "local"
    "argus_model": "gpt-4o",
    "argus_base_url": "https://api.openai.com/v1",
    "argus_api_key_env": "OPENAI_API_KEY",

    # Argus / codex backend
    "argus_codex_provider": "openai",
    "argus_codex_wire_api": "responses",
    "argus_codex_path": None,

    # Argus / claude_code backend
    "argus_claude_code_path": None,

    # Argus / local backend
    "argus_local_max_iterations": 25,
    "argus_local_max_read_bytes": 200_000,

    # Shared limits
    "max_dispatches": 20,
    "max_iterations": 50,
    "argus_task_timeout": 1200,
    "token_budget": 524_288,
}

CONFIG_FILE_SEARCH = [
    Path("lyingdocs.toml"),
    Path.home() / ".config" / "lyingdocs" / "config.toml",
]

VALID_ARGUS_BACKENDS = ("codex", "claude_code", "local")


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


def _reject_legacy(raw: dict, path: Path) -> None:
    """Hard-break guard for the pre-split config format."""
    legacy_top = [k for k in ("model", "base_url") if k in raw]
    legacy_sections = [s for s in ("codex",) if s in raw]
    if legacy_top or legacy_sections:
        parts = []
        if legacy_top:
            parts.append("top-level keys " + ", ".join(repr(k) for k in legacy_top))
        if legacy_sections:
            parts.append("sections " + ", ".join(f"[{s}]" for s in legacy_sections))
        sys.exit(
            f"ERROR: {path} uses the legacy config format ({'; '.join(parts)}). "
            "Migrate to the new schema:\n"
            "  [hermes]\n    model = \"...\"\n    base_url = \"...\"\n"
            "  [argus]\n    backend = \"codex\" | \"claude_code\" | \"local\"\n"
            "    model = \"...\"\n    base_url = \"...\"\n"
            "  [argus.codex]\n    provider = \"...\"\n    wire_api = \"...\"\n    path = \"...\"\n"
            "See README.md for the full example."
        )


def _load_config_file(path: Path) -> dict:
    """Parse a TOML config file and flatten into a config dict."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    _reject_legacy(raw, path)

    flat: dict = {}

    # [hermes]
    hermes = raw.get("hermes", {})
    if "model" in hermes:
        flat["hermes_model"] = hermes["model"]
    if "base_url" in hermes:
        flat["hermes_base_url"] = hermes["base_url"]
    if "api_key_env" in hermes:
        flat["hermes_api_key_env"] = hermes["api_key_env"]

    # [argus]
    argus = raw.get("argus", {})
    if "backend" in argus:
        backend = argus["backend"]
        if backend not in VALID_ARGUS_BACKENDS:
            sys.exit(
                f"ERROR: argus.backend = {backend!r} in {path}. "
                f"Must be one of: {', '.join(VALID_ARGUS_BACKENDS)}."
            )
        flat["argus_backend"] = backend
    if "model" in argus:
        flat["argus_model"] = argus["model"]
    if "base_url" in argus:
        flat["argus_base_url"] = argus["base_url"]
    if "api_key_env" in argus:
        flat["argus_api_key_env"] = argus["api_key_env"]

    # [argus.codex]
    argus_codex = argus.get("codex", {})
    if "provider" in argus_codex:
        flat["argus_codex_provider"] = argus_codex["provider"]
    if "wire_api" in argus_codex:
        flat["argus_codex_wire_api"] = argus_codex["wire_api"]
    if argus_codex.get("path"):
        flat["argus_codex_path"] = argus_codex["path"]

    # [argus.claude_code]
    argus_cc = argus.get("claude_code", {})
    if argus_cc.get("path"):
        flat["argus_claude_code_path"] = argus_cc["path"]

    # [argus.local]
    argus_local = argus.get("local", {})
    if "max_iterations" in argus_local:
        flat["argus_local_max_iterations"] = int(argus_local["max_iterations"])
    if "max_read_bytes" in argus_local:
        flat["argus_local_max_read_bytes"] = int(argus_local["max_read_bytes"])

    # [limits]
    limits = raw.get("limits", {})
    for key in (
        "max_dispatches",
        "max_iterations",
        "argus_task_timeout",
        "token_budget",
    ):
        if key in limits:
            flat[key] = int(limits[key])

    return flat


def _resolve_api_key(config: dict, agent: str) -> str:
    env_var = config.get(f"{agent}_api_key_env") or "OPENAI_API_KEY"
    return os.getenv(env_var, "")


def load_config(args: argparse.Namespace) -> dict:
    """Merge defaults <- config file <- env vars <- CLI args into a single config dict."""
    load_dotenv()

    config = dict(DEFAULTS)

    # Layer: config file
    config_file = _find_config_file(getattr(args, "config", None))
    if config_file:
        config.update(_load_config_file(config_file))

    # Layer: environment variables
    env_map = {
        "HERMES_MODEL": "hermes_model",
        "HERMES_BASE_URL": "hermes_base_url",
        "ARGUS_BACKEND": "argus_backend",
        "ARGUS_MODEL": "argus_model",
        "ARGUS_BASE_URL": "argus_base_url",
        "ARGUS_CODEX_PROVIDER": "argus_codex_provider",
        "ARGUS_CODEX_WIRE_API": "argus_codex_wire_api",
        "ARGUS_CODEX_PATH": "argus_codex_path",
        "ARGUS_CLAUDE_CODE_PATH": "argus_claude_code_path",
        "ARGUS_TASK_TIMEOUT": "argus_task_timeout",
        "TOKEN_BUDGET": "token_budget",
    }
    for env_key, config_key in env_map.items():
        val = os.getenv(env_key)
        if val:
            if config_key in ("argus_task_timeout", "token_budget"):
                config[config_key] = int(val)
            else:
                config[config_key] = val

    # Layer: CLI args
    cli_map = {
        "hermes_model": "hermes_model",
        "hermes_base_url": "hermes_base_url",
        "argus_backend": "argus_backend",
        "argus_model": "argus_model",
        "argus_base_url": "argus_base_url",
        "argus_codex_provider": "argus_codex_provider",
        "argus_codex_wire_api": "argus_codex_wire_api",
    }
    for attr, config_key in cli_map.items():
        val = getattr(args, attr, None)
        if val:
            config[config_key] = val

    for attr in ("max_dispatches", "max_iterations"):
        val = getattr(args, attr, None)
        if val is not None:
            config[attr] = val

    if config["argus_backend"] not in VALID_ARGUS_BACKENDS:
        sys.exit(
            f"ERROR: argus backend {config['argus_backend']!r} is invalid. "
            f"Must be one of: {', '.join(VALID_ARGUS_BACKENDS)}."
        )

    # API keys (per-agent)
    config["hermes_api_key"] = _resolve_api_key(config, "hermes")
    config["argus_api_key"] = _resolve_api_key(config, "argus")

    # Always from args / context
    config["doc_path"] = Path(args.doc_path)
    config["code_path"] = Path(args.code_path)
    config["output_dir"] = Path(args.output_dir)
    config["resume"] = getattr(args, "resume", False)

    if not config["hermes_api_key"]:
        sys.exit(
            f"ERROR: Hermes API key not found. "
            f"Set {config['hermes_api_key_env']} in your environment or .env file."
        )
    # Argus only needs a key for backends that call an API in-process.
    if config["argus_backend"] in ("local",) and not config["argus_api_key"]:
        sys.exit(
            f"ERROR: Argus (backend={config['argus_backend']}) API key not found. "
            f"Set {config['argus_api_key_env']} in your environment or .env file."
        )

    return config
