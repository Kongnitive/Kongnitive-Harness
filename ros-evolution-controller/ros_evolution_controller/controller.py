from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Callable, Iterable

from .models import CandidateStatus, CommandEvidence, ValidationReport
from .store import EvolutionStore
from .workspace import CompletedCommand, WorkspaceError, WorkspaceManager

CommandRunner = Callable[[list[str], Path | None], CompletedCommand]


class EvolutionController:
    """Stateful, deterministic safety boundary between an agent and ROS code."""

    DEFAULT_VALIDATION = (
        ("colcon", "build", "--symlink-install"),
        ("colcon", "test"),
        ("colcon", "test-result", "--verbose"),
    )
    LOWER_IS_BETTER = {"latency_ms", "timeout_rate", "loss_rate", "recovery_ms"}
    HIGHER_IS_BETTER = {"message_hz", "action_success_rate"}

    def __init__(self, runtime_workspace: Path, state_dir: Path, command_runner: CommandRunner | None = None) -> None:
        self.runtime_workspace = runtime_workspace.resolve()
        self.state_dir = state_dir.resolve()
        self.workspace = WorkspaceManager(self.runtime_workspace, self.state_dir / "candidates")
        self.store = EvolutionStore(self.state_dir / "evolution.sqlite3")
        self._run = command_runner or self.workspace.run

    def inspect_runtime(self) -> dict:
        trajectory_id = self._new_id("trajectory")
        commands = (
            ("ros2", "node", "list"),
            ("ros2", "topic", "list"),
            ("ros2", "service", "list"),
            ("ros2", "action", "list"),
        )
        observations = [self._evidence(self._run(list(command), self.runtime_workspace)) for command in commands]
        payload = {"runtime_workspace": str(self.runtime_workspace), "observations": observations}
        self.store.add_trajectory(trajectory_id, "observe", payload)
        return {"trajectory_id": trajectory_id, **payload}

    def create_candidate(self) -> dict:
        candidate_id = self._new_id("candidate")
        candidate_path = self.workspace.create_candidate(candidate_id)
        base_revision = self.workspace.revision(self.runtime_workspace)
        self.store.add_candidate(candidate_id, candidate_path, base_revision)
        self.store.add_evidence(candidate_id, "candidate_created", {"base_revision": base_revision})
        return {"candidate_id": candidate_id, "path": str(candidate_path), "base_revision": base_revision}

    def run_validation(
        self,
        candidate_id: str,
        metrics: dict[str, float],
        baseline: dict[str, float],
        commands: Iterable[Iterable[str]] | None = None,
    ) -> ValidationReport:
        candidate = self.store.candidate(candidate_id)
        self._require_status(candidate, {CandidateStatus.CREATED, CandidateStatus.REJECTED})
        candidate_path = Path(candidate["path"])
        self.store.set_candidate(candidate_id, CandidateStatus.VALIDATING)
        command_evidence = [
            self._evidence(self._run(list(command), candidate_path))
            for command in (commands or self.DEFAULT_VALIDATION)
        ]
        changed_files = self.workspace.changed_files(candidate_path)
        interface_changed = any(path.endswith((".msg", ".srv", ".action")) for path in changed_files)
        regressions = self._metric_regressions(metrics, baseline)
        passed = all(command.returncode == 0 for command in command_evidence) and not regressions
        status = CandidateStatus.AWAITING_APPROVAL if passed else CandidateStatus.REJECTED
        report = ValidationReport(candidate_id, passed, command_evidence, metrics, regressions, interface_changed)
        self.store.set_candidate(candidate_id, status, interface_changed=int(interface_changed))
        self.store.add_evidence(candidate_id, "validation", {**report.as_dict(), "changed_files": changed_files})
        return report

    def submit_for_approval(self, candidate_id: str) -> dict:
        candidate = self.store.candidate(candidate_id)
        self._require_status(candidate, {CandidateStatus.AWAITING_APPROVAL})
        return {
            "candidate_id": candidate_id,
            "status": candidate["status"],
            "interface_changed": bool(candidate["interface_changed"]),
            "evidence": self.store.evidence(candidate_id),
        }

    def approve_candidate(self, candidate_id: str, note: str, approve_interfaces: bool = False) -> dict:
        candidate = self.store.candidate(candidate_id)
        self._require_status(candidate, {CandidateStatus.AWAITING_APPROVAL})
        if candidate["interface_changed"] and not approve_interfaces:
            raise PermissionError("Candidate changes ROS interfaces; approve_interfaces=true is required")
        self.store.set_candidate(candidate_id, CandidateStatus.APPROVED, approval_note=note)
        self.store.add_evidence(candidate_id, "approval", {"note": note, "interfaces_approved": approve_interfaces})
        return {"candidate_id": candidate_id, "status": CandidateStatus.APPROVED}

    def promote(self, candidate_id: str) -> dict:
        candidate = self.store.candidate(candidate_id)
        self._require_status(candidate, {CandidateStatus.APPROVED})
        patch = self.workspace.patch(Path(candidate["path"]))
        commit = self.workspace.apply_and_commit(patch, candidate_id)
        self.store.set_candidate(candidate_id, CandidateStatus.PROMOTED, promotion_commit=commit)
        self.store.add_evidence(candidate_id, "promotion", {"commit": commit})
        return {"candidate_id": candidate_id, "status": CandidateStatus.PROMOTED, "commit": commit}

    def rollback(self, candidate_id: str, reason: str) -> dict:
        candidate = self.store.candidate(candidate_id)
        self._require_status(candidate, {CandidateStatus.PROMOTED})
        rollback_commit = self.workspace.revert(candidate["promotion_commit"])
        self.store.set_candidate(candidate_id, CandidateStatus.ROLLED_BACK)
        self.store.add_evidence(candidate_id, "rollback", {"reason": reason, "commit": rollback_commit})
        return {"candidate_id": candidate_id, "status": CandidateStatus.ROLLED_BACK, "commit": rollback_commit}

    def monitor(self, candidate_id: str, metrics: dict[str, float], baseline: dict[str, float]) -> dict:
        """Record post-promotion metrics and revert a demonstrably worse release."""
        candidate = self.store.candidate(candidate_id)
        self._require_status(candidate, {CandidateStatus.PROMOTED})
        regressions = self._metric_regressions(metrics, baseline)
        self.store.add_evidence(candidate_id, "monitor", {"metrics": metrics, "regressions": regressions})
        if regressions:
            result = self.rollback(candidate_id, "; ".join(regressions))
            return {"healthy": False, "regressions": regressions, "rollback": result}
        return {"healthy": True, "regressions": []}

    def save_verified_skill(self, candidate_id: str, name: str, content: str) -> None:
        candidate = self.store.candidate(candidate_id)
        self._require_status(candidate, {CandidateStatus.PROMOTED})
        self.store.add_skill(candidate_id, name, content)

    def search_skills(self, query: str) -> list[dict[str, str]]:
        return self.store.search_skills(query)

    @staticmethod
    def _evidence(result: CompletedCommand) -> CommandEvidence:
        return CommandEvidence(result.command, result.returncode, result.stdout, result.stderr)

    @classmethod
    def _metric_regressions(cls, metrics: dict[str, float], baseline: dict[str, float]) -> list[str]:
        regressions: list[str] = []
        for name, base_value in baseline.items():
            if name not in metrics:
                regressions.append(f"missing metric: {name}")
                continue
            value = metrics[name]
            if name in cls.LOWER_IS_BETTER and value > base_value:
                regressions.append(f"{name} regressed: {value} > {base_value}")
            if name in cls.HIGHER_IS_BETTER and value < base_value:
                regressions.append(f"{name} regressed: {value} < {base_value}")
        return regressions

    @staticmethod
    def _require_status(candidate: dict, expected: set[CandidateStatus]) -> None:
        status = CandidateStatus(candidate["status"])
        if status not in expected:
            valid = ", ".join(item.value for item in expected)
            raise RuntimeError(f"Candidate {candidate['id']} is {status.value}; expected one of: {valid}")

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"
