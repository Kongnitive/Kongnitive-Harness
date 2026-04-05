"""MuJoCo-based combined Go2 quadruped + SO-101 arm simulation.

The arm is mounted on Go2's back. A single MuJoCo physics instance drives
both subsystems. Implements ArmProtocol + BaseProtocol so one Agent can
hold arm skills and Go2 skills simultaneously.

Lifecycle: MuJoCoGo2WithArm(gui=False) -> connect() -> ... -> disconnect()
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy MuJoCo import
# ---------------------------------------------------------------------------

_mujoco: Any = None


def _get_mujoco() -> Any:
    global _mujoco
    if _mujoco is None:
        import mujoco
        _mujoco = mujoco
    return _mujoco


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SIM_DIR: Path = Path(__file__).parent
_MJCF_DIR: Path = _SIM_DIR / "mjcf" / "go2"
_ROOM_XML: Path = _SIM_DIR / "go2_room.xml"
_ARM_XML: Path = _SIM_DIR / "so101_mujoco.xml"
_ARM_MESH_DIR: Path = _SIM_DIR.parent / "urdf" / "meshes"

# ---------------------------------------------------------------------------
# Arm mount offset on Go2's back (relative to base_link)
# ---------------------------------------------------------------------------

_ARM_MOUNT_POS = "0.1 0 0.08"  # 10cm forward, 8cm up

# ---------------------------------------------------------------------------
# Constants — reused from mujoco_go2.py
# ---------------------------------------------------------------------------

_STAND_JOINTS: list[float] = [0.0, 0.9, -1.8] * 4
_SIT_JOINTS: list[float] = [0.0, 1.5, -2.5] * 4
_LIE_DOWN_JOINTS: list[float] = [0.0, 2.0, -2.7] * 4

_KP: float = 120.0
_KD: float = 3.5
_TAU_HIP: float = 23.7 * 0.9
_TAU_KNEE: float = 45.43 * 0.9
_TAU_LIMITS: np.ndarray = np.array([_TAU_HIP, _TAU_HIP, _TAU_KNEE] * 4, dtype=np.float64)

_SIM_HZ: int = 1000
_SIM_DT: float = 1.0 / _SIM_HZ
_CTRL_HZ: int = 200
_CTRL_DECIM: int = _SIM_HZ // _CTRL_HZ
_VIEWER_SYNC_EVERY: int = 8

_GAIT_FREQ: float = 2.0
_THIGH_AMP: float = 0.25
_CALF_AMP: float = 0.25
_HIP_AMP: float = 0.10
_CALF_PHASE: float = 0.0
_TROT_PHASES: tuple[float, ...] = (0.0, math.pi, math.pi, 0.0)

_VX_MAX: float = 0.8
_VY_MAX: float = 0.4
_VYAW_MAX: float = 4.0

_LIDAR_UPDATE_INTERVAL: int = 200

# Arm home joint positions (all zeros = straight up)
_ARM_HOME_JOINTS: list[float] = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
_ARM_JOINT_NAMES: list[str] = [
    "shoulder_pan", "shoulder_lift", "elbow_flex",
    "wrist_flex", "wrist_roll", "jaw_visual_joint",
]
_ARM_ACTUATOR_NAMES: list[str] = [
    "act_shoulder_pan", "act_shoulder_lift", "act_elbow_flex",
    "act_wrist_flex", "act_wrist_roll", "act_jaw_visual",
]

# Objects placed on kitchen island (surface z ≈ 0.915)
_OBJECT_SURFACE_Z = 0.94
_OBJECTS_ON_ISLAND: list[dict] = [
    {"name": "banana",      "pos": "17.2 2.6 {z}", "rgba": "1.0 0.9 0.2 1",  "mesh": "banana_mesh",      "mass": "0.020"},
    {"name": "mug",         "pos": "16.8 2.9 {z}", "rgba": "0.85 0.15 0.15 1","mesh": "mug_mesh",         "mass": "0.030"},
    {"name": "bottle",      "pos": "17.4 3.0 {z}", "rgba": "0.2 0.4 0.9 1",  "mesh": "bottle_mesh",      "mass": "0.025"},
    {"name": "screwdriver", "pos": "16.6 2.7 {z}", "rgba": "0.1 0.7 0.2 1",  "mesh": "screwdriver_mesh", "mass": "0.015"},
    {"name": "duck",        "pos": "17.0 2.5 {z}", "rgba": "1.0 0.6 0.1 1",  "mesh": "duck_mesh",        "mass": "0.020"},
    {"name": "lego",        "pos": "17.3 2.7 {z}", "rgba": "0.95 0.2 0.2 1", "mesh": "lego_mesh",        "mass": "0.008"},
]


# ---------------------------------------------------------------------------
# Scene XML builder
# ---------------------------------------------------------------------------

def _build_go2_with_arm_scene_xml() -> Path:
    """Build merged Go2 + arm room scene via runtime XML assembly.

    Strategy:
    1. Read go2.xml, find the closing </body> of base_link, inject arm body tree
    2. Read go2_room.xml template, replace <include> with the modified go2 XML
    3. Append arm mesh assets, arm actuators, weld constraints, and objects
    """
    go2_xml_path = _MJCF_DIR / "go2.xml"
    go2_assets_dir = _MJCF_DIR / "assets"
    arm_mesh_dir_str = str(_ARM_MESH_DIR).replace("\\", "/")

    # --- Step 1: Build arm body subtree (to nest inside Go2 base_link) ---
    arm_body = _build_arm_body_xml(arm_mesh_dir_str)

    # --- Step 2: Read go2.xml and inject arm into base_link ---
    go2_raw = go2_xml_path.read_text(encoding="utf-8")
    go2_modified = _inject_arm_into_go2(go2_raw, arm_body)

    # --- Step 3: Read room template, inline the modified Go2 ---
    room_raw = _ROOM_XML.read_text(encoding="utf-8")

    # The room template has:
    #   <compiler ... meshdir="GO2_ASSETS_DIR" .../>
    #   <include file="GO2_MODEL_PATH"/>
    # We replace meshdir and remove the <include>, inlining go2 content instead.
    room_xml = room_raw.replace("GO2_ASSETS_DIR", str(go2_assets_dir).replace("\\", "/"))

    # Remove the <include file="GO2_MODEL_PATH"/> line
    room_xml = re.sub(r'\s*<include\s+file="GO2_MODEL_PATH"\s*/>', "", room_xml)

    # --- Step 4: Inject go2 content (defaults, assets, worldbody, actuators, sensors) ---
    # Extract sections from modified go2 XML
    go2_defaults = _extract_section(go2_modified, "default")
    go2_assets = _extract_section(go2_modified, "asset")
    go2_worldbody_inner = _extract_worldbody_inner(go2_modified)
    go2_actuators = _extract_section(go2_modified, "actuator")
    go2_sensors = _extract_section(go2_modified, "sensor")
    go2_keyframe = _extract_section(go2_modified, "keyframe")

    # Build arm-specific additions
    arm_assets_xml = _build_arm_assets_xml(arm_mesh_dir_str)
    arm_actuators_xml = _build_arm_actuators_xml()
    arm_weld_xml = _build_weld_constraints_xml()
    objects_xml = _build_objects_xml()

    # Insert go2 defaults after the room's <option> line
    room_xml = room_xml.replace(
        '<option cone="elliptic" impratio="100"/>',
        '<option cone="elliptic" impratio="100"/>\n\n' + go2_defaults,
    )

    # Insert go2 assets + arm assets into the room's <asset> block (before closing </asset>)
    room_xml = room_xml.replace(
        "</asset>",
        go2_assets_inner(go2_assets) + "\n" + arm_assets_xml + "\n  </asset>",
    )

    # Insert go2 worldbody (base_link + legs + arm) + objects into room's <worldbody>
    # Find the last </body> before </worldbody> and insert after it
    room_xml = room_xml.replace(
        "</worldbody>",
        "\n    <!-- Go2 + Arm -->\n" + go2_worldbody_inner + "\n\n"
        + "    <!-- Graspable objects on kitchen island -->\n" + objects_xml + "\n\n"
        + "  </worldbody>",
    )

    # Insert actuators, sensors, equality, keyframe before closing </mujoco>
    room_xml = room_xml.replace(
        "</mujoco>",
        "\n" + go2_actuators + "\n\n" + arm_actuators_xml + "\n\n"
        + go2_sensors + "\n\n" + arm_weld_xml + "\n\n"
        + go2_keyframe + "\n\n</mujoco>",
    )

    out = _MJCF_DIR / "scene_go2_with_arm.xml"
    out.write_text(room_xml, encoding="utf-8")
    logger.info("Built merged Go2+Arm scene: %s", out)
    return out


def go2_assets_inner(go2_assets_block: str) -> str:
    """Extract inner content of go2's <asset>...</asset> block."""
    m = re.search(r"<asset[^>]*>(.*?)</asset>", go2_assets_block, re.DOTALL)
    return m.group(1) if m else ""


