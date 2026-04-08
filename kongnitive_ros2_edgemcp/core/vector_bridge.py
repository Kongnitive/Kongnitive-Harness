"""
Process-level singleton for the vector-os-nano MuJoCo simulation Agent.

Shared across all hot-pushed ROS2 nodes in this process so that a single
MuJoCo physics instance is reused. The Agent is lazily initialised on first
call to get_agent().

Because multiple ROS2 nodes share the same Agent (and thus the same MuJoCo
physics state), all execute_skill calls are serialized through a global lock
to prevent concurrent physics mutations that cause NaN explosions.

Usage in a hot-pushed node:
    from kongnitive_ros2_edgemcp.core.vector_bridge import get_agent

    self.agent = get_agent()
    result = self.agent.execute_skill("pick", {"object_label": "red_cube"})
"""

import os
import threading
from typing import Any, Optional

_agent: Optional[Any] = None
_lock = threading.Lock()
_skill_lock = threading.Lock()

_SIM_BACKEND = os.environ.get("EDGEMCP_SIM_BACKEND", "mujoco")


class _ThreadSafeAgentProxy:
    """Wraps an Agent so that execute_skill calls are serialized."""

    def __init__(self, agent: Any) -> None:
        self._agent = agent

    def execute_skill(self, *args: Any, **kwargs: Any) -> Any:
        with _skill_lock:
            return self._agent.execute_skill(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)


def get_agent():
    """Get or lazily create the shared sim Agent.

    Thread-safe double-checked locking. Backend is selected via
    EDGEMCP_SIM_BACKEND env var ("mujoco" default, or "isaac").

    Returns:
        Thread-safe agent proxy with execute_skill() interface.

    Raises:
        ImportError: if the selected backend is not installed.
    """
    global _agent
    if _agent is not None:
        return _agent
    with _lock:
        if _agent is not None:
            return _agent

        if _SIM_BACKEND == "isaac":
            from kongnitive_ros2_edgemcp.core.isaac_bridge import get_agent as _isaac_get  # noqa: PLC0415
            _agent = _isaac_get()
            return _agent

        headless = os.environ.get("MUJOCO_HEADLESS", "1") == "1"
        mode = os.environ.get("EDGEMCP_AGENT_MODE", "go2_arm")

        if mode == "arm_only":
            from vector_os_nano.mcp.server import create_sim_agent  # noqa: PLC0415
            raw_agent = create_sim_agent(headless=headless)
        else:
            from vector_os_nano.mcp.server import create_go2_arm_sim_agent  # noqa: PLC0415
            raw_agent = create_go2_arm_sim_agent(headless=headless)

        _agent = _ThreadSafeAgentProxy(raw_agent)
    return _agent
