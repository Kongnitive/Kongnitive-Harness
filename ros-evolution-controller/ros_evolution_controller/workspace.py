from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompletedCommand:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class WorkspaceManager:
    def __init__(self, runtime_workspace: Path, candidates_root: Path) -> None:
        self.runtime_workspace = runtime_workspace.resolve()
        self.candidates_root = candidates_root.resolve()

    def run(self, command: list[str], cwd: Path | None = None) -> CompletedCommand:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return CompletedCommand(command, completed.returncode, completed.stdout, completed.stderr)

    def require_git_workspace(self) -> None:
        result = self.run(["git", "rev-parse", "--is-inside-work-tree"], self.runtime_workspace)
        if result.returncode != 0 or result.stdout.strip() != "true":
            raise WorkspaceError(f"Runtime workspace is not a git worktree: {self.runtime_workspace}")

    def revision(self, workspace: Path | None = None) -> str:
        result = self.run(["git", "rev-parse", "HEAD"], workspace or self.runtime_workspace)
        if result.returncode != 0:
            raise WorkspaceError(result.stderr.strip() or "Cannot read git revision")
        return result.stdout.strip()

    def create_candidate(self, candidate_id: str) -> Path:
        self.require_git_workspace()
        self.candidates_root.mkdir(parents=True, exist_ok=True)
        candidate_path = self.candidates_root / candidate_id
        result = self.run(
            ["git", "worktree", "add", "--detach", str(candidate_path), "HEAD"], self.runtime_workspace
        )
        if result.returncode != 0:
            raise WorkspaceError(result.stderr.strip() or "Failed to create candidate worktree")
        return candidate_path

    def changed_files(self, candidate_path: Path) -> list[str]:
        result = self.run(["git", "diff", "--name-only", "HEAD"], candidate_path)
        if result.returncode != 0:
            raise WorkspaceError(result.stderr.strip() or "Failed to inspect candidate diff")
        untracked = self.run(["git", "ls-files", "--others", "--exclude-standard"], candidate_path)
        if untracked.returncode != 0:
            raise WorkspaceError(untracked.stderr.strip() or "Failed to inspect untracked candidate files")
        return sorted({*result.stdout.splitlines(), *untracked.stdout.splitlines()} - {""})

    def patch(self, candidate_path: Path) -> str:
        # Intent-to-add makes untracked files visible to git diff without staging
        # their content. Candidate worktrees are disposable, so this does not
        # touch the approved runtime index.
        intent = self.run(["git", "add", "--intent-to-add", "--all"], candidate_path)
        if intent.returncode != 0:
            raise WorkspaceError(intent.stderr.strip() or "Failed to prepare candidate patch")
        result = self.run(["git", "diff", "--binary", "HEAD"], candidate_path)
        if result.returncode != 0:
            raise WorkspaceError(result.stderr.strip() or "Failed to create candidate patch")
        return result.stdout

    def apply_and_commit(self, patch: str, candidate_id: str) -> str:
        if not patch:
            raise WorkspaceError("Candidate has no changes to promote")
        patch_process = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=self.runtime_workspace,
            input=patch,
            capture_output=True,
            text=True,
            check=False,
        )
        if patch_process.returncode != 0:
            raise WorkspaceError(patch_process.stderr.strip() or "Failed to apply candidate patch")
        commit = self.run(
            [
                "git", "-c", "user.name=ROS Evolution Controller",
                "-c", "user.email=controller@localhost",
                "add", "--all",
            ],
            self.runtime_workspace,
        )
        if commit.returncode != 0:
            raise WorkspaceError(commit.stderr.strip() or "Patch applied but staging failed")
        commit = self.run(
            [
                "git", "-c", "user.name=ROS Evolution Controller",
                "-c", "user.email=controller@localhost",
                "commit", "-m", f"Promote candidate {candidate_id}",
            ],
            self.runtime_workspace,
        )
        if commit.returncode != 0:
            raise WorkspaceError(commit.stderr.strip() or "Patch applied but commit failed")
        return self.revision()

    def revert(self, promotion_commit: str) -> str:
        result = self.run(
            ["git", "-c", "user.name=ROS Evolution Controller", "-c", "user.email=controller@localhost", "revert", "--no-edit", promotion_commit],
            self.runtime_workspace,
        )
        if result.returncode != 0:
            raise WorkspaceError(result.stderr.strip() or "Failed to create rollback commit")
        return self.revision()