def _build_arm_body_xml(arm_mesh_dir: str) -> str:
    """Build the arm body subtree to be nested inside Go2's base_link.

    This is the arm's kinematic chain from base_link down, wrapped in a
    container body with the mount offset.
    """
    arm_raw = _ARM_XML.read_text(encoding="utf-8")

    # Extract the arm body tree starting from <body name="base_link" ...>
    # We need everything from base_link opening to its closing </body>
    arm_body = _extract_body_tree(arm_raw, "base_link")
    if not arm_body:
        raise RuntimeError("Could not extract arm base_link body from so101_mujoco.xml")

    # Rename arm's base_link to arm_base_link to avoid collision with Go2's base_link
    arm_body = arm_body.replace('name="base_link"', 'name="arm_base_link"')

    # Remove the original pos="0 0 0.02" (table mount) — we'll set our own mount pos
    arm_body = re.sub(r'(<body\s+name="arm_base_link")\s+pos="[^"]*"', r'\1', arm_body)

    # Wrap in a mount body with the offset position
    return f'      <body name="arm_mount" pos="{_ARM_MOUNT_POS}">\n{_indent(arm_body, 8)}\n      </body>'


def _inject_arm_into_go2(go2_xml: str, arm_body: str) -> str:
    """Inject arm body tree into Go2's base_link, just before the first leg body."""
    # Find the first child body inside base_link (FL_hip)
    # Insert arm body just before it
    marker = '<body name="FL_hip"'
    idx = go2_xml.find(marker)
    if idx < 0:
        raise RuntimeError("Could not find FL_hip in go2.xml")

    return go2_xml[:idx] + arm_body + "\n      " + go2_xml[idx:]


