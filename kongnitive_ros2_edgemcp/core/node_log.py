"""
Process-level per-node execution log store.

Hot-pushed node scripts call node_log() to report skill execution results.
The MCP tool ros_get_node_log() reads from this store.

Usage in a hot-pushed node:
    from kongnitive_ros2_edgemcp.core.node_log import node_log

    node_log(self.get_name(), {
        "skill": "pick",
        "success": result.success,
        "failure_reason": result.failure_reason,
    })
"""

import threading
from collections import deque
from datetime import datetime
from typing import Any

_store: dict[str, deque] = {}
_lock = threading.Lock()
MAX_ENTRIES = 200


def node_log(node_name: str, entry: dict[str, Any]) -> None:
    """Append one execution result entry for the given node.

    Called by hot-pushed node scripts after each skill execution.
    Thread-safe; safe to call from rclpy executor threads.

    Args:
        node_name: ROS2 node name (use self.get_name() inside a Node).
        entry: Arbitrary dict. A 't' (ISO timestamp) key is added automatically.
    """
    with _lock:
        if node_name not in _store:
            _store[node_name] = deque(maxlen=MAX_ENTRIES)
        _store[node_name].append({
            "t": datetime.now().isoformat(timespec="milliseconds"),
            **entry,
        })


def get_logs(node_name: str, limit: int = 50) -> list[dict]:
    """Return the most recent log entries for a node.

    Called by the ros_get_node_log MCP tool.

    Args:
        node_name: Node identifier.
        limit: Maximum number of entries to return (most recent).

    Returns:
        List of log entry dicts, ordered oldest-first.
    """
    with _lock:
        entries = _store.get(node_name, deque())
        return list(entries)[-limit:]


def clear_logs(node_name: str) -> None:
    """Remove all log entries for a node.

    Called by NodeManager when a node is hot-replaced, so the AI
    only sees logs from the current version of the node.

    Args:
        node_name: Node identifier.
    """
    with _lock:
        _store.pop(node_name, None)
