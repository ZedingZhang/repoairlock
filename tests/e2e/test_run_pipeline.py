"""End-to-end tests for the full Tier 0 pipeline.

These tests require Docker daemon to be available.
"""

from __future__ import annotations

import json
import os as _os
import shutil
import subprocess
from pathlib import Path

import pytest

from repoairlock.core.orchestrator import RunConfig, RunOrchestrator
from repoairlock.workspace.manager import WorkspaceManager

_DOCKER_OK = False
_CI_SKIP = _os.environ.get("CI") and _os.environ.get("SKIP_DOCKER_MOUNT_TESTS", "1") == "1"
if not _CI_SKIP and shutil.which("docker"):
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, check=False, timeout=5
        )
        _DOCKER_OK = r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

docker_required = pytest.mark.skipif(not _DOCKER_OK, reason="Docker daemon not available")


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test"],
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path, capture_output=True, check=True,
    )


def _has_image(name: str) -> bool:
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", name],
            capture_output=True, check=False, timeout=5,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _ensure_image(name: str) -> None:
    if not _has_image(name):
        subprocess.run(
            ["docker", "pull", name], capture_output=True, check=False, timeout=120
        )


def _dump_diagnostics(run_dir: Path) -> str:
    """Collect diagnostic output from a failed run."""
    lines: list[str] = []
    for fname in ("stdout.log", "stderr.log"):
        p = run_dir / fname
        if p.exists():
            lines.append(f"--- {fname} ---")
            lines.append(p.read_text()[:2000])
    return "\n".join(lines)


def _diag_worktree(worktree: Path, worktree_name: str) -> str:
    """Diagnose a worktree path from the host side."""
    lines = [f"=== host diag: {worktree_name} ==="]
    lines.append(f"worktree path: {worktree}")
    lines.append(f"exists: {worktree.exists()}")
    if worktree.exists():
        import os as _os2
        lines.append(f"stat: {_os2.stat(str(worktree))}")
        files = list(worktree.iterdir())
        lines.append(f"contents: {[f.name for f in files]}")
        hello = worktree / "hello.py"
        if hello.exists():
            lines.append(f"hello.py stat: {_os2.stat(str(hello))}")
            lines.append(f"hello.py content: {hello.read_text()}")
    return "\n".join(lines)


def _diag_container(worktree: Path, image: str) -> str:
    """Run a diagnostic container to inspect the mounted workspace."""
    cmd = (
        "echo '=== id ===' && id && "
        "echo '=== ls -la /workspace ===' && ls -la /workspace && "
        "echo '=== stat /workspace/hello.py ===' && stat /workspace/hello.py 2>&1 && "
        "echo '=== cat /workspace/hello.py ===' && cat /workspace/hello.py 2>&1"
    )
    try:
        r = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network", "none",
                "--mount", f"type=bind,src={worktree},dst=/workspace",
                "--workdir", "/workspace",
                image,
                "sh", "-c", cmd,
            ],
            capture_output=True, text=True, check=False, timeout=30,
        )
        return f"container diag stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    except Exception as e:
        return f"container diag error: {e}"


@pytest.fixture
def image() -> str:
    _ensure_image("alpine:latest")
    return "alpine:latest"