def _build_arm_assets_xml(arm_mesh_dir: str) -> str:
    """Build <mesh> declarations for arm STL files with absolute paths."""
    arm_meshes = [
        "base_motor_holder_so101_v1", "base_so101_v2", "sts3215_03a_v1",
        "waveshare_mounting_plate_so101_v2", "motor_holder_so101_base_v1",
        "rotation_pitch_so101_v1", "upper_arm_so101_v1", "under_arm_so101_v1",
        "motor_holder_so101_wrist_v1", "sts3215_03a_no_horn_v1",
        "wrist_roll_pitch_so101_v2", "wrist_roll_follower_so101_v1",
        "moving_jaw_so101_v1",
    ]
    object_meshes = [
        ("banana_mesh", "banana.stl", None),
        ("mug_mesh", "mug.stl", None),
        ("bottle_mesh", "bottle.stl", None),
        ("screwdriver_mesh", "screwdriver.stl", None),
        ("duck_mesh", "duck.stl", "0.8 0.8 0.8"),
        ("lego_mesh", "lego.stl", None),
    ]

    lines = ["    <!-- SO-101 arm meshes -->"]
    for name in arm_meshes:
        path = f"{arm_mesh_dir}/{name}.stl"
        lines.append(f'    <mesh name="{name}" file="{path}"/>')

    lines.append("    <!-- Object meshes -->")
    for mesh_name, filename, scale in object_meshes:
        path = f"{arm_mesh_dir}/{filename}"
        scale_attr = f' scale="{scale}"' if scale else ""
        lines.append(f'    <mesh name="{mesh_name}" file="{path}"{scale_attr}/>')

    return "\n".join(lines)


def _build_arm_actuators_xml() -> str:
    """Build arm position-controlled actuators block."""
    return """  <actuator>
    <!-- SO-101 arm actuators (position-controlled) -->
    <position name="act_shoulder_pan"  joint="shoulder_pan"  kp="100" ctrlrange="-1.92 1.92"/>
    <position name="act_shoulder_lift" joint="shoulder_lift" kp="100" ctrlrange="-1.75 1.75"/>
    <position name="act_elbow_flex"    joint="elbow_flex"    kp="80"  ctrlrange="-1.69 1.69"/>
    <position name="act_wrist_flex"    joint="wrist_flex"    kp="60"  ctrlrange="-1.66 1.66"/>
    <position name="act_wrist_roll"    joint="wrist_roll"    kp="60"  ctrlrange="-2.74 2.84"/>
    <position name="act_jaw_visual"   joint="jaw_visual_joint" kp="20" ctrlrange="-0.175 1.75"/>
  </actuator>"""


