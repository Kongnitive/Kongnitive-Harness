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
_CALF_PHASE: float = math.pi
_TROT_PHASES: tuple[float, ...] = (0.0, math.pi, math.pi, 0.0)

_VX_MAX: float = 0.8
_VY_MAX: float = 0.4
_VYAW_MAX: float = 4.0

_LIDAR_UPDATE_INTERVAL: int = 200

# Arm home joint positions (5 controllable joints; jaw is visual only)
_ARM_HOME_JOINTS: list[float] = [0.0, 0.0, 0.0, 0.0, 0.0]
_GO2_LEG_JOINT_NAMES: list[str] = [
    "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint",
    "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
    "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
    "RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
]
_ARM_JOINT_NAMES: list[str] = [
    "shoulder_pan", "shoulder_lift", "elbow_flex",
    "wrist_flex", "wrist_roll",
]
_ARM_ACTUATOR_NAMES: list[str] = [
    "act_shoulder_pan", "act_shoulder_lift", "act_elbow_flex",
    "act_wrist_flex", "act_wrist_roll",
]
_JAW_VISUAL_JOINT_NAME: str = "jaw_visual_joint"
_JAW_VISUAL_ACTUATOR_NAME: str = "act_jaw_visual"
_EE_SITE_NAME: str = "ee_site"

# IK defaults copied from MuJoCoArm for skill compatibility.
_IK_MAX_ITER: int = 100
_IK_TOL: float = 1e-3
_IK_STEP_SIZE: float = 0.5
_IK_DAMPING: float = 1e-4

# Objects scattered on the ground near Go2 start position.
# Positions are in world frame; z=0.02 keeps objects just above the floor.
_OBJECT_SURFACE_Z = 0.02
_OBJECTS_ON_ISLAND: list[dict] = [
    {"name": "banana",      "pos": f"1.2  0.3 {_OBJECT_SURFACE_Z}", "rgba": "1.0 0.9 0.2 1",   "mesh": "banana_mesh",      "mass": "0.020"},
    {"name": "mug",         "pos": f"1.0 -0.4 {_OBJECT_SURFACE_Z}", "rgba": "0.85 0.15 0.15 1", "mesh": "mug_mesh",         "mass": "0.030"},
    {"name": "bottle",      "pos": f"1.5  0.0 {_OBJECT_SURFACE_Z}", "rgba": "0.2 0.4 0.9 1",   "mesh": "bottle_mesh",      "mass": "0.025"},
    {"name": "screwdriver", "pos": f"0.8  0.5 {_OBJECT_SURFACE_Z}", "rgba": "0.1 0.7 0.2 1",   "mesh": "screwdriver_mesh", "mass": "0.015"},
    {"name": "duck",        "pos": f"1.3 -0.2 {_OBJECT_SURFACE_Z}", "rgba": "1.0 0.6 0.1 1",   "mesh": "duck_mesh",        "mass": "0.020"},
    {"name": "lego",        "pos": f"0.9  0.1 {_OBJECT_SURFACE_Z}", "rgba": "0.95 0.2 0.2 1",  "mesh": "lego_mesh",        "mass": "0.008"},
]

# Go2 start position in the flat arena
_GO2_START: tuple[float, float, float] = (0.0, 0.0, 0.35)


# ---------------------------------------------------------------------------
# Scene XML builder — minimal flat arena (replaces heavy house scene)
# ---------------------------------------------------------------------------

