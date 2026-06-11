"""Tests for RunOrchestrator behavior that do not require Docker."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import agentfence.core.orchestrator as orchestrator_module
from agentfence.artifacts.integrity import sha256_file
from agentfence.core.orchestrator import RunConfig, RunOrchestrator
from agentfence.exceptions import CleanupError
from agentfence.models.enums import RunStatus
from agentfence.sandbox.base import ResourceSample, RunResult, SandboxConfig
from agentfence.workspace.manager import WorkspaceManager


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.test"],
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path, capture_output=True, check=True,
    )
    (path / "hello.txt").write_text("base\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True, check=True)


class FakeDockerBackend:
    def __init__(
        self,
        *,
        verifier_exit_code: int = 0,
        mutate_source_repo: Path | None = None,
    ) -> None:
        self._verifier_exit_code = verifier_exit_code
        self._mutate_source_repo = mutate_source_repo

    def assert_available(self) -> None:
        return

    def run(self, config: SandboxConfig) -> RunResult:
        if config.run_id.endswith("-verify"):
            return RunResult(
                exit_code=self._verifier_exit_code,
                stdout="verify\n",
                stderr="",
                duration_ms=5,
            )
        if self._mutate_source_repo is not None:
            (self._mutate_source_repo / "hello.txt").write_text("mutated source\n")
        (config.workspace / "hello.txt").write_text("patched\n")
        return RunResult(
            exit_code=0,
            stdout="ok\n",
            stderr="",
            duration_ms=12,
            resource_samples=[
                ResourceSample(
                    timestamp=1.0,
                    cpu_percent=25.0,
                    memory_bytes=1234,
                    memory_limit_bytes=4096,
                    pids_current=3,
                )
            ],
        )


def test_orchestrator_finalizes_events_report_and_integrity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    orchestrator = RunOrchestrator()
    orchestrator._docker = FakeDockerBackend()
    result = orchestrator.execute(
        RunConfig(
            repo=repo,
            agent_command=["fake-agent"],
            image="fake-image",
            runs_dir=tmp_path / "runs",
        )
    )

    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    report = json.loads((result.run_dir / "report.json").read_text())
    events = [
        json.loads(line)
        for line in (result.run_dir / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]

    assert manifest["status"] == "completed"
    assert manifest["completed_at"]
    assert manifest["integrity"]["events.jsonl"] == sha256_file(result.run_dir / "events.jsonl")
    assert manifest["integrity"]["report.json"] == sha256_file(result.run_dir / "report.json")
    assert report["run_summary"]["status"] == "completed"
    assert report["run_summary"]["head_sha"]
    assert report["artifact_integrity"]["events_jsonl"]
    assert report["artifact_integrity"]["patch_diff"]
    assert report["resource_usage"]["sample_count"] == 1
    assert {event["type"] for event in events} >= {"RUN_COMPLETED", "REPORT_GENERATED"}


def test_verifier_failure_sets_final_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    orchestrator = RunOrchestrator()
    orchestrator._docker = FakeDockerBackend(verifier_exit_code=2)
    result = orchestrator.execute(
        RunConfig(
            repo=repo,
            agent_command=["fake-agent"],
            image="fake-image",
            verify_command=["fake-verify"],
            runs_dir=tmp_path / "runs",
        )
    )

    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    events = _read_event_types(result.run_dir)
    assert result.status == RunStatus.VERIFICATION_FAILED
    assert result.verifier_exit_code == 2
    assert manifest["status"] == "verification_failed"
    assert "VERIFICATION_FAILED" in events


def test_cleanup_failure_sets_final_status_after_main_flow(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    class FailingCleanupWorkspaceManager(WorkspaceManager):
        def cleanup(self, source_repo: str | Path, worktree: Path):
            super().cleanup(source_repo, worktree)
            raise CleanupError("forced cleanup failure")

    monkeypatch.setattr(
        orchestrator_module, "WorkspaceManager", FailingCleanupWorkspaceManager
    )
    orchestrator = RunOrchestrator()
    orchestrator._docker = FakeDockerBackend()
    result = orchestrator.execute(
        RunConfig(
            repo=repo,
            agent_command=["fake-agent"],
            image="fake-image",
            runs_dir=tmp_path / "runs",
        )
    )

    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    events = _read_event_types(result.run_dir)
    assert result.status == RunStatus.CLEANUP_FAILED
    assert manifest["status"] == "cleanup_failed"
    assert "CLEANUP_FAILED" in events


def test_invariant_violation_sets_final_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    orchestrator = RunOrchestrator()
    orchestrator._docker = FakeDockerBackend(mutate_source_repo=repo)
    result = orchestrator.execute(
        RunConfig(
            repo=repo,
            agent_command=["fake-agent"],
            image="fake-image",
            runs_dir=tmp_path / "runs",
        )
    )

    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    events = _read_event_types(result.run_dir)
    assert result.status == RunStatus.INVARIANT_VIOLATION
    assert manifest["status"] == "invariant_violation"
    assert "INVARIANT_VIOLATION" in events


def _read_event_types(run_dir: Path) -> set[str]:
    return {
        json.loads(line)["type"]
        for line in (run_dir / "events.jsonl").read_text().splitlines()
        if line.strip()
    }
