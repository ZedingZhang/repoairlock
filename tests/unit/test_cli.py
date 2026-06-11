"""Tests for the CLI entry point."""

from __future__ import annotations

from typer.testing import CliRunner

from patchguard.cli import app

runner = CliRunner()


def test_help() -> None:
    """patchguard --help should list available commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "run" in result.stdout
    assert "inspect" in result.stdout
    assert "replay" in result.stdout
    assert "compare" in result.stdout


def test_version() -> None:
    """patchguard --version should print version and exit 0."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "patchguard" in result.stdout


def test_doctor_help() -> None:
    """patchguard doctor --help should show help."""
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout


def test_doctor_runs() -> None:
    """patchguard doctor should run and display checks.

    Exit code may be 0 (all pass) or 1 (some failed, e.g. Docker absent).
    """
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code in (0, 1)
    assert "environment check" in result.stdout.lower() or "Doctor" in result.stdout
    assert "Python" in result.stdout
    assert "Git" in result.stdout or "git" in result.stdout


def test_run_requires_repo() -> None:
    """patchguard run without --repo should show usage error."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 2  # Typer usage error


def test_list_works() -> None:
    """patchguard list should exit cleanly."""
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0


def test_inspect_requires_run_id() -> None:
    """patchguard inspect without run_id should show usage error."""
    result = runner.invoke(app, ["inspect"])
    assert result.exit_code == 2


def test_inspect_unknown_run() -> None:
    """patchguard inspect with bogus run should error."""
    result = runner.invoke(app, ["inspect", "nonexistent_run_id"])
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()


def test_replay_requires_run_id() -> None:
    """patchguard replay without run_id should show usage error."""
    result = runner.invoke(app, ["replay"])
    assert result.exit_code == 2


def test_replay_unknown_run() -> None:
    """patchguard replay with bogus run should error."""
    result = runner.invoke(app, ["replay", "nonexistent_run"])
    assert result.exit_code == 1


def test_compare_requires_two_ids() -> None:
    """patchguard compare without arguments should show usage error."""
    result = runner.invoke(app, ["compare"])
    assert result.exit_code == 2


def test_compare_unknown_runs() -> None:
    """patchguard compare with bogus runs should error."""
    result = runner.invoke(app, ["compare", "bogus_a", "bogus_b"])
    assert result.exit_code == 1


def test_inspect_help() -> None:
    """patchguard inspect --help should show help."""
    result = runner.invoke(app, ["inspect", "--help"])
    assert result.exit_code == 0
    assert "inspect" in result.stdout.lower()


def test_replay_help() -> None:
    """patchguard replay --help should show help."""
    result = runner.invoke(app, ["replay", "--help"])
    assert result.exit_code == 0
    assert "replay" in result.stdout.lower()


def test_compare_help() -> None:
    """patchguard compare --help should show help."""
    result = runner.invoke(app, ["compare", "--help"])
    assert result.exit_code == 0
    assert "compare" in result.stdout.lower()
