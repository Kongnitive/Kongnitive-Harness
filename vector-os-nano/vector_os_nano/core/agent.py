"""Vector OS Nano Agent — the main entry point.

This is the ONE class users interact with. It wires together:
- Hardware (arm + gripper)
- Skill registry
- World model
- Task executor

LLM-based natural language planning has been removed. Use execute_skill()
with structured parameters for all robot control.
"""
from __future__ import annotations

import logging
from typing import Any

from vector_os_nano.core.config import load_config
from vector_os_nano.core.executor import TaskExecutor
from vector_os_nano.core.skill import Skill, SkillContext, SkillRegistry
from vector_os_nano.core.types import ExecutionResult
from vector_os_nano.core.world_model import WorldModel

logger = logging.getLogger(__name__)


class Agent:
    """Structured robot arm control via execute_skill().

    Usage::

        from vector_os_nano import Agent
        agent = Agent(arm=arm)
        result = agent.execute_skill("pick", {"object_label": "red cube", "mode": "hold"})

    All hardware arguments are optional — Agent degrades gracefully when
    components are absent (useful for unit testing and partial deployments).

    Args:
        arm: Object implementing ArmProtocol.  None disables motion.
        gripper: Object implementing GripperProtocol.  If None and arm is an
            SO101Arm (has ``_bus``), a SO101Gripper is created automatically.
        perception: Object implementing PerceptionProtocol.  None disables
            vision-based skills.
        skills: Additional Skill instances to register alongside the built-in
            defaults.
        config: Configuration override — a dict, a path to a YAML file, or
            None to use the built-in defaults.
    """

    def __init__(
        self,
        arm: Any = None,
        gripper: Any = None,
        perception: Any = None,
        skills: list[Skill] | None = None,
        config: dict | str | None = None,
        base: Any = None,
        # Kept for backward compat — ignored
        llm: Any = None,
        llm_api_key: str | None = None,
        auto_perception: bool = False,
    ) -> None:
        # ---- Configuration --------------------------------------------------
        if isinstance(config, dict):
            self._config: dict = config
        else:
            self._config = load_config(config)

        # ---- Hardware -------------------------------------------------------
        self._arm = arm
        self._gripper = gripper
        self._base = base

        # Auto-create SO101Gripper when arm shares a serial bus
        if gripper is None and arm is not None and hasattr(arm, "_bus") and arm._bus is not None:
            try:
                from vector_os_nano.hardware.so101.gripper import SO101Gripper
                self._gripper = SO101Gripper(arm._bus)
            except Exception as exc:
                logger.warning("Could not auto-create SO101Gripper: %s", exc)

        # ---- Perception -----------------------------------------------------
        self._perception = perception

        # ---- World model ----------------------------------------------------
        self._world_model = WorldModel()

        # ---- Skill registry -------------------------------------------------
        self._skill_registry = SkillRegistry()

        from vector_os_nano.skills import get_default_skills
        for s in get_default_skills():
            self._skill_registry.register(s)

        if skills:
            for s in skills:
                self._skill_registry.register(s)

        # ---- Executor -------------------------------------------------------
        self._executor = TaskExecutor()

        # ---- Lazy-init state ------------------------------------------------
        self._ik_solver: Any = None
        self._calibration: Any = None

        # ---- Sync world model with hardware ---------------------------------
        self._sync_robot_state()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _sync_robot_state(self) -> None:
        """Sync world model robot state from hardware."""
        if self._arm is not None:
            try:
                joints = self._arm.get_joint_positions()
                ee_pos = (0.0, 0.0, 0.0)
                if self._ik_solver is not None:
                    try:
                        pos, _ = self._ik_solver.fk(joints)
                        ee_pos = tuple(pos)
                    except Exception:
                        pass
                self._world_model.update_robot_state(
                    joint_positions=tuple(joints),
                    ee_position=ee_pos,
                )
            except Exception as exc:
                logger.debug("Could not sync robot state: %s", exc)

        if self._base is not None:
            try:
                pos = self._base.get_position()
                heading = self._base.get_heading()
                self._world_model.update_robot_state(
                    position_xy=(pos[0], pos[1]),
                    heading=heading,
                )
            except Exception as exc:
                logger.debug("Could not sync base state: %s", exc)

    def _refresh_objects(self) -> None:
        """Populate world model with current objects from sim."""
        if self._arm is None:
            return
        if hasattr(self._arm, "get_object_positions"):
            try:
                from vector_os_nano.core.world_model import ObjectState
                objs = self._arm.get_object_positions()
                for name, pos in objs.items():
                    obj = ObjectState(
                        object_id=name,
                        label=name.replace("_", " "),
                        x=float(pos[0]),
                        y=float(pos[1]),
                        z=float(pos[2]),
                        state="on_table",
                        confidence=1.0,
                    )
                    self._world_model.add_object(obj)
            except Exception as exc:
                logger.debug("Could not refresh objects from sim: %s", exc)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def execute_skill(
        self,
        skill_name: str,
        params: dict | None = None,
        on_message: Any = None,
        on_step: Any = None,
        on_step_done: Any = None,
    ) -> ExecutionResult:
        """Execute a skill directly with structured parameters.

        Builds a plan from the skill's auto_steps (if any), otherwise
        executes the single skill. Appends a home step unless the skill
        already returns home internally.
        """
        from vector_os_nano.core.types import TaskPlan, TaskStep

        params = params or {}
        skill_obj = self._skill_registry.get(skill_name)
        if skill_obj is None:
            return ExecutionResult(
                success=False, status="failed",
                failure_reason=f"Unknown skill: {skill_name}",
            )

        object_query = (
            params.get("object_label")
            or params.get("object_id")
            or params.get("query")
            or ""
        )

        raw_auto = getattr(skill_obj, "__skill_auto_steps__", [])
        auto_steps = list(raw_auto) if raw_auto else [skill_name]
        steps = []
        for i, step_skill in enumerate(auto_steps):
            step_params: dict = {}
            if step_skill == skill_name:
                step_params = dict(params)
            elif step_skill == "detect" and object_query:
                step_params = {"query": object_query}
            steps.append(TaskStep(
                step_id=f"s{i+1}",
                skill_name=step_skill,
                parameters=step_params,
                depends_on=[f"s{i}"] if i > 0 else [],
                preconditions=[],
                postconditions=[],
            ))

        # Skip auto-appended home for skills that already return home internally
        skip_home = (
            (skill_name == "pick" and params.get("mode") == "hold")
            or skill_name in ("gripper_close", "gripper_open", "home", "place")
        )
        if not skip_home and (not steps or steps[-1].skill_name != "home"):
            steps.append(TaskStep(
                step_id=f"s{len(steps)+1}",
                skill_name="home",
                parameters={},
                depends_on=[f"s{len(steps)}"],
                preconditions=[],
                postconditions=[],
            ))

        goal = f"{skill_name} {object_query}".strip()
        plan = TaskPlan(goal=goal, steps=steps)

        if on_message:
            step_names = [s.skill_name for s in steps]
            on_message(f"Executing: {' → '.join(step_names)}")

        context = self._build_context()
        result = self._executor.execute(
            plan, self._skill_registry, context,
            on_step=on_step, on_step_done=on_step_done,
        )
        self._sync_robot_state()
        return result

    def register_skill(self, skill: Skill) -> None:
        """Register a custom skill. Overwrites any existing skill with the same name."""
        self._skill_registry.register(skill)

    # -------------------------------------------------------------------------
    # Convenience methods
    # -------------------------------------------------------------------------

    def home(self) -> bool:
        """Move arm to home position."""
        return self.execute_skill("home").success

    def stop(self) -> None:
        """Emergency stop — halts arm motion immediately."""
        if self._arm is not None:
            self._arm.stop()

    def connect(self) -> None:
        """Connect to all hardware peripherals."""
        if self._arm is not None:
            self._arm.connect()
        if self._perception is not None and hasattr(self._perception, "connect"):
            self._perception.connect()

    def disconnect(self) -> None:
        """Disconnect from all hardware peripherals."""
        if self._arm is not None:
            self._arm.disconnect()
        if self._perception is not None and hasattr(self._perception, "disconnect"):
            self._perception.disconnect()

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def world(self) -> WorldModel:
        """The current world model."""
        return self._world_model

    @property
    def skills(self) -> list[str]:
        """Names of all currently registered skills."""
        return self._skill_registry.list_skills()

    # -------------------------------------------------------------------------
    # Context manager
    # -------------------------------------------------------------------------

    def __enter__(self) -> "Agent":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _build_context(self) -> SkillContext:
        """Build a SkillContext from current agent state."""
        if self._ik_solver is None and self._arm is not None:
            try:
                from vector_os_nano.hardware.so101.ik_solver import IKSolver
                self._ik_solver = IKSolver()
                if hasattr(self._arm, "set_ik_solver"):
                    self._arm.set_ik_solver(self._ik_solver)
            except Exception as exc:
                logger.debug("IK solver not available: %s", exc)

        if self._calibration is None:
            try:
                from pathlib import Path
                from vector_os_nano.perception.calibration import Calibration
                cal_file: str = self._config.get("calibration", {}).get("file", "")
                if cal_file:
                    cal_path = Path(cal_file)
                    if not cal_path.is_absolute():
                        candidate = Path.home() / "Desktop" / "vector_os_nano" / cal_path
                        if not candidate.exists():
                            candidate = Path.cwd() / cal_path
                        if candidate.exists():
                            cal_path = candidate
                    self._calibration = Calibration.load(str(cal_path))
                else:
                    self._calibration = Calibration()
            except Exception as exc:
                logger.debug("Calibration not available: %s", exc)

        services: dict = {}
        if hasattr(self, "_skill_registry"):
            services["skill_registry"] = self._skill_registry

        return SkillContext(
            arms={"default": self._arm} if self._arm else {},
            grippers={"default": self._gripper} if self._gripper else {},
            bases={"default": self._base} if self._base else {},
            perception_sources=(
                {"default": self._perception} if self._perception else {}
            ),
            services=services,
            world_model=self._world_model,
            calibration=self._calibration,
            config=self._config,
        )
