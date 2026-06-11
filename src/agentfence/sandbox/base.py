"""Abstract SandboxBackend and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ResourceSample:
    """A single resource usage snapshot."""

    timestamp: float
    cpu_percent: float = 0.0
    memory_bytes: int = 0
    memory_limit_bytes: int = 0
    network_rx_bytes: int = 0
    network_tx_bytes: int = 0
    block_read_bytes: int = 0
    block_write_bytes: int = 0
    pids_current: int = 0


@dataclass
class RunResult:
    """Result of running a command inside the sandbox."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    resource_samples: list[ResourceSample] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass
class SandboxConfig:
    """Configuration for a single sandbox execution."""

    image: str
    command: Sequence[str]
    workspace: Path
    run_id: str
    network: str = "none"
    cpus: float = 2.0
    memory: str = "4g"
    pids_limit: int = 256
    timeout_seconds: int = 1800
    env_allow: list[str] = field(default_factory=list)
    read_only_rootfs: bool = True


class SandboxBackend(ABC):
    """Abstract interface for isolated execution backends."""

    @abstractmethod
    def run(self, config: SandboxConfig) -> RunResult:
        """Execute the command inside the sandbox and return the result."""
        ...

    @abstractmethod
    def check_available(self) -> bool:
        """Return True if this backend can be used."""
        ...
