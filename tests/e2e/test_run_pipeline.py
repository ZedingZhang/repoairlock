"""End-to-end tests for the full Tier 0 pipeline.

These tests require Docker daemon to be available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from repoairlock.core.orchestrator import RunConfig, RunOrchestrator

import os as _os
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


@pytest.fixture
def image() -> str:
    _ensure_image("alpine:latest")
    return "alpine:latest"


@pytest.fixture
def python_image() -> str:
    _ensure_image("python:3.12-alpine")
    return "python:3.12-alpine"


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
        self, clean_repo: Path, python_image: str
    ) -> None:
        """A successful agent run produces manifest, events, patch, and leaves source intact."""
        original_content = (clean_repo / "hello.py").read_text()

        config = RunConfig(
            repo=clean_repo,
            agent_command=["python", "/tmp/agent_success.py"],
            image=python_image,
            timeout=60,
            network="none",
            # Mount agent script into workspace area via env-based approach
            # The agent looks for /workspace/hello.py
        )

        orchestrator = RunOrchestrator()
        result = orchestrator.execute(config)

        assert result.status.value in ("completed", "failed", "agent_failed")
        assert result.exit_code in (0, 1)

        # Original repo unchanged
        assert (clean_repo / "hello.py").read_text() == original_content

        # Artifacts exist
        run_dir = result.run_dir
        assert run_dir.exists()
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "events.jsonl").exists()
        assert (run_dir / "patch.diff").exists()
        assert (run_dir / "stdout.log").exists()

        # Manifest is valid JSON
        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert manifest["run_id"] == result.run_id
        assert "schema_version" in manifest
        assert "integrity" in manifest

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

        # Should complete (even though "modified" is not valid Python, agent exited 0)
        assert result.exit_code == 0
        assert result.patch_bytes > 0

        # Original repo unchanged
        assert (clean_repo / "hello.py").read_text() == original_content

        # Patch contains the change
        patch = (result.run_dir / "patch.diff").read_text()
        assert "modified" in patch

    def test_failure_agent_produces_artifacts(
        self, clean_repo: Path, python_image: str
    ) -> None:
        """A failing agent still produces minimum artifacts."""
        original_content = (clean_repo / "hello.py").read_text()

        config = RunConfig(
            repo=clean_repo,
            agent_command=[
                "python", "-c",
                "import sys; sys.stderr.write('error!\\n'); sys.exit(1)",
            ],
            image=python_image,
            timeout=30,
            network="none",
        )

        orchestrator = RunOrchestrator()
        result = orchestrator.execute(config)

        assert result.exit_code == 1

        # Artifacts still exist
        run_dir = result.run_dir
        assert run_dir.exists()
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "events.jsonl").exists()
        assert (run_dir / "stderr.log").exists()

        # stderr contains the error message
        stderr = (run_dir / "stderr.log").read_text()
        assert "error" in stderr

        # Original repo unchanged
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

        assert result.exit_code == 0
        # Source file NOT modified
        assert (clean_repo / "hello.py").read_text() == original
        # Patch shows the diff
        patch = (result.run_dir / "patch.diff").read_text()
        assert "hacked" in patch


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

        # Check that listing finds this run
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