def _build_weld_constraints_xml() -> str:
    """Build weld constraints for grasping objects."""
    obj_names = [o["name"] for o in _OBJECTS_ON_ISLAND]
    lines = ["  <equality>"]
    for name in obj_names:
        lines.append(f'    <weld body1="gripper_link" body2="{name}" active="false"/>')
    lines.append("  </equality>")
    return "\n".join(lines)


def _build_objects_xml() -> str:
    """Build free-body objects placed on the kitchen island."""
    lines = []
    for obj in _OBJECTS_ON_ISLAND:
        name = obj["name"]
        pos = obj["pos"].format(z=_OBJECT_SURFACE_Z)
        rgba = obj["rgba"]
        mesh = obj["mesh"]
        mass = obj["mass"]

        if name == "lego":
            # Lego uses box + cylinder studs (same as so101_mujoco.xml)
            lines.append(f'    <body name="{name}" pos="{pos}">')
            lines.append(f'      <freejoint name="{name}_free"/>')
            lines.append(f'      <geom name="lego_base" type="box" size="0.016 0.008 0.006"')
            lines.append(f'            rgba="{rgba}" mass="{mass}" condim="4"/>')
            for sx, sy in [(-0.008, -0.004), (0.008, -0.004), (-0.008, 0.004), (0.008, 0.004)]:
                lines.append(f'      <geom type="cylinder" size="0.003 0.002" pos="{sx} {sy} 0.008"')
                lines.append(f'            rgba="{rgba}" mass="0.0005" condim="4"/>')
            lines.append(f'    </body>')
        else:
            lines.append(f'    <body name="{name}" pos="{pos}">')
            lines.append(f'      <freejoint name="{name}_free"/>')
            lines.append(f'      <geom name="{name}_geom" type="mesh" mesh="{mesh}"')
            lines.append(f'            rgba="{rgba}" mass="{mass}" condim="4"/>')
            lines.append(f'    </body>')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# XML parsing helpers
# ---------------------------------------------------------------------------

def _extract_section(xml: str, tag: str) -> str:
    """Extract a top-level <tag>...</tag> section from XML."""
    pattern = rf"(<{tag}[\s>].*?</{tag}>)"
    m = re.search(pattern, xml, re.DOTALL)
    return m.group(1) if m else ""


def _extract_worldbody_inner(xml: str) -> str:
    """Extract inner content of <worldbody>...</worldbody>."""
    m = re.search(r"<worldbody[^>]*>(.*?)</worldbody>", xml, re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_body_tree(xml: str, body_name: str) -> str:
    """Extract a complete <body name="...">...</body> subtree using brace counting."""
    pattern = rf'<body\s+name="{body_name}"'
    m = re.search(pattern, xml)
    if not m:
        return ""

    start = m.start()
    depth = 0
    i = start
    while i < len(xml):
        if xml[i:i+6] == "<body " or xml[i:i+6] == "<body>":
            depth += 1
        elif xml[i:i+7] == "</body>":
            depth -= 1
            if depth == 0:
                return xml[start:i+7]
        i += 1
    return ""


def _indent(text: str, spaces: int) -> str:
    """Indent every line of text by given number of spaces."""
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else line for line in text.split("\n"))


# ---------------------------------------------------------------------------
# Sinusoidal gait (copied from mujoco_go2.py to avoid circular import)
# ---------------------------------------------------------------------------

def _compute_gait_targets(t: float, vx: float, vy: float, vyaw: float) -> np.ndarray:
    """Compute 12 target joint positions for sinusoidal trotting gait."""
    q_target = np.array(_STAND_JOINTS, dtype=np.float64)
    omega = 2.0 * math.pi * _GAIT_FREQ
    fwd_amp = float(np.clip(vx / 0.5, -1.0, 1.0)) if abs(vx) > 0.01 else 0.0
    turn_amp = float(np.clip(vyaw / 1.0, -1.0, 1.0)) if abs(vyaw) > 0.01 else 0.0

    for leg_idx in range(4):
        base = leg_idx * 3
        phase = omega * t + _TROT_PHASES[leg_idx]
        is_left = leg_idx in (0, 2)
        leg_turn = -turn_amp if is_left else turn_amp
        total_amp = float(np.clip(fwd_amp + leg_turn, -1.5, 1.5))

        if abs(vy) > 0.01:
            q_target[base + 0] += _HIP_AMP * (vy / _VY_MAX) * math.sin(phase)

        if total_amp >= 0:
            leg_calf_phase = _CALF_PHASE
            amp = total_amp
        else:
            leg_calf_phase = _CALF_PHASE + math.pi
            amp = -total_amp

        q_target[base + 1] += _THIGH_AMP * amp * math.sin(phase)
        q_target[base + 2] += _CALF_AMP * amp * math.sin(phase + leg_calf_phase)

    return q_target


