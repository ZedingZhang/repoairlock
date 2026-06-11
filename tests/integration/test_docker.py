"""Integration tests for DockerSandbox.

These tests require a working Docker daemon.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from repoairlock.exceptions import EnvironmentError
from repoairlock.sandbox.base import SandboxConfig
from repoairlock.sandbox.docker import DockerBackend

_DOCKER_AVAILABLE = shutil.which("docker") is not None


def _check_docker() -> bool:
    import os as _os
    if _os.environ.get("CI") and _os.environ.get("SKIP_DOCKER_MOUNT_TESTS", "1") == "1":
        return False
    if not _DOCKER_AVAILABLE:
        return False
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, check=False, timeout=5
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _has_image(name: str) -> bool:
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", name],
            capture_output=True, check=False, timeout=5,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


docker_required = pytest.mark.skipif(
    not _check_docker(),
    reason="Docker daemon not available",
)


class TestDockerBackendAvailability:
    def test_check_available_no_docker_binary(self, monkeypatch) -> None:
        """When PATH has no docker, check_available returns False."""
        # We can't easily remove docker from PATH, so test with bogus binary.
        backend = DockerBackend(docker_bin="/nonexistent/docker-xyz")
        assert not backend.check_available()

    def test_assert_available_raises_no_docker(self) -> None:
        backend = DockerBackend(docker_bin="/nonexistent/docker-xyz")
        with pytest.raises(EnvironmentError, match="Docker CLI not found"):
            backend.assert_available()


@docker_required
class TestDockerRun:
    @pytest.fixture
    def backend(self) -> DockerBackend:
        return DockerBackend()

    @pytest.fixture
    def tmp_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "test.txt").write_text("hello docker")
        return ws

    def test_run_simple_command(self, backend: DockerBackend, tmp_workspace: Path) -> None:
        # Ensure alpine image is available
        if not _has_image("alpine:latest"):
            subprocess.run(
                ["docker", "pull", "alpine:latest"],
                capture_output=True, check=False, timeout=120,
            )

        config = SandboxConfig(
            image="alpine:latest",
            command=["echo", "-n", "hello_from_docker"],
            workspace=tmp_workspace,
            run_id="itest_run_simple",
            timeout_seconds=30,
        )
        result = backend.run(config)
        assert result.exit_code == 0
        assert "hello_from_docker" in result.stdout
        assert not result.timed_out

    def test_run_failing_command(self, backend: DockerBackend, tmp_workspace: Path) -> None:
        if not _has_image("alpine:latest"):
            subprocess.run(
                ["docker", "pull", "alpine:latest"],
                capture_output=True, check=False, timeout=120,
            )

        config = SandboxConfig(
            image="alpine:latest",
            command=["sh", "-c", "exit 42"],
            workspace=tmp_workspace,
            run_id="itest_run_fail",
            timeout_seconds=30,
        )
        result = backend.run(config)
        assert result.exit_code == 42
        assert not result.timed_out

    def test_workspace_is_mounted(self, backend: DockerBackend, tmp_workspace: Path) -> None:
        if not _has_image("alpine:latest"):
            subprocess.run(
                ["docker", "pull", "alpine:latest"],
                capture_output=True, check=False, timeout=120,
            )

        config = SandboxConfig(
            image="alpine:latest",
            command=["cat", "/workspace/test.txt"],
            workspace=tmp_workspace,
            run_id="itest_ws_mount",
            timeout_seconds=30,
        )
        result = backend.run(config)
        assert result.exit_code == 0
        assert "hello docker" in result.stdout

    def test_container_cleaned_up(self, backend: DockerBackend, tmp_workspace: Path) -> None:
        if not _has_image("alpine:latest"):
            subprocess.run(
                ["docker", "pull", "alpine:latest"],
                capture_output=True, check=False, timeout=120,
            )

        config = SandboxConfig(
            image="alpine:latest",
            command=["echo", "done"],
            workspace=tmp_workspace,
            run_id="itest_cleanup",
            timeout_seconds=30,
        )
        result = backend.run(config)
        assert result.exit_code == 0
        # Container should be removed after run
        cmd = [
            "docker", "ps", "-a",
            "--filter", "name=repoairlock-itest_cleanup",
            "--format", "{{.ID}}",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert r.stdout.strip() == ""
