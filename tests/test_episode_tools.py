"""
Tests for episode simulation tools and AI patch loop helpers.
"""

from pathlib import Path
import uuid

import pytest

from kongnitive_ros2_edgemcp.core.episode_manager import EpisodeManager
from kongnitive_ros2_edgemcp.tools import episode_tools


@pytest.mark.asyncio
async def test_run_episode_is_reproducible_for_same_seed():
    em = EpisodeManager()
    profile = {"object_pose_jitter": 0.2, "sensor_noise": 0.1}

    r1 = await episode_tools.run_episode(em, seed=1234, profile=profile)
    r2 = await episode_tools.run_episode(em, seed=1234, profile=profile)

    assert r1["status"] == "success"
    assert r2["status"] == "success"
    assert r1["result"]["success"] == r2["result"]["success"]
    assert r1["result"]["failure_code"] == r2["result"]["failure_code"]


@pytest.mark.asyncio
async def test_get_metrics_and_failure_trace():
    em = EpisodeManager()
    run = await episode_tools.run_episode(em, seed=42, profile={"sensor_noise": 0.9})
    run_id = run["result"]["run_id"]

    metrics = await episode_tools.get_metrics(em, run_id)
    trace = await episode_tools.get_failure_trace(em, run_id)

    assert metrics["status"] == "success"
    assert "summary" in metrics
    assert trace["status"] == "success"
    assert trace["trace"]["run_id"] == run_id


class _FakeNodeManager:
    def __init__(self, script_dir: Path):
        self.script_dir = script_dir
        self.nodes = {}
        self.last_script = ""

    async def push_node(self, node_name: str, script: str):
        self.last_script = script
        if "INVALID_PATCH" in script:
            return {"status": "error", "message": "patch error"}
        path = Path(self.script_dir) / f"{node_name}.py"
        path.write_text(script, encoding="utf-8")
        return {"status": "success", "message": "ok"}

    async def get_node_script(self, node_name: str):
        path = Path(self.script_dir) / f"{node_name}.py"
        if not path.exists():
            return {"status": "error", "message": "not found"}
        return {"status": "success", "script": path.read_text(encoding="utf-8")}


@pytest.mark.asyncio
async def test_patch_and_restart_rolls_back_on_failure():
    temp_dir = Path(__file__).parent / ".tmp_episode_tests" / str(uuid.uuid4())
    temp_dir.mkdir(parents=True, exist_ok=True)
    nm = _FakeNodeManager(temp_dir)
    node_name = "detector"
    original = "print('stable')"
    script_path = temp_dir / f"{node_name}.py"
    script_path.write_text(original, encoding="utf-8")

    result = await episode_tools.patch_and_restart(nm, node_name, "INVALID_PATCH")
    restored = script_path.read_text(encoding="utf-8")

    assert result["status"] == "error"
    assert result["rolled_back"] is True
    assert restored == original
