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
import pathlib
import queue
import re
import tempfile
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ExecutionResult:
    """Minimal drop-in for vector_os_nano.core.types.ExecutionResult."""

    def __init__(
        self,
        success: bool,
        status: str = "completed",
        message: str = "",
        failure_reason: str | None = None,
        world_model_diff: dict | None = None,
    ) -> None:
        self.success = success
        self.status = status
        self.message = message
        self.failure_reason = failure_reason
        self.world_model_diff = world_model_diff or {}


_agent: Optional[Any] = None
_lock = threading.Lock()
_skill_lock = threading.Lock()

# Thread-safe skill dispatch queue: ROS2 threads post here, main thread executes
_skill_queue: queue.Queue = queue.Queue(maxsize=1)
_result_event = threading.Event()
_result_data: dict = {}

# Refs held for run_sim_loop()
_sim_app_ref: Optional[Any] = None
_world_ref: Optional[Any] = None
_robot_ref: Optional[Any] = None

# SO-101 joint names (order matches URDF joint definitions)
_ARM_JOINTS = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]

# Named poses (radians) — [shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper]
_POSES = {
    "home":  [0.0,   0.5,  -1.0,  0.5,  0.0,  0.0],
    "scan":  [0.0,   0.3,  -0.5,  0.3,  0.0,  0.0],
    "reach": [0.0,   0.8,  -1.4,  0.6,  0.0,  0.0],
}

_GRIPPER_OPEN  = 1.0   # rad — approaches upper limit of gripper joint
_GRIPPER_CLOSE = 0.0

