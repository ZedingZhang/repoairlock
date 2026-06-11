"""CommandAdapter — Tier 0 process wrapper for arbitrary CLI agents."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from patchguard.adapters.base import AdapterLaunchSpec, AgentAdapter
from patchguard.models.enums import CapabilityTier


class CommandAdapter(AgentAdapter):
    """Wraps a raw CLI command as-is for sandbox execution.

    No shell string concatenation — always argv lists.
    Marks capability as Tier 0 (process wrapper).
    """

    name = "command"
    version = "0.1.0"

    def build_launch_spec(
        self,
        *,
        workspace: Path,
        user_command: Sequence[str],
        run_id: str,
    ) -> AdapterLaunchSpec:
        argv = list(user_command)
        return AdapterLaunchSpec(
            argv=argv,
            env={},
            capability_tier=CapabilityTier.PROCESS_WRAPPER,
            redacted_argv=_redact(argv),
        )


def _redact(argv: Sequence[str]) -> list[str]:
    """Produce a redacted copy of argv for safe logging/manifest storage."""
    sensitive_flags = {
        "--api-key", "--apikey", "--token", "--secret",
        "--password", "--pass", "--access-key", "--secret-key",
    }
    redacted: list[str] = []
    skip_next = False
    for _i, arg in enumerate(argv):
        if skip_next:
            redacted.append("***")
            skip_next = False
            continue
        if arg.lower() in sensitive_flags:
            redacted.append(arg)
            skip_next = True
        elif "=" in arg:
            key = arg.split("=", 1)[0].lower()
            if key in sensitive_flags:
                redacted.append(f"{arg.split('=', 1)[0]}=***")
            else:
                redacted.append(arg)
        else:
            redacted.append(arg)
    return redacted
