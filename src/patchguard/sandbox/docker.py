"""DockerSandbox — runs commands in isolated Docker containers."""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import time

from patchguard.exceptions import (
    EnvironmentError,
)
from patchguard.sandbox.base import (
    RunResult,
    SandboxBackend,
    SandboxConfig,
)
from patchguard.sandbox.command_builder import build_docker_run_args
from patchguard.sandbox.resource_monitor import ResourceSampler


class DockerBackend(SandboxBackend):
    """Runs commands inside Docker containers with safe defaults.

    - No network by default
    - Read-only rootfs
    - All capabilities dropped
    - CPU, memory, PID limits
    - Environment variable allowlist
    - Resource sampling
    """

    def __init__(self, docker_bin: str = "docker") -> None:
        self._docker = docker_bin

    def check_available(self) -> bool:
        """Check that Docker CLI and daemon are reachable."""
        if shutil.which(self._docker) is None:
            return False
        try:
            result = subprocess.run(
                [self._docker, "info"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def assert_available(self) -> None:
        """Raise EnvironmentError if Docker is not usable."""
        if shutil.which(self._docker) is None:
            raise EnvironmentError(
                "Docker CLI not found. Install Docker and try again."
            )
        try:
            result = subprocess.run(
                [self._docker, "info"],
                capture_output=True, text=True, check=False, timeout=10,
            )
        except subprocess.TimeoutExpired as exc:
            raise EnvironmentError("Docker daemon is not responding (timeout).") from exc
        if result.returncode != 0:
            raise EnvironmentError(
                f"Docker daemon not reachable:\n{result.stderr.strip()}"
            )

    def run(self, config: SandboxConfig) -> RunResult:
        """Run the command inside a Docker container and return the result."""
        self.assert_available()

        container_name = f"patchguard-{config.run_id}"
        docker_args = build_docker_run_args(
            config=config,
            container_name=container_name,
        )

        # Start resource sampler
        sampler = ResourceSampler(container_name, interval=2.0)

        t0 = time.monotonic()
        timed_out = False

        try:
            # Launch docker run
            proc = subprocess.Popen(
                [self._docker] + docker_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Wait briefly for container to start, then begin sampling
            time.sleep(0.5)
            sampler.start()

            try:
                stdout, stderr = proc.communicate(timeout=config.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_container(self._docker, container_name)
                proc.kill()
                try:
                    stdout, stderr = proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    stdout, stderr = proc.communicate(timeout=5)

        except FileNotFoundError as exc:
            raise EnvironmentError(f"Docker binary not found: {self._docker}") from exc
        finally:
            sampler.stop()
            # Best-effort cleanup
            _rm_container(self._docker, container_name)

        duration_ms = int((time.monotonic() - t0) * 1000)

        return RunResult(
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_ms=duration_ms,
            timed_out=timed_out,
            resource_samples=sampler.samples,
        )


def _kill_container(docker_bin: str, name: str) -> None:
    with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError):
        subprocess.run(
            [docker_bin, "kill", name],
            capture_output=True, check=False, timeout=10,
        )


def _rm_container(docker_bin: str, name: str) -> None:
    with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError):
        subprocess.run(
            [docker_bin, "rm", "-f", name],
            capture_output=True, check=False, timeout=10,
        )
