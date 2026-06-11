"""Abstract AgentAdapter and launch specification."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdapterLaunchSpec:
    """The command and environment to execute inside the sandbox."""

    argv: Sequence[str]
    env: dict[str, str]
    capability_tier: str
    redacted_argv: Sequence[str]


class AgentAdapter(ABC):
    """Abstract adapter for preparing an agent command for sandbox execution."""

    name: str
    version: str

    @abstractmethod
    def build_launch_spec(
        self,
        *,
        workspace: Path,
        user_command: Sequence[str],
        run_id: str,
    ) -> AdapterLaunchSpec:
        """Produce the argv and environment for the agent inside the sandbox."""
        ...