def _build_go2_with_arm_scene_xml() -> Path:
    """Build merged Go2 + arm scene: flat arena + scattered objects.

    Strategy:
    1. Read go2.xml, inject arm body tree into base_link
    2. Assemble a minimal <mujoco> XML from scratch (no go2_room.xml)
       — just a flat floor, sky, and the Go2+arm model
    3. Append arm mesh assets, arm actuators, weld constraints, objects
    """
    go2_xml_path = _MJCF_DIR / "go2.xml"
    go2_assets_dir = str((_MJCF_DIR / "assets")).replace("\\", "/")
    arm_mesh_dir_str = str(_ARM_MESH_DIR).replace("\\", "/")

    # --- Step 1: Build arm body subtree, inject into go2.xml ---
    arm_body = _build_arm_body_xml(arm_mesh_dir_str)
    go2_raw = go2_xml_path.read_text(encoding="utf-8")
    go2_modified = _inject_arm_into_go2(go2_raw, arm_body)

    # --- Step 2: Extract sections from modified go2 XML ---
    go2_defaults_inner = _extract_defaults_inner(go2_modified)
    go2_assets_inner_xml = _extract_section_inner(go2_modified, "asset")
    go2_worldbody_inner = _extract_worldbody_inner(go2_modified)
    go2_actuators = _extract_section(go2_modified, "actuator")
    go2_sensors = _extract_section(go2_modified, "sensor")
    go2_keyframe = _extract_section(go2_modified, "keyframe")

    # --- Step 3: Arm-specific additions ---
    arm_defaults_inner = _extract_defaults_inner(_ARM_XML.read_text(encoding="utf-8"))
    arm_assets_xml = _build_arm_assets_xml(arm_mesh_dir_str)
    arm_actuators_xml = _build_arm_actuators_xml()
    arm_weld_xml = _build_weld_constraints_xml()
    objects_xml = _build_objects_xml()

    x0, y0, z0 = _GO2_START

    scene = f"""<mujoco model="go2_with_arm_arena">
  <compiler angle="radian" meshdir="{go2_assets_dir}" autolimits="true"/>

  <option cone="elliptic" impratio="100"/>

  <statistic center="{x0} {y0} 0.5" extent="4"/>

  <visual>
    <headlight diffuse="0.6 0.6 0.6" ambient="0.3 0.3 0.3" specular="0 0 0"/>
    <rgba haze="0.15 0.25 0.35 1"/>
    <global azimuth="-120" elevation="-25"/>
    <quality shadowsize="2048"/>
  </visual>

  <default>
    {go2_defaults_inner}
    <!-- SO-101 arm defaults -->
    {arm_defaults_inner}
  </default>

  <asset>
    <texture type="skybox" builtin="gradient"
             rgb1="0.88 0.90 0.95" rgb2="0.65 0.70 0.80" width="512" height="3072"/>
    <texture type="2d" name="floor_tex" builtin="checker"
             rgb1="0.82 0.78 0.70" rgb2="0.70 0.66 0.58" width="300" height="300"/>
    <material name="floor_mat" texture="floor_tex" texrepeat="4 4" reflectance="0.1"/>
    {go2_assets_inner_xml}
    {arm_assets_xml}
  </asset>

  <worldbody>
    <!-- Flat arena floor — 10m × 10m -->
    <geom name="floor" type="plane" size="5 5 0.1" material="floor_mat"
          condim="3" friction="0.8 0.02 0.01"/>
    <!-- Light -->
    <light name="sun" pos="0 0 4" dir="0 0 -1" directional="true"
           diffuse="0.8 0.8 0.8" specular="0.2 0.2 0.2" castshadow="true"/>

    <!-- Go2 + Arm -->
    {go2_worldbody_inner}

    <!-- Graspable objects on the ground -->
    {objects_xml}
  </worldbody>

  {go2_actuators}

  {arm_actuators_xml}

  {go2_sensors}

  {arm_weld_xml}

  {go2_keyframe}

</mujoco>"""

    out = _MJCF_DIR / "scene_go2_with_arm.xml"
    out.write_text(scene, encoding="utf-8")
    logger.info("Built Go2+Arm flat-arena scene: %s", out)
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
    """Build free-body objects scattered on the ground."""
    lines = []
    for obj in _OBJECTS_ON_ISLAND:
        name = obj["name"]
        pos = obj["pos"]   # already a complete position string
        rgba = obj["rgba"]
        mesh = obj["mesh"]
        mass = obj["mass"]

        if name == "lego":
            # Lego uses box + cylinder studs (no mesh)
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

