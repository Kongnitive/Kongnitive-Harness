"""
Isaac Sim backend for Kongnitive Harness.

Drop-in replacement for vector_bridge.py's get_agent().
Exposes the same execute_skill(skill_name, params) -> ExecutionResult interface
so all hot-pushed ROS2 nodes work without modification.

Usage:
    EDGEMCP_SIM_BACKEND=isaac python -m kongnitive_ros2_edgemcp.server

Environment variables:
    ISAAC_HEADLESS   "1" (default) = headless, "0" = open Isaac Sim window
"""

import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

_agent: Optional[Any] = None
_lock = threading.Lock()
_skill_lock = threading.Lock()

# Skills mirroring the MuJoCo agent's capability set
_SUPPORTED_SKILLS = [
    # Go2 locomotion
    "walk", "turn", "navigate", "stand", "sit", "lie_down", "stop",
    "where_am_i", "patrol",
    # Arm
    "pick", "place", "detect", "scan", "home", "gripper_open", "gripper_close",
]


class _IsaacAgentProxy:
    """Isaac Sim backend agent.

    Implements the same interface as vector-os-nano's Agent so that
    all Kongnitive MCP tools and hot-pushed nodes work unchanged.
    """

    def __init__(self, sim_app: Any, world: Any) -> None:
        self._sim_app = sim_app
        self._world = world

    def execute_skill(
        self,
        skill_name: str,
        params: dict | None = None,
        **kwargs: Any,
    ) -> Any:
        with _skill_lock:
            return _dispatch_skill(self._world, skill_name, params or {})

    @property
    def skills(self) -> list[str]:
        return list(_SUPPORTED_SKILLS)

    def stop(self) -> None:
        pass

    def home(self) -> None:
        pass


def _dispatch_skill(world: Any, skill_name: str, params: dict) -> Any:
    """Map a skill call to Isaac Sim actions.

    Phase 1 (hackathon): stubs return success so the full Harness loop
    (hot-push → execute → log → AI reads result) works end-to-end.
    Replace each branch with real Isaac Sim articulation / action graph calls.
    """
    from vector_os_nano.core.types import ExecutionResult  # reuse existing dataclass

    logger.info("isaac_bridge: execute_skill(%s, %s)", skill_name, params)

    if skill_name not in _SUPPORTED_SKILLS:
        return ExecutionResult(
            success=False,
            status="failed",
            failure_reason=f"Unknown skill: {skill_name}",
        )

    # --- Locomotion stubs ---
    if skill_name == "walk":
        direction = params.get("direction", "forward")
        distance = params.get("distance", 1.0)
        # TODO: drive Isaac Sim articulation controller
        return ExecutionResult(
            success=True, status="completed",
            message=f"walked {direction} {distance}m (isaac stub)",
        )

    if skill_name == "turn":
        angle = params.get("angle", 0)
        return ExecutionResult(
            success=True, status="completed",
            message=f"turned {angle}° (isaac stub)",
        )

    if skill_name in ("stand", "sit", "lie_down", "stop", "where_am_i"):
        return ExecutionResult(
            success=True, status="completed",
            message=f"{skill_name} (isaac stub)",
        )

    if skill_name == "navigate":
        room = params.get("room", "unknown")
        return ExecutionResult(
            success=True, status="completed",
            message=f"navigated to {room} (isaac stub)",
        )

    if skill_name == "patrol":
        waypoints = params.get("waypoints", [])
        return ExecutionResult(
            success=True, status="completed",
            message=f"patrolled {len(waypoints)} waypoints (isaac stub)",
        )

    # --- Arm stubs ---
    if skill_name == "pick":
        label = params.get("object_label", "object")
        return ExecutionResult(
            success=True, status="completed",
            message=f"picked {label} (isaac stub)",
        )

    if skill_name == "place":
        x, y, z = params.get("x", 0), params.get("y", 0), params.get("z", 0)
        return ExecutionResult(
            success=True, status="completed",
            message=f"placed at ({x},{y},{z}) (isaac stub)",
        )

    if skill_name == "detect":
        query = params.get("query", "")
        return ExecutionResult(
            success=True, status="completed",
            message=f"detected '{query}' (isaac stub)",
            world_model_diff={"detected": [{"label": query, "confidence": 0.9}]},
        )

    # scan / home / gripper_open / gripper_close
    return ExecutionResult(
        success=True, status="completed",
        message=f"{skill_name} (isaac stub)",
    )


def get_agent() -> _IsaacAgentProxy:
    """Get or lazily create the shared Isaac Sim agent.

    Thread-safe double-checked locking. First call starts Isaac Sim
    (may take 30-60 s); subsequent calls return immediately.

    Returns:
        _IsaacAgentProxy with execute_skill() interface.

    Raises:
        ImportError: if isaacsim is not installed.
    """
    global _agent
    if _agent is not None:
        return _agent
    with _lock:
        if _agent is not None:
            return _agent

        headless = os.environ.get("ISAAC_HEADLESS", "1") == "1"
        logger.info("isaac_bridge: starting Isaac Sim (headless=%s) ...", headless)

        from isaacsim import SimulationApp  # noqa: PLC0415
        sim_app = SimulationApp({
            "headless": headless,
            "renderer": "RayTracedLighting",
        })

        # Lazy imports — must come after SimulationApp is created
        from omni.isaac.core import World  # noqa: PLC0415

        world = World(stage_units_in_meters=1.0)

        # Load Go2 USD asset from Isaac Nucleus (or local path)
        # Uncomment and adjust once you have the USD asset path:
        #
        # from omni.isaac.core.utils.nucleus import get_assets_root_path
        # from omni.isaac.core.robots import Robot
        # assets_root = get_assets_root_path()
        # go2_usd = f"{assets_root}/Isaac/Robots/Unitree/Go2/go2.usd"
        # robot = world.scene.add(Robot(prim_path="/World/Go2", usd_path=go2_usd))

        world.reset()

        _agent = _IsaacAgentProxy(sim_app=sim_app, world=world)
        logger.info("isaac_bridge: Isaac Sim agent ready")
    return _agent