@pytest.fixture
def clean_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "test-repo"
    _init_repo(repo)
    (repo / "hello.py").write_text('def greet():\n    return "Hello, World!"\n')
    subprocess.run(["git", "add", "hello.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    return repo


@docker_required
class TestE2EPipeline:
    def test_success_agent_produces_patch(
        self, clean_repo: Path, image: str
    ) -> None:
        """A successful agent run produces manifest, events, patch, and leaves source intact."""
        original_content = (clean_repo / "hello.py").read_text()

        config = RunConfig(
            repo=clean_repo,
            agent_command=[
                "sh", "-c",
                "cat /workspace/hello.py > /tmp/orig && "
                "echo 'print(\"Hello, PatchGuard!\")' > /workspace/hello.py",
            ],
            image=image,
            timeout=60,
            network="none",
        )

        orchestrator = RunOrchestrator()
        result = orchestrator.execute(config)

        if result.exit_code != 0:
            diag = _dump_diagnostics(result.run_dir)
            pytest.fail(
                f"Expected exit 0, got {result.exit_code}\n{diag}"
            )

        assert result.status.value == "completed"
        assert result.exit_code == 0
        assert result.patch_bytes > 0

        assert (clean_repo / "hello.py").read_text() == original_content

        run_dir = result.run_dir
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "events.jsonl").exists()
        assert (run_dir / "patch.diff").exists()
        assert (run_dir / "stdout.log").exists()

        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert manifest["run_id"] == result.run_id

    def test_success_agent_with_shell_command(
        self, clean_repo: Path, image: str
    ) -> None:
        """Run a simple echo command via Docker to verify the pipeline works."""
        original_content = (clean_repo / "hello.py").read_text()

        config = RunConfig(
            repo=clean_repo,
            agent_command=["sh", "-c", "echo modified > /workspace/hello.py"],
            image=image,
            timeout=30,
            network="none",
        )

        orchestrator = RunOrchestrator()
        result = orchestrator.execute(config)

        if result.exit_code != 0:
            diag = _dump_diagnostics(result.run_dir)
            pytest.fail(f"Expected exit 0, got {result.exit_code}\n{diag}")

        assert result.exit_code == 0
        assert result.patch_bytes > 0
        assert (clean_repo / "hello.py").read_text() == original_content

        patch = (result.run_dir / "patch.diff").read_text()
        assert "modified" in patch

    def test_failure_agent_produces_artifacts(
        self, clean_repo: Path, image: str
    ) -> None:
        """A failing agent still produces minimum artifacts."""
        original_content = (clean_repo / "hello.py").read_text()

        config = RunConfig(
            repo=clean_repo,
            agent_command=["sh", "-c", "echo 'error!' >&2; exit 1"],
            image=image,
            timeout=30,
            network="none",
        )

        orchestrator = RunOrchestrator()
        result = orchestrator.execute(config)

        assert result.exit_code == 1

        run_dir = result.run_dir
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "events.jsonl").exists()
        assert (run_dir / "stderr.log").exists()

        stderr = (run_dir / "stderr.log").read_text()
        assert "error" in stderr
        assert (clean_repo / "hello.py").read_text() == original_content

    def test_agent_run_isolates_from_source(
        self, clean_repo: Path, image: str
    ) -> None:
        """Agent modifications happen in the worktree, not the source repo."""
        original = (clean_repo / "hello.py").read_text()

        config = RunConfig(
            repo=clean_repo,
            agent_command=["sh", "-c", "echo 'hacked' > /workspace/hello.py"],
            image=image,
            timeout=30,
            network="none",
        )
        orchestrator = RunOrchestrator()
        result = orchestrator.execute(config)

        if result.exit_code != 0:
            diag = _dump_diagnostics(result.run_dir)
            pytest.fail(f"Expected exit 0, got {result.exit_code}\n{diag}")

        assert result.exit_code == 0
        assert (clean_repo / "hello.py").read_text() == original

        patch = (result.run_dir / "patch.diff").read_text()
        assert "hacked" in patch


@docker_required
class TestE2EDiagnostics:
    """Diagnosis tests to isolate binding and permission failures."""

    def test_raw_docker_bind_mount_write(self, tmp_path: Path, image: str) -> None:
        """Level 1: raw docker --mount write (no git, no orchestrator)."""
        ws = tmp_path / "diag-ws"
        ws.mkdir()
        (ws / "hello.py").write_text("original\n")

        r = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network", "none",
                "--mount", f"type=bind,src={ws},dst=/workspace",
                "--workdir", "/workspace",
                image,
                "sh", "-c", "echo modified > /workspace/hello.py",
            ],
            capture_output=True, text=True, check=False, timeout=30,
        )
        assert r.returncode == 0, f"raw docker failed: exit={r.returncode} stderr={r.stderr}"
        assert (ws / "hello.py").read_text().strip() == "modified"

    def test_workspace_manager_mount_write(
        self, clean_repo: Path, image: str
    ) -> None:
        """Level 2: WorkspaceManager worktree + raw docker mount write."""
        wm = WorkspaceManager()
        wt, _ = wm.prepare(clean_repo, "diag-wm")
        try:
            r = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--network", "none",
                    "--mount", f"type=bind,src={wt},dst=/workspace",
                    "--workdir", "/workspace",
                    image,
                    "sh", "-c", "echo modified > /workspace/hello.py",
                ],
                capture_output=True, text=True, check=False, timeout=30,
            )
            assert r.returncode == 0, (
                f"WM + docker failed: exit={r.returncode}\n"
                f"worktree={wt}\nstderr={r.stderr}\nstdout={r.stdout}"
            )
            assert (wt / "hello.py").read_text().strip() == "modified"
        finally:
            wm.cleanup(clean_repo, wt)

    def test_orchestrator_simple_write(
        self, clean_repo: Path, image: str
    ) -> None:
        """Level 3: full orchestrator with a minimal write command."""
        config = RunConfig(
            repo=clean_repo,
            agent_command=["sh", "-c", "echo 'diag-test' > /workspace/orch_test.txt"],
            image=image,
            timeout=30,
            network="none",
        )
        orchestrator = RunOrchestrator()
        result = orchestrator.execute(config)
        assert result.exit_code == 0, (
            f"orchestrator failed: exit={result.exit_code} status={result.status.value}\n"
            f"{_dump_diagnostics(result.run_dir)}"
        )


@docker_required
class TestE2EListRuns:
    def test_list_after_run(self, clean_repo: Path, image: str) -> None:
        """After running, list command should show the run."""
        config = RunConfig(
            repo=clean_repo,
            agent_command=["echo", "hello"],
            image=image,
            timeout=30,
        )
        orchestrator = RunOrchestrator()
        result = orchestrator.execute(config)

        from repoairlock.constants import DEFAULT_RUNS_DIR
        manifests = list(DEFAULT_RUNS_DIR.glob("*/manifest.json"))
        run_ids = []
        for mf in manifests:
            try:
                data = json.loads(mf.read_text())
                run_ids.append(data.get("run_id", ""))
            except (json.JSONDecodeError, OSError):
                pass
        assert result.run_id in run_ids
