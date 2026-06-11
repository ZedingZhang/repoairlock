"""Docker command builder — constructs safe docker run argument lists.

Never uses shell strings. All parameters are passed as argv list items.
Forbidden options are rejected at construction time (fail-closed).
"""

from __future__ import annotations

from collections.abc import Sequence

from repoairlock.exceptions import ConfigurationError
from repoairlock.sandbox.base import SandboxConfig

# -- Forbidden items (must be rejected at construction) --------------------

FORBIDDEN_FLAGS = frozenset({"--privileged", "--network host", "--pid host", "--ipc host"})
FORBIDDEN_CAP_ADD = frozenset({"ALL", "SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE"})
FORBIDDEN_MOUNTS = frozenset({"/var/run/docker.sock", "/"})


def _assert_safe_flag(flag: str) -> None:
    if flag in FORBIDDEN_FLAGS:
        raise ConfigurationError(f"Forbidden Docker flag rejected: {flag}")


def _assert_safe_mount(source: str) -> None:
    if source.rstrip("/") in FORBIDDEN_MOUNTS or source == "/":
        raise ConfigurationError(
            f"Forbidden mount source rejected: {source}"
        )
    if source.endswith("docker.sock"):
        raise ConfigurationError(
            f"Docker socket mount rejected: {source}"
        )


def build_docker_run_args(
    *,
    config: SandboxConfig,
    container_name: str | None = None,
    extra_mounts: Sequence[str] | None = None,
) -> list[str]:
    """Build a safe `docker run` argument list.

    The returned list is suitable for passing directly to subprocess.
    It does NOT include the `docker` binary name itself.
    """
    validate_sandbox_config(config)

    name = container_name or f"repoairlock-{config.run_id}"

    args: list[str] = [
        "run",
        "--rm",
        "--name", name,
        "--network", config.network,
        "--cap-drop", "ALL",
        "--cap-add", "DAC_OVERRIDE",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(config.pids_limit),
        "--cpus", str(config.cpus),
        "--memory", config.memory,
    ]

    if config.read_only_rootfs:
        args.extend(["--read-only"])

    # tmpfs mounts
    args.extend([
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=512m",
        "--tmpfs", "/home/agent:rw,nosuid,size=512m",
    ])

    # workspace bind mount
    ws = str(config.workspace)
    args.extend([
        "--mount", f"type=bind,src={ws},dst=/workspace",
        "--workdir", "/workspace",
    ])

    # extra mounts — validate each one
    for mount in (extra_mounts or []):
        # mount format: type=bind,src=<path>,dst=<path>
        if "src=" in mount:
            src_part = [p for p in mount.split(",") if p.startswith("src=")][0]
            src_path = src_part.removeprefix("src=")
            _assert_safe_mount(src_path)
        args.extend(["--mount", mount])

    # environment variables
    args.extend([
        "--env", "PATH",
        "--env", "HOME=/home/agent",
        "--env", f"REPOAIRLOCK_RUN_ID={config.run_id}",
        "--env", "REPOAIRLOCK_WORKSPACE=/workspace",
    ])
    for var in config.env_allow:
        # Only pass the name; Docker resolves it from the host
        args.extend(["--env", var])

    # image and command
    args.append(config.image)
    args.extend(config.command)

    return args


def validate_sandbox_config(config: SandboxConfig) -> None:
    """Validate a SandboxConfig, raising ConfigurationError on forbidden values.

    Basic validation covers parameter ranges. Policy engine validation
    covers security rules (privileged, network, mounts).
    """
    if config.network not in ("none", "bridge"):
        raise ConfigurationError(f"Invalid network mode: {config.network}")
    if config.cpus <= 0:
        raise ConfigurationError("CPUs must be positive")
    if config.pids_limit <= 0:
        raise ConfigurationError("PIDs limit must be positive")

    # Reject forbidden flags
    _assert_safe_flag(f"--network {config.network}")

    # Policy engine validation
    from repoairlock.policy.engine import PolicyEngine
    engine = PolicyEngine.load_defaults()
    results = engine.evaluate_sandbox(
        network=config.network,
        privileged=False,
    )
    if engine.any_denied(results):
        reasons = engine.deny_reasons(results)
        raise ConfigurationError(
            "Policy engine blocked sandbox configuration:\n"
            + "\n".join(f"  - {r}" for r in reasons)
        )
