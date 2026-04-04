"""
Process-level singleton for the vector-os-nano MuJoCo simulation Agent.

Shared across all hot-pushed ROS2 nodes in this process so that a single
MuJoCo physics instance is reused. The Agent is lazily initialised on first
call to get_agent().

Usage in a hot-pushed node:
    from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent

    self.agent = get_agent()
    result = self.agent.execute_skill("pick", {"object_label": "red_cube"})
"""

import threading
from typing import Any, Optional

_agent: Optional[Any] = None
_lock = threading.Lock()


def get_agent():
    """Get or lazily create the shared MuJoCo sim Agent.

    Thread-safe double-checked locking. The first call initialises
    MuJoCo (headless) which takes ~2–5 s; subsequent calls return
    immediately.

    Returns:
        vector_os_nano.core.agent.Agent instance backed by MuJoCo sim.

    Raises:
        ImportError: if vector-os-nano is not installed.
    """
    global _agent
    if _agent is not None:
        return _agent
    with _lock:
        if _agent is not None:
            return _agent
        from vector_os_nano.mcp.server import create_sim_agent  # noqa: PLC0415
        _agent = create_sim_agent(headless=True)
    return _agent
