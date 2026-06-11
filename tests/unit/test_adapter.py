"""Tests for CommandAdapter and AdapterLaunchSpec."""

from __future__ import annotations

from pathlib import Path

from patchguard.adapters.base import AdapterLaunchSpec
from patchguard.adapters.command import CommandAdapter


class TestAdapterLaunchSpec:
    def test_create(self) -> None:
        spec = AdapterLaunchSpec(
            argv=["python", "agent.py"],
            env={},
            capability_tier="tier_0_process_wrapper",
            redacted_argv=["python", "agent.py"],
        )
        assert spec.argv == ["python", "agent.py"]
        assert spec.capability_tier == "tier_0_process_wrapper"


class TestCommandAdapter:
    def test_name_and_version(self) -> None:
        adapter = CommandAdapter()
        assert adapter.name == "command"
        assert adapter.version == "0.1.0"

    def test_build_launch_spec_passes_command_through(self) -> None:
        adapter = CommandAdapter()
        spec = adapter.build_launch_spec(
            workspace=Path("/workspace"),
            user_command=["python", "/opt/agent.py", "--verbose"],
            run_id="run_test",
        )
        assert spec.argv == ["python", "/opt/agent.py", "--verbose"]
        assert spec.capability_tier == "tier_0_process_wrapper"

    def test_redacted_argv_hides_secrets(self) -> None:
        adapter = CommandAdapter()
        spec = adapter.build_launch_spec(
            workspace=Path("/workspace"),
            user_command=["agent", "--api-key", "mysecret", "run"],
            run_id="run_test",
        )
        assert spec.redacted_argv == ["agent", "--api-key", "***", "run"]

    def test_redacted_argv_hides_token_equals(self) -> None:
        adapter = CommandAdapter()
        spec = adapter.build_launch_spec(
            workspace=Path("/workspace"),
            user_command=["agent", "--token=s3cr3t", "run"],
            run_id="run_test",
        )
        assert spec.redacted_argv == ["agent", "--token=***", "run"]

    def test_redacted_argv_does_not_redact_normal_args(self) -> None:
        adapter = CommandAdapter()
        spec = adapter.build_launch_spec(
            workspace=Path("/workspace"),
            user_command=["python", "agent.py", "--model", "gpt-4"],
            run_id="run_test",
        )
        assert spec.redacted_argv == ["python", "agent.py", "--model", "gpt-4"]