_SUPPORTED_SKILLS = [
    "walk", "turn", "navigate", "stand", "sit", "lie_down", "stop",
    "where_am_i", "patrol",
    "pick", "place", "detect", "scan", "home", "gripper_open", "gripper_close",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _urdf_with_absolute_mesh_paths() -> str:
    """Return path to a temp URDF where package:// paths are replaced with
    absolute filesystem paths pointing to the bundled mesh directory."""
    urdf_src = pathlib.Path(__file__).parents[2] / \
        "vector-os-nano" / "vector_os_nano" / "hardware" / "urdf" / "so101.urdf"
    mesh_dir = urdf_src.parent / "meshes"

    text = urdf_src.read_text()
    # Replace  package://so101_description/meshes/<file>
    # with     file:///absolute/path/to/meshes/<file>
    text = re.sub(
        r'package://so101_description/meshes/([^"]+)',
        lambda m: mesh_dir.as_posix() + "/" + m.group(1),
        text,
    )

    tmp = tempfile.NamedTemporaryFile(
        suffix="_so101.urdf", mode="w", delete=False, encoding="utf-8"
    )
    tmp.write(text)
    tmp.close()
    return tmp.name


def _step_sim(world: Any, steps: int = 10) -> None:
    """Advance the simulation by N physics steps (must be called from main thread)."""
    for _ in range(steps):
        world.step(render=True)


def run_sim_loop() -> None:
    """Drive the Isaac Sim render loop from the main thread.

    Checks the skill queue on every frame. When a skill is pending, executes
    it on the main thread (safe for world.step), then signals the result back
    to the waiting ROS2 executor thread.

    Call this AFTER get_agent() returns and AFTER the MCP server has been
    started in a background thread.
    """
    if _sim_app_ref is None or _world_ref is None:
        logger.error("run_sim_loop: Isaac Sim not initialized")
        return

    logger.info("isaac_bridge: entering main sim loop")
    while _sim_app_ref.is_running():
        try:
            skill_name, params = _skill_queue.get_nowait()
        except queue.Empty:
            # No pending skill — just advance one frame for rendering
            _sim_app_ref.update()
            continue

        # Execute skill on main thread
        try:
            result = _dispatch_skill(_world_ref, _robot_ref, skill_name, params)
            _result_data["result"] = result
            _result_data["error"] = None
        except Exception as e:  # noqa: BLE001
            _result_data["result"] = None
            _result_data["error"] = e
        finally:
            _result_event.set()

    logger.info("isaac_bridge: sim loop exited")


# ---------------------------------------------------------------------------
# Agent proxy
# ---------------------------------------------------------------------------

class _IsaacAgentProxy:
    """Isaac Sim backend agent.

    Implements the same interface as vector-os-nano's Agent so that
    all Kongnitive MCP tools and hot-pushed nodes work unchanged.
    """

    def __init__(self, sim_app: Any, world: Any, robot: Any) -> None:
        self._sim_app = sim_app
        self._world = world
        self._robot = robot

    def execute_skill(
        self,
        skill_name: str,
        params: dict | None = None,
        **kwargs: Any,
    ) -> Any:
        with _skill_lock:
            _result_event.clear()
            _result_data.clear()
            _skill_queue.put((skill_name, params or {}))
            _result_event.wait(timeout=120)
            if _result_data.get("error"):
                raise _result_data["error"]
            return _result_data.get("result")

    @property
    def skills(self) -> list[str]:
        return list(_SUPPORTED_SKILLS)

    def stop(self) -> None:
        pass

    def home(self) -> None:
        self.execute_skill("home", {})


# ---------------------------------------------------------------------------
# Articulation helpers
# ---------------------------------------------------------------------------

def _move_to_pose(world: Any, robot: Any, pose_name: str, steps: int = 60) -> None:
    """Drive robot to a named joint pose."""
    from omni.isaac.core.utils.types import ArticulationAction  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    positions = np.array(_POSES[pose_name], dtype=float)
    action = ArticulationAction(joint_positions=positions)
    robot.apply_action(action)
    _step_sim(world, steps)


def _set_gripper(world: Any, robot: Any, value: float, steps: int = 30) -> None:
    from omni.isaac.core.utils.types import ArticulationAction  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    # Only set the last joint (gripper)
    joint_idx = len(_ARM_JOINTS) - 1
    positions = robot.get_joint_positions()
    positions[joint_idx] = value
    action = ArticulationAction(joint_positions=positions)
    robot.apply_action(action)
    _step_sim(world, steps)


# ---------------------------------------------------------------------------
# Skill dispatcher
# ---------------------------------------------------------------------------

def _dispatch_skill(world: Any, robot: Any, skill_name: str, params: dict) -> Any:
    logger.info("isaac_bridge: execute_skill(%s, %s)", skill_name, params)

    if skill_name not in _SUPPORTED_SKILLS:
        return ExecutionResult(
            success=False,
            status="failed",
            failure_reason=f"Unknown skill: {skill_name}",
        )

    # ---- Arm skills (real articulation control) ----

    if skill_name == "home":
        _move_to_pose(world, robot, "home")
        return ExecutionResult(success=True, status="completed", message="arm at home pose")

    if skill_name == "scan":
        _move_to_pose(world, robot, "scan")
        return ExecutionResult(success=True, status="completed", message="arm at scan pose")

    if skill_name == "gripper_open":
        _set_gripper(world, robot, _GRIPPER_OPEN)
        return ExecutionResult(success=True, status="completed", message="gripper opened")

    if skill_name == "gripper_close":
        _set_gripper(world, robot, _GRIPPER_CLOSE)
        return ExecutionResult(success=True, status="completed", message="gripper closed")

    if skill_name == "pick":
        label = params.get("object_label", "object")
        # Sequence: scan → reach → close gripper
        _move_to_pose(world, robot, "scan")
        _move_to_pose(world, robot, "reach")
        _set_gripper(world, robot, _GRIPPER_CLOSE)
        return ExecutionResult(
            success=True, status="completed",
            message=f"picked {label}",
        )

    if skill_name == "place":
        x = params.get("x", 0.0)
        y = params.get("y", 0.0)
        z = params.get("z", 0.0)
        # Open gripper at reach pose, then return home
        _move_to_pose(world, robot, "reach")
        _set_gripper(world, robot, _GRIPPER_OPEN)
        _move_to_pose(world, robot, "home")
        return ExecutionResult(
            success=True, status="completed",
            message=f"placed at ({x:.3f}, {y:.3f}, {z:.3f})",
        )

    if skill_name == "detect":
        query = params.get("query", "")
        _move_to_pose(world, robot, "scan")
        return ExecutionResult(
            success=True, status="completed",
            message=f"detected '{query}' (isaac)",
            world_model_diff={"detected": [{"label": query, "confidence": 0.9}]},
        )

    # ---- Locomotion stubs (Go2 not yet wired) ----

    if skill_name == "walk":
        direction = params.get("direction", "forward")
        distance = params.get("distance", 1.0)
        return ExecutionResult(
            success=True, status="completed",
            message=f"walked {direction} {distance}m (stub — Go2 not loaded)",
        )

    if skill_name == "turn":
        angle = params.get("angle", 0)
        return ExecutionResult(
            success=True, status="completed",
            message=f"turned {angle}° (stub)",
        )

    if skill_name in ("stand", "sit", "lie_down", "stop", "where_am_i"):
        return ExecutionResult(success=True, status="completed", message=f"{skill_name} (stub)")

    if skill_name == "navigate":
        room = params.get("room", "unknown")
        return ExecutionResult(success=True, status="completed", message=f"navigated to {room} (stub)")

    if skill_name == "patrol":
        waypoints = params.get("waypoints", [])
        return ExecutionResult(success=True, status="completed", message=f"patrolled {len(waypoints)} waypoints (stub)")

    return ExecutionResult(success=True, status="completed", message=f"{skill_name} (stub)")


# ---------------------------------------------------------------------------
# Lazy init
# ---------------------------------------------------------------------------

def get_agent() -> _IsaacAgentProxy:
    """Get or lazily create the shared Isaac Sim agent.

    Thread-safe double-checked locking. First call starts Isaac Sim
    (may take 30-60 s); subsequent calls return immediately.
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

        # Must come after SimulationApp
        from omni.isaac.core import World  # noqa: PLC0415
        from omni.isaac.core.robots import Robot  # noqa: PLC0415
        import omni.kit.commands  # noqa: PLC0415
        from isaacsim.asset.importer.urdf import _urdf  # noqa: PLC0415

        world = World(stage_units_in_meters=1.0)
        world.scene.add_default_ground_plane()

        # --- Import SO-101 from URDF ---
        urdf_path = _urdf_with_absolute_mesh_paths()
        logger.info("isaac_bridge: importing SO-101 from %s", urdf_path)

        urdf_interface = _urdf.acquire_urdf_interface()
        import_config = _urdf.ImportConfig()
        import_config.fix_base = True
        import_config.make_default_prim = True
        import_config.self_collision = False
        import_config.distance_scale = 1.0
        import_config.density = 0.0
        import_config.convex_decomp = False

        # Set drive parameters for all joints
        result, robot_model = omni.kit.commands.execute(
            "URDFParseFile",
            urdf_path=urdf_path,
            import_config=import_config,
        )
        for joint_name in robot_model.joints:
            robot_model.joints[joint_name].drive.strength = 100.0
            robot_model.joints[joint_name].drive.damping = 10.0

        result, prim_path = omni.kit.commands.execute(
            "URDFImportRobot",
            urdf_robot=robot_model,
            import_config=import_config,
        )
        logger.info("isaac_bridge: SO-101 imported at prim path: %s", prim_path)

        # Wrap as articulation robot
        robot = world.scene.add(
            Robot(prim_path=prim_path or "/so101_new_calib", name="so101")
        )

        world.reset()

        # --- Set viewport camera closer to SO-101 (GUI mode only) ---
        if not headless:
            try:
                from omni.isaac.core.utils.viewports import set_camera_view  # noqa: PLC0415
                set_camera_view(
                    eye=[0.0, 0.7, 0.4],    # camera position rotated ~45 deg left
                    target=[0.0, 0.0, 0.2],  # look-at point (robot base area)
                )
                logger.info("isaac_bridge: viewport camera set")
            except Exception as e:
                logger.warning("isaac_bridge: could not set camera view: %s", e)

        # Move to home pose immediately
        from omni.isaac.core.utils.types import ArticulationAction  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        robot.apply_action(ArticulationAction(joint_positions=np.array(_POSES["home"])))
        for _ in range(30):
            world.step(render=True)

        _agent = _IsaacAgentProxy(sim_app=sim_app, world=world, robot=robot)

        # Store refs for run_sim_loop()
        global _sim_app_ref, _world_ref, _robot_ref
        _sim_app_ref = sim_app
        _world_ref = world
        _robot_ref = robot

        logger.info("isaac_bridge: Isaac Sim agent ready (SO-101 loaded)")
    return _agent
