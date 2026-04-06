"""Static contract tests for MuJoCoGo2WithArm.

These tests avoid importing mujoco at runtime; they only verify that the
combined backend exposes the API surface expected by existing arm skills,
gripper, and perception helpers.
"""

from vector_os_nano.hardware.sim.mujoco_go2_with_arm import MuJoCoGo2WithArm


def test_combined_backend_exposes_arm_properties():
    arm = MuJoCoGo2WithArm()
    assert arm.name == "mujoco_go2_with_arm"
    assert arm.dof == 5
    assert arm.joint_names == [
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
    ]


def test_combined_backend_has_required_arm_methods():
    arm = MuJoCoGo2WithArm()
    for attr in (
        "get_joint_positions",
        "set_joint_positions",
        "move_joints",
        "ik",
        "fk",
        "render",
        "get_object_positions",
        "get_ee_position",
        "stop",
    ):
        assert hasattr(arm, attr), attr


def test_combined_backend_has_required_sim_handles():
    arm = MuJoCoGo2WithArm()
    for attr in ("_model", "_data", "_viewer", "_ee_site_id", "_connected", "_sim_lock"):
        assert hasattr(arm, attr), attr
