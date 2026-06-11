"""Unit tests for GitClient."""

from __future__ import annotations

from pathlib import Path

import pytest

from patchguard.exceptions import WorkspaceError
from patchguard.workspace.git_client import GitClient


class TestGitClientErrors:
    def test_not_a_git_repo(self, tmp_path: Path) -> None:
        git = GitClient()
        assert not git.is_git_repo(tmp_path)

    def test_assert_git_repo_raises(self, tmp_path: Path) -> None:
        git = GitClient()
        with pytest.raises(WorkspaceError, match="Not a git repository"):
            git.assert_git_repo(tmp_path)

    def test_bogus_binary(self) -> None:
        git = GitClient(git_bin="/nonexistent/git-xyz")
        with pytest.raises(WorkspaceError):
            git._run(Path("/"), ["version"])

    def test_failed_command(self, tmp_path: Path) -> None:
        git = GitClient()
        with pytest.raises(WorkspaceError, match="git.*failed"):
            git._run(tmp_path, ["rev-parse", "does-not-exist"])


class TestGitClientOnRepo:
    """Tests that need a real git repo (tmp_path with git init)."""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        import subprocess

        r = tmp_path / "repo"
        r.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=r, capture_output=True, check=True)
        cmd = ["git", "config", "user.email", "test@test.test"]
        subprocess.run(cmd, cwd=r, capture_output=True, check=True)
        cmd = ["git", "config", "user.name", "Test"]
        subprocess.run(cmd, cwd=r, capture_output=True, check=True)
        (r / "hello.py").write_text("print('hello')")
        cmd = ["git", "add", "hello.py"]
        subprocess.run(cmd, cwd=r, capture_output=True, check=True)
        cmd = ["git", "commit", "-m", "initial"]
        subprocess.run(cmd, cwd=r, capture_output=True, check=True)
        return r

    def test_is_git_repo(self, repo: Path) -> None:
        git = GitClient()
        assert git.is_git_repo(repo)

    def test_rev_parse_toplevel(self, repo: Path) -> None:
        git = GitClient()
        top = git.rev_parse_toplevel(repo)
        assert top == repo

    def test_head_sha_is_40_chars(self, repo: Path) -> None:
        git = GitClient()
        sha = git.head_sha(repo)
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_is_dirty_clean_repo(self, repo: Path) -> None:
        git = GitClient()
        assert not git.is_dirty(repo)

    def test_is_dirty_after_change(self, repo: Path) -> None:
        git = GitClient()
        (repo / "hello.py").write_text("print('world')")
        assert git.is_dirty(repo)

    def test_status_porcelain_lines_clean(self, repo: Path) -> None:
        git = GitClient()
        lines = git.status_porcelain_lines(repo)
        assert lines == []

    def test_diff_head_clean(self, repo: Path) -> None:
        git = GitClient()
        assert git.diff_head(repo) == ""

    def test_untracked_files_empty(self, repo: Path) -> None:
        git = GitClient()
        assert git.untracked_files(repo) == []

    def test_untracked_files_present(self, repo: Path) -> None:
        git = GitClient()
        (repo / "new_file.txt").write_text("untracked")
        files = git.untracked_files(repo)
        assert "new_file.txt" in files

    def test_worktree_add_and_remove(self, repo: Path) -> None:
        git = GitClient()
        head = git.head_sha(repo)
        wt_path = repo.parent / "test-worktree"

        git.worktree_add_detach(repo, wt_path, head)
        assert (wt_path / "hello.py").exists()

        git.worktree_remove(repo, wt_path, force=True)
        git.worktree_prune(repo)
        assert not wt_path.exists()

    def test_diff_worktree_after_modification(self, repo: Path) -> None:
        git = GitClient()
        head = git.head_sha(repo)
        wt_path = repo.parent / "test-worktree-2"

        git.worktree_add_detach(repo, wt_path, head)
        (wt_path / "hello.py").write_text("print('modified')")
        diff = git.diff_worktree(wt_path)
        assert "modified" in diff or len(diff) > 0

        git.worktree_remove(repo, wt_path, force=True)
        git.worktree_prune(repo)
