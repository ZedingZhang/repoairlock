"""ReplayService — validates and replays a run's patch without re-invoking the agent.

INV-010: Replay must not rerun the agent unless explicitly requested
by a distinct rerun command.
"""

from __future__ import annotations

from pathlib import Path

from agentfence.artifacts.integrity import sha256_file
from agentfence.exceptions import ConfigurationError, WorkspaceError
from agentfence.models.manifest import Manifest
from agentfence.workspace.git_client import GitClient
from agentfence.workspace.manager import WorkspaceManager


class ReplayService:
    """Replays a previously exported patch to verify reproducibility.

    Does NOT re-invoke the agent. Only validates artifacts and
    applies the recorded patch to a fresh worktree.
    """

    def __init__(self, *, runs_dir: Path | None = None) -> None:
        from agentfence.constants import DEFAULT_RUNS_DIR
        self._runs_dir = runs_dir or DEFAULT_RUNS_DIR
        self._git = GitClient()

    def replay(
        self,
        run_id: str,
        *,
        repo_override: Path | None = None,
    ) -> ReplayResult:
        """Replay a run's patch. Returns structured result.

        Args:
            run_id: The run to replay.
            repo_override: Override the source repo path (useful if moved).
        """
        run_dir = self._runs_dir / run_id
        if not run_dir.exists():
            raise ConfigurationError(f"Run not found: {run_id}")

        # 1. Load manifest
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            raise ConfigurationError(f"Manifest not found for run: {run_id}")
        try:
            manifest = Manifest.model_validate_json(manifest_path.read_text())
        except Exception as e:
            raise ConfigurationError(
                f"Failed to parse manifest for run {run_id}: {e}"
            ) from e
        if manifest.schema_version != "1.0":
            raise ConfigurationError(
                f"Unknown schema version: {manifest.schema_version}"
            )

        # 2. Validate patch integrity (before needing source repo)
        patch_path = run_dir / "patch.diff"
        if not patch_path.exists():
            raise ConfigurationError("patch.diff not found — nothing to replay")
        patch_actual = sha256_file(patch_path)
        patch_expected = manifest.integrity.patch_diff
        if patch_expected and patch_actual != patch_expected:
            raise ConfigurationError(
                f"Patch integrity check FAILED.\n"
                f"  Expected: {patch_expected}\n"
                f"  Actual:   {patch_actual}\n"
                f"The patch has been modified or corrupted."
            )

        # 3. Determine source repo
        repo_path = repo_override
        if repo_path is None:
            repo_path = Path(manifest.repo.source_path)
        if not repo_path.exists():
            raise ConfigurationError(
                f"Source repo not found: {repo_path}. "
                "Use --repo to specify an alternate path."
            )

        # 4. Create temporary worktree from original repo HEAD
        head_sha = manifest.repo.head_sha
        if not head_sha:
            head_sha = self._git.head_sha(repo_path)

        wm = WorkspaceManager(git=self._git)
        wt_path, _ = wm.prepare(repo_path, f"replay-{run_id}", ref=head_sha)
        try:
            # 5. Apply patch
            import subprocess
            patch_content = patch_path.read_text()
            if patch_content.strip():
                result = subprocess.run(
                    ["git", "apply", "--binary"],
                    cwd=wt_path,
                    input=patch_content,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise WorkspaceError(
                        f"Failed to apply patch: {result.stderr.strip()}"
                    )

            # 6. Verify the applied patch matches stored patch
            new_diff = self._git.diff_worktree(wt_path)
            patch_applied = bool(new_diff.strip())
            patch_match = _normalize_patch(new_diff) == _normalize_patch(patch_content)

            return ReplayResult(
                run_id=run_id,
                integrity_ok=True,
                patch_applied=patch_applied,
                patch_match=patch_match,
                head_sha=head_sha,
                manifest_status=str(manifest.status.value),
            )
        finally:
            wm.cleanup(repo_path, wt_path)


class ReplayResult:
    def __init__(
        self,
        *,
        run_id: str,
        integrity_ok: bool,
        patch_applied: bool,
        patch_match: bool,
        head_sha: str,
        manifest_status: str,
    ) -> None:
        self.run_id = run_id
        self.integrity_ok = integrity_ok
        self.patch_applied = patch_applied
        self.patch_match = patch_match
        self.head_sha = head_sha
        self.manifest_status = manifest_status

    @property
    def success(self) -> bool:
        return self.integrity_ok and self.patch_match


def _normalize_patch(patch: str) -> str:
    """Normalize only insignificant trailing whitespace for replay comparison."""
    return patch.strip()
