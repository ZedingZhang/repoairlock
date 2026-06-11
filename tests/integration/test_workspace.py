"""Integration tests for WorkspaceManager — prove INV-001 (original workspace immutable).

These tests create real git repos and exercise the full worktree lifecycle.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from patchguard.exceptions import InvariantViolationError, WorkspaceError
from patchguard.workspace.fingerprint import capture_fingerprint
from patchguard.workspace.git_client import GitClient
from patchguard.workspace.manager import WorkspaceManager

# -- helpers ---------------------------------------------------------------


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, ["init", "-b", "main"])
    _git(path, ["config", "user.email", "test@test.test"])
    _git(path, ["config", "user.name", "Test"])


def _git(cwd: Path, args: list[str]) -> None:
    subprocess.run(["git"] + args, cwd=cwd, capture_output=True, check=True)


def _commit(path: Path, filename: str, content: str, msg: str = "commit") -> None:
    (path / filename).write_text(content, encoding="utf-8")
    _git(path, ["add", filename])
    _git(path, ["commit", "-m", msg])


# -- fixtures --------------------------------------------------------------


@pytest.fixture
def git() -> GitClient:
    return GitClient()


@pytest.fixture
def wm() -> WorkspaceManager:
    return WorkspaceManager()


@pytest.fixture
def clean_repo(tmp_path: Path) -> Path:
    """A clean git repo with one committed file."""
    repo = tmp_path / "clean_repo"
    _init_repo(repo)
    _commit(repo, "hello.py", "print('hello')\n")
    return repo


@pytest.fixture
def dirty_repo(tmp_path: Path) -> Path:
    """A git repo with a committed file and uncommitted tracked changes."""
    repo = tmp_path / "dirty_repo"
    _init_repo(repo)
    _commit(repo, "hello.py", "print('hello')\n")
    (repo / "hello.py").write_text("print('modified')\n")
    return repo


@pytest.fixture
def untracked_repo(tmp_path: Path) -> Path:
    """A clean git repo with an additional untracked file."""
    repo = tmp_path / "untracked_repo"
    _init_repo(repo)
    _commit(repo, "hello.py", "print('hello')\n")
    (repo / "unrelated.log").write_text("debug info\n")
    return repo


# -- clean repo tests ------------------------------------------------------


class TestCleanRepo:
    def test_clean_repo_unchanged_after_full_lifecycle(
        self, clean_repo: Path, git: GitClient, wm: WorkspaceManager
    ) -> None:
        before = capture_fingerprint(clean_repo, git)

        wt, before_fp = wm.prepare(clean_repo, "run_clean_test")

        # Modify the worktree (simulate agent work)
        (wt / "hello.py").write_text("print('patched')\n")

        patch = wm.export_patch(wt)
        assert "patched" in patch or len(patch) > 0

        after_fp = wm.cleanup(clean_repo, wt)
        wm.verify_source_unchanged(before, after_fp)

        # Also verify worktree is gone
        assert not wt.exists()

    def test_patch_can_be_applied_to_new_worktree(
        self, clean_repo: Path, git: GitClient, wm: WorkspaceManager
    ) -> None:
        wt1, _ = wm.prepare(clean_repo, "run_patch_a")
        (wt1 / "hello.py").write_text("print('patched')\n")
        patch = wm.export_patch(wt1)
        wm.cleanup(clean_repo, wt1)

        # Apply patch to a second fresh worktree
        wt2, _ = wm.prepare(clean_repo, "run_patch_b")
        # Write patch to file and apply
        patch_file = wt2 / "changes.diff"
        patch_file.write_text(patch)
        subprocess.run(
            ["git", "apply", "changes.diff"], cwd=wt2, capture_output=True, check=True
        )
        patched_content = (wt2 / "hello.py").read_text()
        assert patched_content == "print('patched')\n"

        wm.cleanup(clean_repo, wt2)


# -- dirty repo tests ------------------------------------------------------


class TestDirtyRepo:
    def test_dirty_repo_unchanged(
        self, dirty_repo: Path, git: GitClient, wm: WorkspaceManager
    ) -> None:
        before = capture_fingerprint(dirty_repo, git)
        original_content = (dirty_repo / "hello.py").read_text()

        wt, before_fp = wm.prepare(dirty_repo, "run_dirty")
        (wt / "hello.py").write_text("print('agent_changed_in_worktree')\n")
        _ = wm.export_patch(wt)
        after_fp = wm.cleanup(dirty_repo, wt)

        wm.verify_source_unchanged(before, after_fp)
        # Original dirty content is preserved
        assert (dirty_repo / "hello.py").read_text() == original_content

    def test_worktree_has_clean_snapshot_not_dirty(
        self, dirty_repo: Path, git: GitClient, wm: WorkspaceManager
    ) -> None:
        """The worktree is based on HEAD, so dirty changes are NOT propagated."""
        wt, _ = wm.prepare(dirty_repo, "run_snapshot")
        # HEAD version is "print('hello')", not the dirty "print('modified')"
        wt_content = (wt / "hello.py").read_text()
        assert wt_content == "print('hello')\n"
        wm.cleanup(dirty_repo, wt)


# -- untracked repo tests --------------------------------------------------


class TestUntrackedRepo:
    def test_untracked_repo_unchanged(
        self, untracked_repo: Path, git: GitClient, wm: WorkspaceManager
    ) -> None:
        before = capture_fingerprint(untracked_repo, git)
        assert "unrelated.log" in before.untracked_files

        wt, before_fp = wm.prepare(untracked_repo, "run_untracked")
        (wt / "hello.py").write_text("print('patched')\n")
        _ = wm.export_patch(wt)
        after_fp = wm.cleanup(untracked_repo, wt)

        wm.verify_source_unchanged(before, after_fp)
        # Untracked file still exists
        assert (untracked_repo / "unrelated.log").exists()
        assert (untracked_repo / "unrelated.log").read_text() == "debug info\n"


# -- error / edge-case tests -----------------------------------------------


class TestWorkspaceEdgeCases:
    def test_not_a_git_repo_raises(self, tmp_path: Path, wm: WorkspaceManager) -> None:
        bogus = tmp_path / "not_repo"
        bogus.mkdir()
        with pytest.raises(WorkspaceError, match="Not a git repository"):
            wm.prepare(bogus, "run_bogus")

    def test_cleanup_idempotent(self, clean_repo: Path, wm: WorkspaceManager) -> None:
        """Calling cleanup on an already-cleaned worktree should not crash."""
        wt, _ = wm.prepare(clean_repo, "run_idem")
        wm.cleanup(clean_repo, wt)
        # Second cleanup should be a no-op (or handle gracefully)
        wm.cleanup(clean_repo, wt)

    def test_patch_export_from_unmodified_worktree_is_empty(
        self, clean_repo: Path, wm: WorkspaceManager
    ) -> None:
        wt, _ = wm.prepare(clean_repo, "run_empty_patch")
        patch = wm.export_patch(wt)
        assert patch.strip() == ""
        wm.cleanup(clean_repo, wt)


# -- invariant tests -------------------------------------------------------


class TestInvariantEnforcement:
    def test_fingerprint_mismatch_detected(
        self, clean_repo: Path, git: GitClient
    ) -> None:
        """Deliberately modifying original repo after fingerprint triggers error."""
        before = capture_fingerprint(clean_repo, git)
        (clean_repo / "hello.py").write_text("tampered\n")
        after = capture_fingerprint(clean_repo, git)
        with pytest.raises(InvariantViolationError):
            before.assert_unchanged(after)

    def test_worktree_lifecycle_many_times(
        self, clean_repo: Path, git: GitClient, wm: WorkspaceManager
    ) -> None:
        """Running full prepare→modify→cleanup loop 5 times leaves source intact."""
        before = capture_fingerprint(clean_repo, git)
        for i in range(5):
            wt, _ = wm.prepare(clean_repo, f"run_loop_{i}")
            (wt / "hello.py").write_text(f"print('iteration_{i}')\n")
            wm.cleanup(clean_repo, wt)
        after = capture_fingerprint(clean_repo, git)
        before.assert_unchanged(after)
