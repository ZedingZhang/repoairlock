"""Tests for the CLI entry point."""

from __future__ import annotations

from typer.testing import CliRunner

from agentfence.cli import app

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