def _extract_section_inner(xml: str, tag: str) -> str:
    """Extract inner content of <tag>...</tag>, stripping the outer tags."""
    full = _extract_section(xml, tag)
    if not full:
        return ""
    inner_m = re.match(rf"<{re.escape(tag)}[^>]*>(.*)</{re.escape(tag)}>", full, re.DOTALL)
    return inner_m.group(1).strip() if inner_m else ""


def _extract_section(xml: str, tag: str) -> str:
    """Extract a top-level <tag>...</tag> section from XML.

    Uses depth counting so nested identical tags (e.g. <default class="x">
    nested inside <default>) are handled correctly. The naive regex .*? with
    re.DOTALL stops at the first closing tag and produces malformed XML.
    """
    # Find the opening tag
    m = re.search(rf"<{re.escape(tag)}[\s>]", xml)
    if not m:
        return ""
    start = m.start()
    depth = 0
    i = start
    while i < len(xml):
        if xml[i] != "<":
            i += 1
            continue
        # Check for closing tag
        close_m = re.match(rf"</{re.escape(tag)}>", xml[i:])
        if close_m:
            depth -= 1
            if depth == 0:
                return xml[start:i + close_m.end()]
            i += close_m.end()
            continue
        # Check for opening tag (not self-closing)
        open_m = re.match(rf"<{re.escape(tag)}[\s>]", xml[i:])
        if open_m:
            # Self-closing: <tag ... />
            tag_end = xml.index(">", i)
            if xml[tag_end - 1] == "/":
                i = tag_end + 1
                continue
            depth += 1
            i += open_m.end()
            continue
        i += 1
    return ""


def _extract_defaults_inner(xml: str) -> str:
    """Extract the inner content of the top-level <default>...</default> block,
    excluding the outer wrapper tags. Used to merge arm defaults into go2 defaults."""
    full = _extract_section(xml, "default")
    if not full:
        return ""
    inner_m = re.match(r"<default[^>]*>(.*)</default>", full, re.DOTALL)
    return inner_m.group(1).strip() if inner_m else ""


