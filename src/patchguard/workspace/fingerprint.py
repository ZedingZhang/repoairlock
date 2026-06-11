"""Workspace fingerprint — captures and verifies original workspace integrity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from patchguard.exceptions import InvariantViolationError, WorkspaceError
from patchguard.workspace.git_client import GitClient


@dataclass(frozen=True)
class WorkspaceFingerprint:
    """Immutable snapshot of a git working tree at a point in time.

    Captured before and after a run to prove the original workspace
    was not modified (INV-001).
    """

    head_sha: str
    status_hash: str  # sha256 of `git status --porcelain=v1 -z`
    diff_hash: str  # sha256 of `git diff HEAD`
    untracked_files: tuple[str, ...] = ()  # relative paths, sorted

    def summary(self) -> str:
        return (
            f"sha256:{_digest(self.head_sha + self.status_hash + self.diff_hash)}"
        )

    def assert_unchanged(self, after: WorkspaceFingerprint, *, label: str = "") -> None:
        """Raise InvariantViolationError if the two fingerprints differ."""
        prefix = f"{label}: " if label else ""
        if self.head_sha != after.head_sha:
            raise InvariantViolationError(
                f"{prefix}HEAD changed: {self.head_sha[:8]} -> {after.head_sha[:8]}"
            )
        if self.status_hash != after.status_hash:
            raise InvariantViolationError(
                f"{prefix}Working tree status changed (dirty state modified)"
            )
        if self.diff_hash != after.diff_hash:
            raise InvariantViolationError(
                f"{prefix}Tracked file diffs changed"
            )
        if self.untracked_files != after.untracked_files:
            raise InvariantViolationError(
                f"{prefix}Untracked files changed"
            )


def capture_fingerprint(repo: Path, git: GitClient) -> WorkspaceFingerprint:
    """Capture a fingerprint of the current working tree state."""
    try:
        head_sha = git.head_sha(repo)
    except WorkspaceError as exc:
        raise WorkspaceError(
            f"Failed to get HEAD SHA for {repo}. Is this a git repository?"
        ) from exc
    status_raw = git.status_porcelain(repo)
    diff_raw = git.diff_head(repo)
    untracked = tuple(git.untracked_files(repo))
    return WorkspaceFingerprint(
        head_sha=head_sha,
        status_hash=_sha256_hex(status_raw),
        diff_hash=_sha256_hex(diff_raw),
        untracked_files=untracked,
    )


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _digest(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]
