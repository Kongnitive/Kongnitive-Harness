"""
Persistent successful node example store.

This module complements the in-memory node_log store so successful node
strategies can be reused across server restarts and cold-start sessions.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any


_STORE_LOCK = Lock()
_STORE_FILENAME = "successful_node_examples.json"


def get_store_path(script_dir: str | Path) -> Path:
    """Return the JSON store path associated with a node script directory."""
    script_path = Path(script_dir).expanduser()
    return script_path.parent / _STORE_FILENAME


def load_examples(store_path: str | Path) -> list[dict[str, Any]]:
    """Load persisted successful examples from disk."""
    path = Path(store_path)
    if not path.exists():
        return []

    with _STORE_LOCK:
        data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def save_examples(store_path: str | Path, examples: list[dict[str, Any]]) -> None:
    """Persist the complete example list to disk."""
    path = Path(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(examples, ensure_ascii=False, indent=2)
    with _STORE_LOCK:
        path.write_text(payload, encoding="utf-8")


def find_success_entries(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return entries that indicate some successful execution."""
    return [entry for entry in logs if entry.get("success") is True]


def has_goal_success(logs: list[dict[str, Any]]) -> bool:
    """Return whether the logs include a successful final goal entry."""
    return any(
        entry.get("skill") == "goal" and entry.get("success") is True
        for entry in logs
    )


def build_example(
    *,
    node_name: str,
    script: str,
    script_path: str,
    recent_logs: list[dict[str, Any]],
    source: str,
    goal: str = "",
    summary: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Build a normalized example record."""
    script_hash = hashlib.sha256(script.encode("utf-8")).hexdigest()[:16]
    success_entries = find_success_entries(recent_logs)
    timestamp = datetime.now().isoformat(timespec="seconds")
    return {
        "id": f"{node_name}:{script_hash}",
        "node_name": node_name,
        "script_path": str(script_path),
        "script": script,
        "source": source,
        "goal": goal,
        "summary": summary,
        "tags": list(tags or []),
        "success_count": len(success_entries),
        "has_goal_success": has_goal_success(recent_logs),
        "last_success": success_entries[-1] if success_entries else None,
        "recent_logs": recent_logs[-20:],
        "updated_at": timestamp,
    }


def upsert_example(store_path: str | Path, example: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace an example in the persistent store."""
    examples = load_examples(store_path)
    by_id = {item.get("id"): item for item in examples if item.get("id")}
    by_id[example["id"]] = example
    updated = sorted(
        by_id.values(),
        key=lambda item: (
            str(item.get("last_success", {}).get("t", "")),
            str(item.get("updated_at", "")),
            str(item.get("node_name", "")),
        ),
        reverse=True,
    )
    save_examples(store_path, updated)
    return example


def filter_examples(
    examples: list[dict[str, Any]],
    goal_filter: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Filter and rank examples for retrieval."""
    filt = (goal_filter or "").strip().lower()
    matched: list[dict[str, Any]] = []
    for item in examples:
        haystacks = [
            str(item.get("node_name", "")).lower(),
            str(item.get("script", "")).lower(),
            str(item.get("goal", "")).lower(),
            str(item.get("summary", "")).lower(),
            " ".join(str(tag).lower() for tag in item.get("tags", [])),
            " ".join(str(entry).lower() for entry in item.get("recent_logs", [])),
        ]
        if filt and not any(filt in hay for hay in haystacks):
            continue
        matched.append(item)

    matched.sort(
        key=lambda item: (
            bool(item.get("has_goal_success")),
            int(item.get("success_count", 0)),
            str((item.get("last_success") or {}).get("t", "")),
            str(item.get("updated_at", "")),
            str(item.get("node_name", "")),
        ),
        reverse=True,
    )
    return matched[: max(1, int(limit))]


def merge_examples(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge example groups with later duplicates ignored."""
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for item in group:
            item_id = str(item.get("id") or "")
            if item_id and item_id not in merged:
                merged[item_id] = item
    return list(merged.values())
