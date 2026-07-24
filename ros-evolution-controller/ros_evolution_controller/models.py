from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class CandidateStatus(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    REJECTED = "rejected"
    APPROVED = "approved"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class CommandEvidence:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationReport:
    candidate_id: str
    passed: bool
    commands: list[CommandEvidence]
    metrics: dict[str, float]
    regressions: list[str]
    interface_changed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "passed": self.passed,
            "commands": [command.as_dict() for command in self.commands],
            "metrics": self.metrics,
            "regressions": self.regressions,
            "interface_changed": self.interface_changed,
        }
