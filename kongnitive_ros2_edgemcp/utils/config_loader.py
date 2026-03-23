"""Configuration loading helpers for Kongnitive ROS2 EdgeMCP."""

import os
from pathlib import Path
from typing import Dict, Any

import yaml


def _candidate_config_dirs() -> list:
    env_dir = os.getenv("KONGNITIVE_CONFIG_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir))

    pkg_dir = Path(__file__).resolve().parents[1]
    repo_dir = pkg_dir.parent

    # Prefer repository-level config during development to avoid drift
    # between duplicated files.
    candidates.append(repo_dir / "config")
    candidates.append(pkg_dir / "config")

    # Deduplicate while preserving order
    unique = []
    seen = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def get_config_dir() -> Path:
    """Return first existing config directory."""
    for config_dir in _candidate_config_dirs():
        if config_dir.exists() and config_dir.is_dir():
            return config_dir
    return _candidate_config_dirs()[0]


def load_server_config() -> Dict[str, Any]:
    """Load server_config.yaml from available config directories."""
    config_dir = get_config_dir()
    config_path = config_dir / "server_config.yaml"

    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_system_prompt(default_prompt: str = "") -> str:
    """Load system prompt text from config directory."""
    config_dir = get_config_dir()
    prompt_path = config_dir / "system_prompt.txt"

    if not prompt_path.exists():
        return default_prompt

    return prompt_path.read_text(encoding="utf-8")