def _extract_worldbody_inner(xml: str) -> str:
    """Extract inner content of <worldbody>...</worldbody>.

    Uses depth counting to handle nested bodies correctly.
    """
    full = _extract_section(xml, "worldbody")
    if not full:
        return ""
    inner_m = re.match(r"<worldbody[^>]*>(.*)</worldbody>", full, re.DOTALL)
    return inner_m.group(1).strip() if inner_m else ""



    """Extract inner content of <worldbody>...</worldbody>.

    Uses depth counting to handle nested <worldbody> if any, though in
    practice MuJoCo MJCF only has one. Avoids the re.DOTALL .*? truncation bug.
    """
    full = _extract_section(xml, "worldbody")
    if not full:
        return ""
    # Strip outer <worldbody ...> and </worldbody>
    inner_m = re.match(r"<worldbody[^>]*>(.*)</worldbody>", full, re.DOTALL)
    return inner_m.group(1).strip() if inner_m else ""


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
        self._model: Any = None
        self._data: Any = None
        self._viewer: Any = None
        self._connected: bool = False
        self._sim_lock: threading.RLock = threading.RLock()

        # Joint/actuator IDs (cached on connect)
        self._go2_leg_joint_ids: list[int] = []
        self._go2_leg_qpos_adrs: list[int] = []
        self._go2_leg_qvel_adrs: list[int] = []
        self._arm_joint_ids: list[int] = []
        self._arm_act_ids: list[int] = []
        self._ee_site_id: int = -1

        # Arm joint offsets are discovered dynamically because the merged XML
        # injection changes qpos ordering; do not assume legs occupy qpos[7:19].
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

        # Render helpers (created lazily)
        self._renderers: dict[tuple[str, int, int], Any] = {}
        self._cam_renderer: Any = None
        self._cam_obj: Any = None

    # ------------------------------------------------------------------
    # Capability properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "mujoco_go2_with_arm"

    @property
    def joint_names(self) -> list[str]:
        return list(_ARM_JOINT_NAMES)

    @property
    def dof(self) -> int:
        return len(_ARM_JOINT_NAMES)

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
        self._model = model
        self._data = data

        # Cache arm and Go2 leg joint IDs plus actuator IDs
        self._go2_leg_joint_ids = []
        self._arm_joint_ids = []
        self._arm_act_ids = []
        for jname in _ARM_JOINT_NAMES:
            jid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, jname)
            if jid < 0:
                raise RuntimeError(f"Arm joint '{jname}' not found in merged scene")
            self._arm_joint_ids.append(jid)
        for jname in _GO2_LEG_JOINT_NAMES:
            jid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, jname)
            if jid < 0:
                raise RuntimeError(f"Go2 leg joint '{jname}' not found in merged scene")
            self._go2_leg_joint_ids.append(jid)

        for aname in _ARM_ACTUATOR_NAMES:
            aid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, aname)
            if aid < 0:
                raise RuntimeError(f"Arm actuator '{aname}' not found in merged scene")
            self._arm_act_ids.append(aid)

        self._go2_leg_qpos_adrs = [model.jnt_qposadr[jid] for jid in self._go2_leg_joint_ids]
        self._go2_leg_qvel_adrs = [model.jnt_dofadr[jid] for jid in self._go2_leg_joint_ids]

        # Determine arm qpos/qvel offsets
        first_arm_jid = self._arm_joint_ids[0]
        self._arm_qpos_start = model.jnt_qposadr[first_arm_jid]
        self._arm_qvel_start = model.jnt_dofadr[first_arm_jid]
        self._ee_site_id = mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, _EE_SITE_NAME)
        if self._ee_site_id < 0:
            raise RuntimeError(f"Site '{_EE_SITE_NAME}' not found in merged scene")

        # Place Go2 at arena start position
        data.qpos[0] = _GO2_START[0]
        data.qpos[1] = _GO2_START[1]
        data.qpos[2] = _GO2_START[2]
        # Set standing leg joints
        for adr, pos in zip(self._go2_leg_qpos_adrs, _STAND_JOINTS):
            data.qpos[adr] = pos
        # Set arm to home position
        for i, jid in enumerate(self._arm_joint_ids):
            data.qpos[model.jnt_qposadr[jid]] = _ARM_HOME_JOINTS[i]
        jaw_aid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, _JAW_VISUAL_ACTUATOR_NAME)
        if jaw_aid >= 0:
            data.ctrl[jaw_aid] = 0.8

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
                    self._viewer.cam.lookat[:] = [0.5, 0.0, 0.3]
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
        for renderer in self._renderers.values():
            try:
                renderer.close()
            except Exception:
                pass
        self._renderers.clear()
        if self._cam_renderer is not None:
            try:
                self._cam_renderer.close()
            except Exception:
                pass
        self._cam_renderer = None
        self._cam_obj = None
        self._mj = None
        self._model = None
        self._data = None
        self._ee_site_id = -1
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

            time_now = float(self._data.time)
            is_moving = (vx != 0.0 or vy != 0.0 or vyaw != 0.0)

            if sim_step % _CTRL_DECIM == 0:
                q_cur = self._get_go2_leg_qpos()
                dq_cur = self._get_go2_leg_qvel()

                if is_moving:
                    q_target = _compute_gait_targets(time_now, vx, vy, vyaw)
                else:
                    q_target = np.array(_STAND_JOINTS, dtype=np.float64)

                tau = _KP * (q_target - q_cur) - _KD * dq_cur
                tau = np.clip(tau, -_TAU_LIMITS, _TAU_LIMITS)
                tau_hold = tau.copy()

            # Arm actuators are position-controlled (MuJoCo handles PD internally)
            # — no explicit torque computation needed; ctrl values set by set_joint_positions()

            with self._sim_lock:
                mj.mj_step1(self._model, self._data)
                self._mj.set_joint_torque(tau_hold)
                mj.mj_step2(self._model, self._data)

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
        """Return arm joint positions (5 controllable DOF)."""
        self._require_connection()
        with self._sim_lock:
            return [float(self._data.qpos[self._model.jnt_qposadr[jid]])
                    for jid in self._arm_joint_ids]

    def set_joint_positions(
        self,
        positions: list[float],
        duration: float | None = None,
    ) -> None:
        """Set arm joint target positions via position actuators."""
        self._require_connection()
        with self._sim_lock:
            for i, aid in enumerate(self._arm_act_ids):
                if i < len(positions):
                    self._data.ctrl[aid] = float(positions[i])

    def move_joints(
        self,
        positions: list[float],
        duration: float = 3.0,
    ) -> bool:
        """Move to target joint positions over duration seconds."""
        self._require_connection()
        if len(positions) != self.dof:
            raise ValueError(
                f"MuJoCoGo2WithArm.move_joints: expected {self.dof} positions, "
                f"got {len(positions)}"
            )

        mj = _get_mujoco()
        was_running = self._running
        if was_running:
            self._pause_physics()

        dt = self._model.opt.timestep
        steps = max(1, int(duration / dt))
        sync_interval = max(1, int(1.0 / 60.0 / dt))
        start = [float(self._data.ctrl[aid]) for aid in self._arm_act_ids]

        try:
            if self._viewer is not None:
                wall_start = time.monotonic()
                for i in range(steps):
                    t = (i + 1) / steps
                    with self._sim_lock:
                        for act_id, s, g in zip(self._arm_act_ids, start, positions):
                            self._data.ctrl[act_id] = s + t * (g - s)
                        mj.mj_step(self._model, self._data)
                    if i % sync_interval == 0:
                        self._viewer.sync()
                        sim_elapsed = (i + 1) * dt
                        wall_elapsed = time.monotonic() - wall_start
                        sleep = sim_elapsed - wall_elapsed
                        if sleep > 0:
                            time.sleep(sleep)
            else:
                for i in range(steps):
                    t = (i + 1) / steps
                    with self._sim_lock:
                        for act_id, s, g in zip(self._arm_act_ids, start, positions):
                            self._data.ctrl[act_id] = s + t * (g - s)
                        mj.mj_step(self._model, self._data)
        finally:
            if was_running:
                self._resume_physics()

        return True

    def fk(
        self,
        joint_positions: list[float],
    ) -> tuple[list[float], list[list[float]]]:
        """Forward kinematics via MuJoCo, matching MuJoCoArm semantics."""
        self._require_connection()
        mj = _get_mujoco()

        with self._sim_lock:
            old_qpos = self._data.qpos.copy()
            old_qvel = self._data.qvel.copy()
            try:
                for i, pos in enumerate(joint_positions):
                    self._data.joint(_ARM_JOINT_NAMES[i]).qpos[0] = pos
                mj.mj_forward(self._model, self._data)
                ee_pos = list(self._data.site_xpos[self._ee_site_id].copy())
                ee_rot = self._data.site_xmat[self._ee_site_id].reshape(3, 3).tolist()
                return ee_pos, ee_rot
            finally:
                self._data.qpos[:] = old_qpos
                self._data.qvel[:] = old_qvel
                mj.mj_forward(self._model, self._data)

    def ik(
        self,
        target_xyz: tuple[float, float, float],
        current_joints: list[float] | None = None,
    ) -> list[float] | None:
        """Inverse kinematics using the same damped least-squares solver as MuJoCoArm."""
        self._require_connection()
        mj = _get_mujoco()
        target = np.array(target_xyz, dtype=np.float64)

        with self._sim_lock:
            old_qpos = self._data.qpos.copy()
            old_qvel = self._data.qvel.copy()
            try:
                seed = current_joints if current_joints is not None else self.get_joint_positions()
                for i, pos in enumerate(seed):
                    self._data.joint(_ARM_JOINT_NAMES[i]).qpos[0] = pos

                arm_qpos_adrs = [
                    self._model.jnt_qposadr[jid] for jid in self._arm_joint_ids
                ]
                arm_dof_adrs = [
                    self._model.jnt_dofadr[jid] for jid in self._arm_joint_ids
                ]

                for _ in range(_IK_MAX_ITER):
                    mj.mj_forward(self._model, self._data)
                    ee_pos = self._data.site_xpos[self._ee_site_id].copy()
                    err = target - ee_pos
                    if np.linalg.norm(err) < _IK_TOL:
                        return [float(self._data.qpos[adr]) for adr in arm_qpos_adrs]

                    jacp = np.zeros((3, self._model.nv), dtype=np.float64)
                    mj.mj_jacSite(self._model, self._data, jacp, None, self._ee_site_id)
                    J = jacp[:, arm_dof_adrs]
                    JJt = J @ J.T + _IK_DAMPING * np.eye(3)
                    dq = J.T @ np.linalg.solve(JJt, err)

                    for i, adr in enumerate(arm_qpos_adrs):
                        self._data.qpos[adr] += _IK_STEP_SIZE * dq[i]
                        lo = self._model.jnt_range[self._arm_joint_ids[i], 0]
                        hi = self._model.jnt_range[self._arm_joint_ids[i], 1]
                        self._data.qpos[adr] = float(np.clip(self._data.qpos[adr], lo, hi))
                return None
            finally:
                self._data.qpos[:] = old_qpos
                self._data.qvel[:] = old_qvel
                mj.mj_forward(self._model, self._data)

    def get_object_positions(self) -> dict[str, tuple[float, float, float]]:
        """Return world positions of all graspable objects (ground truth)."""
        self._require_connection()
        mj = _get_mujoco()
        result = {}
        with self._sim_lock:
            for name in self._object_names:
                bid = mj.mj_name2id(self._model, mj.mjtObj.mjOBJ_BODY, name)
                if bid >= 0:
                    pos = self._data.xpos[bid]
                    result[name] = (float(pos[0]), float(pos[1]), float(pos[2]))
        return result

    def get_ee_position(self) -> tuple[float, float, float]:
        """Return end-effector position in world frame."""
        self._require_connection()
        with self._sim_lock:
            pos = self._data.site_xpos[self._ee_site_id]
            return (float(pos[0]), float(pos[1]), float(pos[2]))

    def render(
        self,
        camera_name: str = "overhead",
        width: int = 640,
        height: int = 480,
    ) -> Any:
        """Render an RGB image compatible with MuJoCoArm.render()."""
        self._require_connection()
        mj = _get_mujoco()
        key = (camera_name, width, height)

        with self._sim_lock:
            renderer = self._renderers.get(key)
            if renderer is None:
                renderer = mj.Renderer(self._model, height=height, width=width)
                self._renderers[key] = renderer

            camera = self._make_render_camera(camera_name)
            renderer.update_scene(self._data, camera=camera)
            rgb = renderer.render()
            return np.ascontiguousarray(rgb[:, :, ::-1])

    def stop(self) -> None:
        """Emergency stop — zero Go2 velocity and hold arm position."""
        self._require_connection()
        with self._cmd_lock:
            self._cmd_vel = (0.0, 0.0, 0.0)
        self.set_joint_positions(self.get_joint_positions())

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
        with self._sim_lock:
            return list(self._data.qpos[0:3].astype(float))

    def get_velocity(self) -> list[float]:
        self._require_connection()
        with self._sim_lock:
            return list(self._data.qvel[0:3].astype(float))

    def get_heading(self) -> float:
        self._require_connection()
        with self._sim_lock:
            w, x, y, z = self._data.qpos[3:7]
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

        with self._sim_lock:
            self._cam_renderer.update_scene(self._data, camera=self._cam_obj)
            return self._cam_renderer.render().copy()

    def _make_render_camera(self, camera_name: str) -> Any:
        """Return a MuJoCo camera config for named renders."""
        mj = _get_mujoco()
        if camera_name == "front":
            return self._make_front_render_camera()

        cam = mj.MjvCamera()
        cam.type = mj.mjtCamera.mjCAMERA_FREE

        if camera_name == "overhead":
            cam.lookat[:] = [17.0, 2.8, 0.9]
            cam.distance = 3.0
            cam.azimuth = 180
            cam.elevation = -70
        elif camera_name == "side":
            cam.lookat[:] = [17.0, 2.8, 0.9]
            cam.distance = 3.0
            cam.azimuth = 90
            cam.elevation = -20
        else:
            raise ValueError(f"Unknown render camera: {camera_name}")
        return cam

    def _make_front_render_camera(self) -> Any:
        """Build a free camera aligned with the robot heading for front renders."""
        mj = _get_mujoco()
        heading = self.get_heading()
        cos_h = math.cos(heading)
        sin_h = math.sin(heading)
        pos = self.get_position()

        cam = mj.MjvCamera()
        cam.type = mj.mjtCamera.mjCAMERA_FREE
        cam.lookat[:] = [pos[0] + cos_h * 2.0, pos[1] + sin_h * 2.0, pos[2] + 0.25]
        cam.distance = 2.0
        cam.azimuth = math.degrees(heading) + 180
        cam.elevation = -5
        return cam

    # ------------------------------------------------------------------
    # Posture commands (Go2)
    # ------------------------------------------------------------------

    def stand(self, duration: float = 2.0) -> bool:
        self._require_connection()
        target = np.array(_STAND_JOINTS, dtype=np.float64)
        self._pd_interpolate(target, duration)
        if self._is_stance_close(target):
            return True
        logger.warning(
            "MuJoCoGo2WithArm.stand: PD posture did not converge; applying hard stance reset"
        )
        self._force_leg_posture(target)
        return self._is_stance_close(target)

    def sit(self, duration: float = 2.0) -> bool:
        self._require_connection()
        target = np.array(_SIT_JOINTS, dtype=np.float64)
        self._pd_interpolate(target, duration)
        if self._is_stance_close(target, z_min=0.05, z_max=0.25):
            return True
        logger.warning(
            "MuJoCoGo2WithArm.sit: PD posture did not converge; applying hard posture reset"
        )
        self._force_leg_posture(target)
        return self._is_stance_close(target, z_min=0.05, z_max=0.25)

    def lie_down(self, duration: float = 2.0) -> bool:
        self._require_connection()
        target = np.array(_LIE_DOWN_JOINTS, dtype=np.float64)
        self._pd_interpolate(target, duration)
        if self._is_stance_close(target, z_min=0.0, z_max=0.15):
            return True
        logger.warning(
            "MuJoCoGo2WithArm.lie_down: PD posture did not converge; applying hard posture reset"
        )
        self._force_leg_posture(target)
        return self._is_stance_close(target, z_min=0.0, z_max=0.15)

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
        q_start = self._get_go2_leg_qpos()
        q_target = np.asarray(target_joints, dtype=np.float64)
        hold_steps = max(0, int(0.5 / dt))

        for step in range(total_steps + hold_steps):
            if step < total_steps:
                t_norm = (step + 1) * dt / (duration / 3.0)
                phase = float(np.tanh(t_norm))
                q_des = q_start + phase * (q_target - q_start)
            else:
                q_des = q_target

            q_cur = self._get_go2_leg_qpos()
            dq_cur = self._get_go2_leg_qvel()
            tau = _KP * (q_des - q_cur) - _KD * dq_cur
            tau = np.clip(tau, -_TAU_LIMITS, _TAU_LIMITS)
            self._mj.set_joint_torque(tau)
            mj.mj_step(model, data)

            if self._viewer is not None and step % _VIEWER_SYNC_EVERY == 0:
                self._viewer.sync()

        if was_running:
            self._resume_physics()

    def _is_stance_close(
        self,
        target_joints: np.ndarray,
        joint_tol: float = 0.25,
        z_min: float = 0.2,
        z_max: float = 0.45,
    ) -> bool:
        """Check whether Go2 leg joints and base height are near the requested posture."""
        with self._sim_lock:
            actual = self._get_go2_leg_qpos()
            base_z = float(self._data.qpos[2])
        max_err = float(np.max(np.abs(actual - target_joints)))
        return bool(max_err <= joint_tol and z_min <= base_z <= z_max)

    def _force_leg_posture(self, target_joints: np.ndarray) -> None:
        """Hard-reset Go2 leg joints to the target posture and zero leg velocities."""
        mj = _get_mujoco()
        with self._sim_lock:
            for adr, pos in zip(self._go2_leg_qpos_adrs, np.asarray(target_joints, dtype=np.float64)):
                self._data.qpos[adr] = float(pos)
            for adr in self._go2_leg_qvel_adrs:
                self._data.qvel[adr] = 0.0
            self._data.qpos[2] = max(float(self._data.qpos[2]), _GO2_START[2])
            mj.mj_forward(self._model, self._data)

    def _get_go2_leg_qpos(self) -> np.ndarray:
        """Return Go2 leg joint positions in canonical FL/FR/RL/RR order."""
        return np.array([self._data.qpos[adr] for adr in self._go2_leg_qpos_adrs], dtype=np.float64)

    def _get_go2_leg_qvel(self) -> np.ndarray:
        """Return Go2 leg joint velocities in canonical FL/FR/RL/RR order."""
        return np.array([self._data.qvel[adr] for adr in self._go2_leg_qvel_adrs], dtype=np.float64)

    # ------------------------------------------------------------------
    # Sensor helpers
    # ------------------------------------------------------------------

    def _update_odometry(self) -> None:
        from vector_os_nano.core.types import Odometry
        with self._sim_lock:
            q = self._data.qpos.copy()
            v = self._data.qvel.copy()
            timestamp = float(self._data.time)
        self._last_odom = Odometry(
            timestamp=timestamp,
            x=float(q[0]), y=float(q[1]), z=float(q[2]),
            qx=float(q[4]), qy=float(q[5]), qz=float(q[6]), qw=float(q[3]),
            vx=float(v[0]), vy=float(v[1]), vz=float(v[2]), vyaw=float(v[5]),
        )

    def _update_lidar(self) -> None:
        """Simplified lidar — same as MuJoCoGo2 but with fewer rays for performance."""
        from vector_os_nano.core.types import LaserScan
        mj = _get_mujoco()

        with self._sim_lock:
            pos = self._data.qpos[0:3].copy().astype(np.float64)
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
            with self._sim_lock:
                dist = mj.mj_ray(
                    self._model, self._data,
                    pos_lidar, direction, None, 1, robot_body_id, geom_id,
                )
            ranges.append(float(dist) if dist > 0 else float("inf"))

        self._last_scan = LaserScan(
            timestamp=float(self._data.time),
            angle_min=-math.pi, angle_max=math.pi,
            angle_increment=math.radians(azimuth_step),
            range_min=0.1, range_max=12.0,
            ranges=tuple(ranges),
        )
        self._last_pointcloud = []  # simplified — 2D only for now