# ---------------------------------------------------------------------------
# _Go2Model (lightweight wrapper, same as mujoco_go2.py)
# ---------------------------------------------------------------------------

class _Go2Model:
    __slots__ = ("model", "data", "base_bid", "_act_ids", "viewer")

    def __init__(self, model: Any, data: Any) -> None:
        mj = _get_mujoco()
        self.model = model
        self.data = data
        self.viewer = None
        self.base_bid: int = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, "base_link")
        self._act_ids: list[int] = []
        for leg in ("FL", "FR", "RL", "RR"):
            for joint in ("hip", "thigh", "calf"):
                self._act_ids.append(
                    mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, f"{leg}_{joint}")
                )

    def set_joint_torque(self, torque: np.ndarray) -> None:
        for i, aid in enumerate(self._act_ids):
            self.data.ctrl[aid] = float(torque[i])


# ---------------------------------------------------------------------------
# MuJoCoGo2WithArm — dual ArmProtocol + BaseProtocol
# ---------------------------------------------------------------------------

class MuJoCoGo2WithArm:
    """Go2 quadruped with SO-101 arm mounted on its back.

    Single MuJoCo physics instance. Exposes both ArmProtocol (for arm skills)
    and BaseProtocol (for Go2 locomotion skills).

    Args:
        gui: Open interactive viewer on connect().
        room: Use indoor room scene (always True for combined mode).
    """

    def __init__(self, gui: bool = False, room: bool = True) -> None:
        self._gui: bool = gui
        self._room: bool = room
        self._mj: _Go2Model | None = None
        self._viewer: Any = None
        self._connected: bool = False

        # Arm joint/actuator IDs (cached on connect)
        self._arm_joint_ids: list[int] = []
        self._arm_act_ids: list[int] = []

        # Go2 qpos layout: [0:3]=pos, [3:7]=quat, [7:19]=leg joints
        # Arm joints come after Go2's 12 leg joints in qpos
        self._arm_qpos_start: int = 0  # set on connect
        self._arm_qvel_start: int = 0

        # Background physics thread
        self._cmd_vel: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._cmd_lock: threading.Lock = threading.Lock()
        self._physics_thread: threading.Thread | None = None
        self._running: bool = False
        self._last_odom: Any = None
        self._last_scan: Any = None
        self._last_pointcloud: list = []

        # Object tracking for perception
        self._object_names: list[str] = [o["name"] for o in _OBJECTS_ON_ISLAND]

    # ------------------------------------------------------------------
    # Capability properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "mujoco_go2_with_arm"

    @property
    def supports_holonomic(self) -> bool:
        return True

    @property
    def supports_lidar(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Load merged scene and start physics thread."""
        mj = _get_mujoco()

        scene_path = _build_go2_with_arm_scene_xml()
        model = mj.MjModel.from_xml_path(str(scene_path))
        data = mj.MjData(model)
        self._mj = _Go2Model(model, data)

        # Cache arm joint and actuator IDs
        self._arm_joint_ids = []
        self._arm_act_ids = []
        for jname in _ARM_JOINT_NAMES:
            jid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, jname)
            if jid < 0:
                raise RuntimeError(f"Arm joint '{jname}' not found in merged scene")
            self._arm_joint_ids.append(jid)

        for aname in _ARM_ACTUATOR_NAMES:
            aid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, aname)
            if aid < 0:
                raise RuntimeError(f"Arm actuator '{aname}' not found in merged scene")
            self._arm_act_ids.append(aid)

        # Determine arm qpos/qvel offsets
        # Go2 freejoint: 7 qpos (3 pos + 4 quat) + 12 leg joints = qpos[0:19]
        # Arm joints follow after Go2's joints
        first_arm_jid = self._arm_joint_ids[0]
        self._arm_qpos_start = model.jnt_qposadr[first_arm_jid]
        self._arm_qvel_start = model.jnt_dofadr[first_arm_jid]

        # Place Go2 in the kitchen area (near the island with objects)
        data.qpos[0] = 16.0   # x — in front of kitchen island
        data.qpos[1] = 1.8    # y — facing the island
        data.qpos[2] = 0.35   # z — standing height
        # Set standing leg joints
        data.qpos[7:19] = _STAND_JOINTS
        # Set arm to home position
        for i, jid in enumerate(self._arm_joint_ids):
            data.qpos[model.jnt_qposadr[jid]] = _ARM_HOME_JOINTS[i]

        model.opt.timestep = _SIM_DT
        mj.mj_forward(model, data)

        if self._gui:
            try:
                import mujoco.viewer
                self._viewer = mujoco.viewer.launch_passive(
                    model, data, show_left_ui=False, show_right_ui=False,
                )
                if self._viewer is not None:
                    self._viewer.cam.type = mj.mjtCamera.mjCAMERA_FREE
                    self._viewer.cam.lookat[:] = [16.0, 3.0, 0.5]
                    self._viewer.cam.distance = 5.0
                    self._viewer.cam.elevation = -35
                    self._viewer.cam.azimuth = -90
            except Exception as exc:
                logger.warning("Viewer failed to launch: %s", exc)
                self._viewer = None

        self._connected = True
        logger.info("MuJoCoGo2WithArm connected (gui=%s)", self._gui)

        # Start physics thread
        self._running = True
        self._physics_thread = threading.Thread(
            target=self._physics_loop, daemon=True, name="go2_with_arm_physics",
        )
        self._physics_thread.start()

    def disconnect(self) -> None:
        """Stop physics and release resources."""
        self._running = False
        if self._physics_thread is not None:
            self._physics_thread.join(timeout=2.0)
            self._physics_thread = None
        if self._viewer is not None:
            try:
                self._viewer.close()
            except Exception:
                pass
            self._viewer = None
        self._mj = None
        self._connected = False

    def _require_connection(self) -> None:
        if not self._connected:
            raise RuntimeError("MuJoCoGo2WithArm: not connected")

    # ------------------------------------------------------------------
    # Physics thread
    # ------------------------------------------------------------------

    def _pause_physics(self) -> None:
        self._running = False
        if self._physics_thread is not None:
            self._physics_thread.join(timeout=2.0)
            self._physics_thread = None

    def _resume_physics(self) -> None:
        self._running = True
        self._physics_thread = threading.Thread(
            target=self._physics_loop, daemon=True, name="go2_with_arm_physics",
        )
        self._physics_thread.start()

    def _physics_loop(self) -> None:
        """1 kHz physics loop: Go2 gait + arm position control."""
        mj = _get_mujoco()
        tau_hold: np.ndarray = np.zeros(12, dtype=float)
        sim_step: int = 0
        scan_counter: int = 0

        while self._running:
            loop_start = time.perf_counter()

            with self._cmd_lock:
                vx, vy, vyaw = self._cmd_vel

            time_now = float(self._mj.data.time)
            is_moving = (vx != 0.0 or vy != 0.0 or vyaw != 0.0)

            if sim_step % _CTRL_DECIM == 0:
                q_cur = np.array(self._mj.data.qpos[7:19], dtype=np.float64)
                dq_cur = np.array(self._mj.data.qvel[6:18], dtype=np.float64)

                if is_moving:
                    q_target = _compute_gait_targets(time_now, vx, vy, vyaw)
                else:
                    q_target = np.array(_STAND_JOINTS, dtype=np.float64)

                tau = _KP * (q_target - q_cur) - _KD * dq_cur
                tau = np.clip(tau, -_TAU_LIMITS, _TAU_LIMITS)
                tau_hold = tau.copy()

            # Arm actuators are position-controlled (MuJoCo handles PD internally)
            # — no explicit torque computation needed; ctrl values set by set_joint_positions()

            mj.mj_step1(self._mj.model, self._mj.data)
            self._mj.set_joint_torque(tau_hold)
            mj.mj_step2(self._mj.model, self._mj.data)

            self._update_odometry()

            scan_counter += 1
            if scan_counter >= _LIDAR_UPDATE_INTERVAL:
                self._update_lidar()
                scan_counter = 0

            if self._viewer is not None and sim_step % _VIEWER_SYNC_EVERY == 0:
                self._viewer.sync()

            sim_step += 1

            elapsed = time.perf_counter() - loop_start
            sleep_time = _SIM_DT - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    # ------------------------------------------------------------------
    # ArmProtocol — joint control
    # ------------------------------------------------------------------

    def get_joint_positions(self) -> list[float]:
        """Return arm joint positions (6 DOF)."""
        self._require_connection()
        model = self._mj.model
        return [float(self._mj.data.qpos[model.jnt_qposadr[jid]])
                for jid in self._arm_joint_ids]

    def set_joint_positions(
        self,
        positions: list[float],
        duration: float | None = None,
    ) -> None:
        """Set arm joint target positions via position actuators."""
        self._require_connection()
        for i, aid in enumerate(self._arm_act_ids):
            if i < len(positions):
                self._mj.data.ctrl[aid] = float(positions[i])

    def get_object_positions(self) -> dict[str, tuple[float, float, float]]:
        """Return world positions of all graspable objects (ground truth)."""
        self._require_connection()
        mj = _get_mujoco()
        result = {}
        for name in self._object_names:
            bid = mj.mj_name2id(self._mj.model, mj.mjtObj.mjOBJ_BODY, name)
            if bid >= 0:
                pos = self._mj.data.xpos[bid]
                result[name] = (float(pos[0]), float(pos[1]), float(pos[2]))
        return result

    def get_ee_position(self) -> tuple[float, float, float]:
        """Return end-effector position in world frame."""
        self._require_connection()
        mj = _get_mujoco()
        site_id = mj.mj_name2id(self._mj.model, mj.mjtObj.mjOBJ_SITE, "ee_site")
        if site_id >= 0:
            pos = self._mj.data.site_xpos[site_id]
            return (float(pos[0]), float(pos[1]), float(pos[2]))
        return (0.0, 0.0, 0.0)

    def stop(self) -> None:
        """Emergency stop — zero Go2 velocity and hold arm position."""
        self._require_connection()
        with self._cmd_lock:
            self._cmd_vel = (0.0, 0.0, 0.0)

    # ------------------------------------------------------------------
    # BaseProtocol — locomotion
    # ------------------------------------------------------------------

    def set_velocity(self, vx: float, vy: float, vyaw: float) -> None:
        self._require_connection()
        with self._cmd_lock:
            self._cmd_vel = (
                float(np.clip(vx, -_VX_MAX, _VX_MAX)),
                float(np.clip(vy, -_VY_MAX, _VY_MAX)),
                float(np.clip(vyaw, -_VYAW_MAX, _VYAW_MAX)),
            )

    def get_position(self) -> list[float]:
        self._require_connection()
        return list(self._mj.data.qpos[0:3].astype(float))

    def get_velocity(self) -> list[float]:
        self._require_connection()
        return list(self._mj.data.qvel[0:3].astype(float))

    def get_heading(self) -> float:
        self._require_connection()
        w, x, y, z = self._mj.data.qpos[3:7]
        return float(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))

    def get_odometry(self) -> Any:
        self._require_connection()
        if self._last_odom is None:
            self._update_odometry()
        return self._last_odom

    def get_lidar_scan(self) -> Any:
        self._require_connection()
        if self._last_scan is None:
            self._update_lidar()
        return self._last_scan

    def get_3d_pointcloud(self) -> list[tuple[float, float, float, float]]:
        self._require_connection()
        if not self._last_pointcloud:
            self._update_lidar()
        return self._last_pointcloud

    def get_camera_frame(self, width: int = 320, height: int = 240) -> "np.ndarray":
        """Render first-person RGB frame from Go2 head camera."""
        self._require_connection()
        mj = _get_mujoco()
        if not hasattr(self, "_cam_renderer"):
            self._cam_renderer = mj.Renderer(self._mj.model, height, width)
            self._cam_obj = mj.MjvCamera()
            self._cam_obj.type = mj.mjtCamera.mjCAMERA_FREE

        heading = self.get_heading()
        cos_h = math.cos(heading)
        sin_h = math.sin(heading)
        odom = self.get_odometry()

        cam_x = odom.x + cos_h * 0.3
        cam_y = odom.y + sin_h * 0.3
        cam_z = odom.z + 0.15

        self._cam_obj.lookat[:] = [cam_x + cos_h * 2.0, cam_y + sin_h * 2.0, cam_z + 0.1]
        self._cam_obj.distance = 2.0
        self._cam_obj.azimuth = math.degrees(heading) + 180
        self._cam_obj.elevation = -5

        self._cam_renderer.update_scene(self._mj.data, camera=self._cam_obj)
        return self._cam_renderer.render().copy()

    # ------------------------------------------------------------------
    # Posture commands (Go2)
    # ------------------------------------------------------------------

    def stand(self, duration: float = 2.0) -> bool:
        self._require_connection()
        self._pd_interpolate(np.array(_STAND_JOINTS, dtype=np.float64), duration)
        return True

    def sit(self, duration: float = 2.0) -> bool:
        self._require_connection()
        self._pd_interpolate(np.array(_SIT_JOINTS, dtype=np.float64), duration)
        return True

    def lie_down(self, duration: float = 2.0) -> bool:
        self._require_connection()
        self._pd_interpolate(np.array(_LIE_DOWN_JOINTS, dtype=np.float64), duration)
        return True

    def walk(self, vx: float = 0.0, vy: float = 0.0, vyaw: float = 0.0, duration: float = 2.0) -> bool:
        self._require_connection()
        self.set_velocity(vx, vy, vyaw)
        time.sleep(duration)
        self.set_velocity(0.0, 0.0, 0.0)
        time.sleep(0.2)
        pos = self.get_position()
        return bool(pos[2] > 0.15)

    # ------------------------------------------------------------------
    # PD interpolation (synchronous, physics thread paused)
    # ------------------------------------------------------------------

    def _pd_interpolate(self, target_joints: np.ndarray, duration: float = 2.0) -> None:
        was_running = self._running
        if was_running:
            self._pause_physics()

        mj = _get_mujoco()
        model = self._mj.model
        data = self._mj.data
        dt = model.opt.timestep
        total_steps = max(1, int(duration / dt))
        q_start = np.array(data.qpos[7:19], dtype=np.float64)
        q_target = np.asarray(target_joints, dtype=np.float64)
        hold_steps = max(0, int(0.5 / dt))

        for step in range(total_steps + hold_steps):
            if step < total_steps:
                t_norm = (step + 1) * dt / (duration / 3.0)
                phase = float(np.tanh(t_norm))
                q_des = q_start + phase * (q_target - q_start)
            else:
                q_des = q_target

            q_cur = np.array(data.qpos[7:19], dtype=np.float64)
            dq_cur = np.array(data.qvel[6:18], dtype=np.float64)
            tau = _KP * (q_des - q_cur) - _KD * dq_cur
            tau = np.clip(tau, -_TAU_LIMITS, _TAU_LIMITS)
            self._mj.set_joint_torque(tau)
            mj.mj_step(model, data)

            if self._viewer is not None and step % _VIEWER_SYNC_EVERY == 0:
                self._viewer.sync()

        if was_running:
            self._resume_physics()

    # ------------------------------------------------------------------
    # Sensor helpers
    # ------------------------------------------------------------------

    def _update_odometry(self) -> None:
        from vector_os_nano.core.types import Odometry
        q = self._mj.data.qpos
        v = self._mj.data.qvel
        self._last_odom = Odometry(
            timestamp=float(self._mj.data.time),
            x=float(q[0]), y=float(q[1]), z=float(q[2]),
            qx=float(q[4]), qy=float(q[5]), qz=float(q[6]), qw=float(q[3]),
            vx=float(v[0]), vy=float(v[1]), vz=float(v[2]), vyaw=float(v[5]),
        )

    def _update_lidar(self) -> None:
        """Simplified lidar — same as MuJoCoGo2 but with fewer rays for performance."""
        from vector_os_nano.core.types import LaserScan
        mj = _get_mujoco()

        pos = self._mj.data.qpos[0:3].copy().astype(np.float64)
        heading = self.get_heading()
        cos_h = math.cos(heading)
        sin_h = math.sin(heading)

        pos_lidar = np.array([
            float(pos[0]) + cos_h * 0.2,
            float(pos[1]) + sin_h * 0.2,
            float(pos[2]) + 0.1,
        ], dtype=np.float64)

        robot_body_id = self._mj.base_bid
        n_azimuth = 360
        azimuth_step = 360.0 / n_azimuth
        ranges: list[float] = []

        for i in range(n_azimuth):
            azimuth = heading + math.radians(i * azimuth_step - 180)
            direction = np.array([math.cos(azimuth), math.sin(azimuth), 0.0], dtype=np.float64)
            geom_id = np.zeros(1, dtype=np.int32)
            dist = mj.mj_ray(
                self._mj.model, self._mj.data,
                pos_lidar, direction, None, 1, robot_body_id, geom_id,
            )
            ranges.append(float(dist) if dist > 0 else float("inf"))

        self._last_scan = LaserScan(
            timestamp=float(self._mj.data.time),
            angle_min=-math.pi, angle_max=math.pi,
            angle_increment=math.radians(azimuth_step),
            range_min=0.1, range_max=12.0,
            ranges=tuple(ranges),
        )
        self._last_pointcloud = []  # simplified — 2D only for now
