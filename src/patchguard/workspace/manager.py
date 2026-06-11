"""WorkspaceManager — manages git worktree lifecycle for isolated agent execution."""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from pathlib import Path

from patchguard.exceptions import CleanupError, WorkspaceError
from patchguard.workspace.fingerprint import (
    WorkspaceFingerprint,
    capture_fingerprint,
)
from patchguard.workspace.git_client import GitClient


class WorkspaceManager:
    """Creates and cleans up detached git worktrees for agent isolation.

    Guarantees INV-001: the original working tree is never modified.
    A fingerprint is captured before and after every operation to prove it.
    """

    def __init__(
        self,
        *,
        git: GitClient | None = None,
        tmp_root: Path | None = None,
    ) -> None:
        self._git = git or GitClient()
        self._tmp_root = tmp_root or Path(tempfile.gettempdir())

    # -- public API --------------------------------------------------------

    def prepare(
        self, source_repo: str | Path, run_id: str
    ) -> tuple[Path, WorkspaceFingerprint]:
        """Validate repo, capture fingerprint, create detached worktree.

        Returns (worktree_path, before_fingerprint).
        """
        repo = Path(source_repo).resolve()
        toplevel = self._git.assert_git_repo(repo)

        # Capture fingerprint BEFORE
        before = capture_fingerprint(toplevel, self._git)

        # Create worktree
        worktree_path = self._tmp_root / f"patchguard-wt-{run_id}"
        if worktree_path.exists():
            shutil.rmtree(worktree_path)
        self._git.worktree_add_detach(toplevel, worktree_path, before.head_sha)

        # Verify fingerprint unchanged after worktree creation
        after_create = capture_fingerprint(toplevel, self._git)
        before.assert_unchanged(after_create, label="After worktree creation")

        return worktree_path, before

    def export_patch(self, worktree: Path) -> str:
        """Export `git diff` from the worktree as a patch."""
        return self._git.diff_worktree(worktree)

    def cleanup(
        self, source_repo: str | Path, worktree: Path
    ) -> WorkspaceFingerprint:
        """Remove the worktree, prune metadata, and capture final fingerprint.

        On failure, prints manual cleanup instructions and raises CleanupError.
        """
        repo = Path(source_repo).resolve()
        toplevel = self._git.assert_git_repo(repo)

        # Attempt worktree removal
        with contextlib.suppress(WorkspaceError):
            self._git.worktree_remove(toplevel, worktree, force=True)
        with contextlib.suppress(WorkspaceError):
            self._git.worktree_prune(toplevel)

        # If worktree directory still exists, print manual instructions
        if worktree.exists():
            _warn_manual_cleanup(worktree, toplevel)
            raise CleanupError(
                f"Failed to remove worktree: {worktree}. "
                f"Manually run: git -C {toplevel} worktree remove --force {worktree}"
            )

        # Capture final fingerprint
        after = capture_fingerprint(toplevel, self._git)
        return after

    def verify_source_unchanged(
        self,
        before: WorkspaceFingerprint,
        after: WorkspaceFingerprint,
    ) -> None:
        """Verify the original working tree fingerprint is unchanged (INV-001)."""
        before.assert_unchanged(after, label="INV-001 violation")


def _warn_manual_cleanup(worktree: Path, repo: Path) -> None:
    print(
        f"\n[!] WARNING: Failed to automatically remove worktree at {worktree}\n"
        f"    Manual cleanup required:\n"
        f"    git -C {repo} worktree remove --force {worktree}\n"
        f"    git -C {repo} worktree prune\n"
    )
