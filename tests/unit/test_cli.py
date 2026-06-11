"""Tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from agentfence.cli import app
from agentfence.core.orchestrator import RunResultSummary
from agentfence.models.enums import RunStatus

runner = CliRunner()


def test_help() -> None:
    """agentfence --help should list available commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "run" in result.stdout
    assert "inspect" in result.stdout
    assert "replay" in result.stdout
    assert "compare" in result.stdout
    assert "unsafe-local-execution" not in result.stdout


def test_version() -> None:
    """agentfence --version should print version and exit 0."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "agentfence" in result.stdout


def test_doctor_help() -> None:
    """agentfence doctor --help should show help."""
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout


def test_doctor_runs() -> None:
    """agentfence doctor should run and display checks.

    Exit code may be 0 (all pass) or 1 (some failed, e.g. Docker absent).
    """
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code in (0, 1)
    assert "environment check" in result.stdout.lower() or "Doctor" in result.stdout
    assert "Python" in result.stdout
    assert "Git" in result.stdout or "git" in result.stdout


def test_run_requires_repo() -> None:
    """agentfence run without --repo should show usage error."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 2  # Typer usage error


def test_run_rejects_invalid_network_enum(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = runner.invoke(
        app,
        ["run", "--repo", str(repo), "--network", "host", "--", "echo", "hello"],
    )
    assert result.exit_code == 2


def test_run_exits_nonzero_for_cleanup_failed(tmp_path: Path, monkeypatch) -> None:
    _assert_run_status_exit(
        tmp_path,
        monkeypatch,
        status=RunStatus.CLEANUP_FAILED,
        expected_exit_code=70,
    )


def test_run_exits_nonzero_for_invariant_violation(
    tmp_path: Path, monkeypatch
) -> None:
    _assert_run_status_exit(
        tmp_path,
        monkeypatch,
        status=RunStatus.INVARIANT_VIOLATION,
        expected_exit_code=80,
    )


def test_run_exits_nonzero_for_verification_failed(
    tmp_path: Path, monkeypatch
) -> None:
    _assert_run_status_exit(
        tmp_path,
        monkeypatch,
        status=RunStatus.VERIFICATION_FAILED,
        expected_exit_code=40,
    )


def test_list_works() -> None:
    """agentfence list should exit cleanly."""
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0


def test_inspect_requires_run_id() -> None:
    """agentfence inspect without run_id should show usage error."""
    result = runner.invoke(app, ["inspect"])
    assert result.exit_code == 2


def test_inspect_unknown_run() -> None:
    """agentfence inspect with bogus run should error."""
    result = runner.invoke(app, ["inspect", "nonexistent_run_id"])
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()


def test_replay_requires_run_id() -> None:
    """agentfence replay without run_id should show usage error."""
    result = runner.invoke(app, ["replay"])
    assert result.exit_code == 2


def test_replay_unknown_run() -> None:
    """agentfence replay with bogus run should error."""
    result = runner.invoke(app, ["replay", "nonexistent_run"])
    assert result.exit_code == 1


def test_compare_requires_two_ids() -> None:
    """agentfence compare without arguments should show usage error."""
    result = runner.invoke(app, ["compare"])
    assert result.exit_code == 2


def test_compare_unknown_runs() -> None:
    """agentfence compare with bogus runs should error."""
    result = runner.invoke(app, ["compare", "bogus_a", "bogus_b"])
    assert result.exit_code == 1


def test_inspect_help() -> None:
    """agentfence inspect --help should show help."""
    result = runner.invoke(app, ["inspect", "--help"])
    assert result.exit_code == 0
    assert "inspect" in result.stdout.lower()


def test_replay_help() -> None:
    """agentfence replay --help should show help."""
    result = runner.invoke(app, ["replay", "--help"])
    assert result.exit_code == 0
    assert "replay" in result.stdout.lower()


def test_compare_help() -> None:
    """agentfence compare --help should show help."""
    result = runner.invoke(app, ["compare", "--help"])
    assert result.exit_code == 0
    assert "compare" in result.stdout.lower()


def _assert_run_status_exit(
    tmp_path: Path,
    monkeypatch,
    *,
    status: RunStatus,
    expected_exit_code: int,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "runs" / "run_fake"
    run_dir.mkdir(parents=True)

    class FakeRunOrchestrator:
        def execute(self, config):
            return RunResultSummary(
                run_id="run_fake",
                run_dir=run_dir,
                status=status,
                exit_code=0,
                patch_bytes=0,
                verifier_exit_code=1 if status == RunStatus.VERIFICATION_FAILED else None,
            )

    import agentfence.core.orchestrator as orchestrator_module
    monkeypatch.setattr(orchestrator_module, "RunOrchestrator", FakeRunOrchestrator)
    result = runner.invoke(app, ["run", "--repo", str(repo), "--", "echo", "hello"])
    assert result.exit_code == expected_exit_code
    assert status.value in result.stdout
