from __future__ import annotations

import math


def test_forward_gait_calf_is_antiphase_to_thigh() -> None:
    from vector_os_nano.hardware.sim import mujoco_go2

    q_target = mujoco_go2._compute_gait_targets(0.0, vx=0.3, vy=0.0, vyaw=0.0)

    thigh_delta = q_target[1] - mujoco_go2._STAND_JOINTS[1]
    calf_delta = q_target[2] - mujoco_go2._STAND_JOINTS[2]

    assert math.isclose(mujoco_go2._CALF_PHASE, math.pi)
    assert thigh_delta == 0.0
    assert calf_delta == 0.0


def test_forward_gait_calf_moves_opposite_to_thigh_after_quarter_cycle() -> None:
    from vector_os_nano.hardware.sim import mujoco_go2

    t = 1.0 / (4.0 * mujoco_go2._GAIT_FREQ)
    q_target = mujoco_go2._compute_gait_targets(t, vx=0.3, vy=0.0, vyaw=0.0)

    thigh_delta = q_target[1] - mujoco_go2._STAND_JOINTS[1]
    calf_delta = q_target[2] - mujoco_go2._STAND_JOINTS[2]

    assert thigh_delta > 0.0
    assert calf_delta < 0.0
