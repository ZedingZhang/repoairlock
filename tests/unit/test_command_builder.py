"""Tests for Docker command builder safety constraints."""

from __future__ import annotations

from pathlib import Path

import pytest

from patchguard.exceptions import ConfigurationError
from patchguard.sandbox.base import SandboxConfig
from patchguard.sandbox.command_builder import (
    build_docker_run_args,
    validate_sandbox_config,
)


@pytest.fixture
def base_config() -> SandboxConfig:
    return SandboxConfig(
        image="test-image:latest",
        command=["echo", "hello"],
        workspace=Path("/tmp/ws"),
        run_id="run_test123",
    )


class TestDefaultArguments:
    def test_contains_required_flags(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        assert "run" in args
        assert "--rm" in args
        assert "--read-only" in args
        assert "--network" in args
        idx = args.index("--network")
        assert args[idx + 1] == "none"

    def test_cap_drop_all(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        idx = args.index("--cap-drop")
        assert args[idx + 1] == "ALL"

    def test_security_opt_no_new_privileges(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        idx = args.index("--security-opt")
        assert args[idx + 1] == "no-new-privileges"

    def test_resource_limits_present(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        assert "--cpus" in args
        assert "--memory" in args
        assert "--pids-limit" in args

    def test_workspace_mount(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        # Find the mount argument
        assert "--mount" in args
        mount_idx = args.index("--mount")
        mount_arg = args[mount_idx + 1]
        assert "type=bind" in mount_arg
        assert "dst=/workspace" in mount_arg
        assert "rw" in mount_arg

    def test_workdir_is_workspace(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        idx = args.index("--workdir")
        assert args[idx + 1] == "/workspace"

    def test_tmpfs_mounts(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        tmpfs_indices = [i for i, a in enumerate(args) if a == "--tmpfs"]
        assert len(tmpfs_indices) >= 2

    def test_image_and_command_are_last(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        assert args[-3] == "test-image:latest"
        assert args[-2:] == ["echo", "hello"]


class TestEnvironmentVariables:
    def test_default_env_vars(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        assert "--env" in args
        env_indices = [i for i, a in enumerate(args) if a == "--env"]
        env_values = [args[i + 1] for i in env_indices]
        assert "PATH" in env_values
        assert "HOME=/home/agent" in env_values
        assert any("PATCHGUARD_RUN_ID=" in v for v in env_values)
        assert "PATCHGUARD_WORKSPACE=/workspace" in env_values

    def test_env_allow_passes_variable_names(self, base_config: SandboxConfig) -> None:
        config = SandboxConfig(
            image="img", command=["cmd"], workspace=Path("/ws"),
            run_id="r1", env_allow=["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
        )
        args = build_docker_run_args(config=config)
        env_indices = [i for i, a in enumerate(args) if a == "--env"]
        env_values = [args[i + 1] for i in env_indices]
        assert "ANTHROPIC_API_KEY" in env_values
        assert "OPENAI_API_KEY" in env_values

    def test_run_id_in_environment(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        env_indices = [i for i, a in enumerate(args) if a == "--env"]
        env_values = [args[i + 1] for i in env_indices]
        assert "PATCHGUARD_RUN_ID=run_test123" in env_values


class TestForbiddenOptions:
    def test_privileged_is_absent(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        assert "--privileged" not in args

    def test_no_docker_socket_mount(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        mount_args = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
        for m in mount_args:
            assert "docker.sock" not in m

    def test_no_host_root_mount(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        mount_args = [args[i + 1] for i, a in enumerate(args) if a == "--mount"]
        for m in mount_args:
            # Check for root mount: src=/ alone (followed by , or end of string)
            # The workspace mount is src=/tmp/ws,dst=... which is safe
            src_match = False
            for part in m.split(","):
                if part == "src=/" or part.startswith("src=/,dst="):
                    src_match = True
            assert not src_match, f"Root mount detected in: {m}"

    def test_no_host_network(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        # There is a --network but it's "none", not "host"
        assert "--network" in args
        assert "host" not in args


class TestNetworkOptions:
    def test_default_network_none(self, base_config: SandboxConfig) -> None:
        args = build_docker_run_args(config=base_config)
        network_idx = args.index("--network")
        assert args[network_idx + 1] == "none"

    def test_bridge_network(self, base_config: SandboxConfig) -> None:
        config = SandboxConfig(
            image="img", command=["cmd"], workspace=Path("/ws"),
            run_id="r1", network="bridge",
        )
        args = build_docker_run_args(config=config)
        network_idx = args.index("--network")
        assert args[network_idx + 1] == "bridge"


class TestValidateConfig:
    def test_valid_config_passes(self, base_config: SandboxConfig) -> None:
        validate_sandbox_config(base_config)  # should not raise

    def test_invalid_network_rejected(self, base_config: SandboxConfig) -> None:
        config = SandboxConfig(
            image="img", command=["cmd"], workspace=Path("/ws"),
            run_id="r1", network="egress_only",
        )
        with pytest.raises(ConfigurationError, match="Invalid network mode"):
            validate_sandbox_config(config)

    def test_zero_cpus_rejected(self, base_config: SandboxConfig) -> None:
        config = SandboxConfig(
            image="img", command=["cmd"], workspace=Path("/ws"),
            run_id="r1", cpus=0,
        )
        with pytest.raises(ConfigurationError, match="CPUs must be positive"):
            validate_sandbox_config(config)

    def test_zero_pids_rejected(self, base_config: SandboxConfig) -> None:
        config = SandboxConfig(
            image="img", command=["cmd"], workspace=Path("/ws"),
            run_id="r1", pids_limit=0,
        )
        with pytest.raises(ConfigurationError, match="PIDs limit must be positive"):
            validate_sandbox_config(config)

    def test_read_only_rootfs_default(self, base_config: SandboxConfig) -> None:
        assert base_config.read_only_rootfs is True
        args = build_docker_run_args(config=base_config)
        assert "--read-only" in args
