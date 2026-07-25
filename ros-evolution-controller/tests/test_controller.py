from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ros_evolution_controller import EvolutionController
from ros_evolution_controller.workspace import WorkspaceError


def git(workspace: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=workspace, capture_output=True, text=True, check=True)
    return result.stdout.strip()


@pytest.fixture
def runtime_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "runtime"
    workspace.mkdir()
    git(workspace, "init")
    git(workspace, "config", "user.name", "Test User")
    git(workspace, "config", "user.email", "test@example.com")
    (workspace / "node.py").write_text("VALUE = 1\n", encoding="utf-8")
    git(workspace, "add", "node.py")
    git(workspace, "commit", "-m", "baseline")
    return workspace


def passing_command() -> list[str]:
    return [sys.executable, "-c", "print('validation ok')"]


def test_candidate_requires_approval_then_promotes_and_rolls_back(runtime_workspace: Path, tmp_path: Path) -> None:
    controller = EvolutionController(runtime_workspace, tmp_path / "state")
    candidate = controller.create_candidate()
    candidate_path = Path(candidate["path"])
    (candidate_path / "node.py").write_text("VALUE = 2\n", encoding="utf-8")

    report = controller.run_validation(
        candidate["candidate_id"],
        metrics={"latency_ms": 8, "message_hz": 20, "action_success_rate": 1.0},
        baseline={"latency_ms": 10, "message_hz": 10, "action_success_rate": 0.9},
        commands=[passing_command()],
    )
    assert report.passed
    assert runtime_workspace.joinpath("node.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    with pytest.raises(RuntimeError, match="approved"):
        controller.promote(candidate["candidate_id"])

    controller.approve_candidate(candidate["candidate_id"], "reviewed")
    promoted = controller.promote(candidate["candidate_id"])
    assert promoted["status"] == "promoted"
    assert runtime_workspace.joinpath("node.py").read_text(encoding="utf-8") == "VALUE = 2\n"

    controller.save_verified_skill(candidate["candidate_id"], "repair value", "Updated node safely")
    assert controller.search_skills("safely")[0]["name"] == "repair value"

    monitored = controller.monitor(candidate["candidate_id"], {"latency_ms": 30}, {"latency_ms": 10})
    assert not monitored["healthy"]
    assert runtime_workspace.joinpath("node.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_metric_regression_rejects_candidate(runtime_workspace: Path, tmp_path: Path) -> None:
    controller = EvolutionController(runtime_workspace, tmp_path / "state")
    candidate = controller.create_candidate()
    report = controller.run_validation(
        candidate["candidate_id"],
        metrics={"latency_ms": 20},
        baseline={"latency_ms": 10},
        commands=[passing_command()],
    )
    assert not report.passed
    assert report.regressions == ["latency_ms regressed: 20 > 10"]
    with pytest.raises(RuntimeError, match="awaiting_approval"):
        controller.submit_for_approval(candidate["candidate_id"])


def test_interface_change_requires_explicit_approval(runtime_workspace: Path, tmp_path: Path) -> None:
    controller = EvolutionController(runtime_workspace, tmp_path / "state")
    candidate = controller.create_candidate()
    interface = Path(candidate["path"]) / "interfaces" / "RobotState.msg"
    interface.parent.mkdir()
    interface.write_text("string state\n", encoding="utf-8")
    report = controller.run_validation(candidate["candidate_id"], {}, {}, commands=[passing_command()])
    assert report.interface_changed

    with pytest.raises(PermissionError, match="approve_interfaces"):
        controller.approve_candidate(candidate["candidate_id"], "normal code review")

    assert controller.approve_candidate(candidate["candidate_id"], "interface review", approve_interfaces=True)["status"] == "approved"
    controller.promote(candidate["candidate_id"])
    assert runtime_workspace.joinpath("interfaces", "RobotState.msg").exists()


def test_promotion_requires_clean_runtime_baseline(runtime_workspace: Path, tmp_path: Path) -> None:
    controller = EvolutionController(runtime_workspace, tmp_path / "state")
    candidate = controller.create_candidate()
    Path(candidate["path"], "node.py").write_text("VALUE = 2\n", encoding="utf-8")
    controller.run_validation(candidate["candidate_id"], {}, {}, commands=[passing_command()])
    controller.approve_candidate(candidate["candidate_id"], "reviewed")
    runtime_workspace.joinpath("operator-note.txt").write_text("do not publish over this\n", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="clean baseline"):
        controller.promote(candidate["candidate_id"])
