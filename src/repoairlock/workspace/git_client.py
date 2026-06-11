"""Thin wrapper around git CLI using subprocess argv lists — no shell."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from repoairlock.exceptions import WorkspaceError

_GIT_BIN = "git"


class GitClient:
    """Minimal git CLI wrapper. All commands use argv lists, never shell strings."""

    def __init__(self, git_bin: str = _GIT_BIN) -> None:
        self._git = git_bin

    # -- queries -----------------------------------------------------------

    def rev_parse(self, repo: Path, ref: str) -> str:
        """Return the full SHA for `ref` (e.g. HEAD)."""
        return self._run(repo, ["rev-parse", ref]).stdout.strip()

    def rev_parse_toplevel(self, repo: Path) -> Path:
        """Return the absolute top-level directory of the repo."""
        out = self._run(repo, ["rev-parse", "--show-toplevel"]).stdout.strip()
        return Path(out)

    def head_sha(self, repo: Path) -> str:
        return self.rev_parse(repo, "HEAD")

    def status_porcelain(self, repo: Path) -> str:
        """Return `git status --porcelain=v1 -z` output."""
        return self._run(repo, ["status", "--porcelain=v1", "-z"]).stdout

    def status_porcelain_lines(self, repo: Path) -> list[str]:
        """Return porcelain status entries split by null byte."""
        raw = self.status_porcelain(repo)
        if not raw.strip("\0"):
            return []
        return raw.rstrip("\0").split("\0")

    def diff_head(self, repo: Path) -> str:
        """Return `git diff HEAD` for tracked file changes."""
        return self._run(repo, ["diff", "HEAD"]).stdout

    def diff_head_stat(self, repo: Path) -> str:
        """Return `git diff HEAD --stat` summary."""
        return self._run(repo, ["diff", "HEAD", "--stat"]).stdout

    def untracked_files(self, repo: Path) -> list[str]:
        """Return a sorted list of untracked file paths relative to repo root."""
        out = self._run(
            repo, ["ls-files", "--others", "--exclude-standard", "-z"]
        ).stdout
        if not out.strip("\0"):
            return []
        return sorted(p for p in out.rstrip("\0").split("\0") if p)

    def diff_worktree(self, worktree: Path) -> str:
        """Return a patch for tracked and untracked worktree changes."""
        tracked = self._run(worktree, ["diff", "HEAD", "--binary"]).stdout
        untracked_patches: list[str] = []
        for rel_path in self.untracked_files(worktree):
            result = self._run_allow_returncodes(
                worktree,
                ["diff", "--no-index", "--binary", "--", "/dev/null", rel_path],
                allowed_returncodes={0, 1},
            )
            if result.stdout.strip():
                untracked_patches.append(result.stdout)

        parts = [tracked, *untracked_patches]
        return "".join(_ensure_trailing_newline(p) for p in parts if p)

    # -- worktree operations -----------------------------------------------

    def worktree_add_detach(self, repo: Path, target: Path, ref: str) -> None:
        """Create a detached worktree at `target` from `ref`."""
        self._run(
            repo,
            ["worktree", "add", "--detach", str(target), ref],
        )

    def worktree_remove(self, repo: Path, target: Path, *, force: bool = True) -> None:
        """Remove a linked worktree."""
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(target))
        self._run(repo, args)

    def worktree_prune(self, repo: Path) -> None:
        """Prune stale worktree metadata."""
        self._run(repo, ["worktree", "prune"])

    def worktree_list_porcelain(self, repo: Path) -> list[dict[str, str]]:
        """Return parsed `git worktree list --porcelain` as a list of dicts."""
        out = self._run(repo, ["worktree", "list", "--porcelain"]).stdout
        entries: list[dict[str, str]] = []
        current: dict[str, str] = {}
        for line in out.split("\n"):
            line = line.strip()
            if not line:
                if current:
                    entries.append(current)
                    current = {}
                continue
            if " " in line:
                key, _, val = line.partition(" ")
                current[key] = val
        if current:
            entries.append(current)
        return entries

    # -- repo validation ---------------------------------------------------

    def is_git_repo(self, path: Path) -> bool:
        """Check whether `path` is inside a git working tree."""
        try:
            self.rev_parse_toplevel(path)
            return True
        except WorkspaceError:
            return False

    def assert_git_repo(self, path: Path) -> Path:
        """Assert that `path` is a git repo and return its top-level."""
        try:
            return self.rev_parse_toplevel(path)
        except WorkspaceError as exc:
            raise WorkspaceError(
                f"Not a git repository: {path}. "
                "RepoAirlock requires a git working tree."
            ) from exc

    def is_dirty(self, repo: Path) -> bool:
        """Return True if the working tree has uncommitted changes."""
        return bool(self.status_porcelain(repo).strip("\0"))

    # -- internal -----------------------------------------------------------

    def _run(self, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        """Run a git command and raise WorkspaceError on failure."""
        return self._run_allow_returncodes(cwd, args, allowed_returncodes={0})

    def _run_allow_returncodes(
        self,
        cwd: Path,
        args: list[str],
        *,
        allowed_returncodes: set[int],
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command and raise WorkspaceError unless its status is allowed."""
        if shutil.which(self._git) is None:
            raise WorkspaceError(f"git binary not found: {self._git}")
        try:
            result = subprocess.run(
                [self._git] + args,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise WorkspaceError(f"git binary not found: {self._git}") from exc
        if result.returncode not in allowed_returncodes:
            raise WorkspaceError(
                f"git {' '.join(args)} failed (exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )
        return result


def _ensure_trailing_newline(text: str) -> str:
    if not text or text.endswith("\n"):
        return text
    return text + "\n"
