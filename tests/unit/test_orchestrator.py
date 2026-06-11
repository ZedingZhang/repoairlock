"""Tests for RunOrchestrator behavior that do not require Docker."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import repoairlock.core.orchestrator as orchestrator_module
from repoairlock.artifacts.integrity import sha256_file
from repoairlock.artifacts.store import ArtifactStore
from repoairlock.core.orchestrator import RunConfig, RunOrchestrator, merge_status
from repoairlock.exceptions import CleanupError
from repoairlock.models.enums import RunStatus
from repoairlock.sandbox.base import ResourceSample, RunResult, SandboxConfig
from repoairlock.workspace.manager import WorkspaceManager


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
        agent_exit_code: int = 0,
        agent_timed_out: bool = False,
        verifier_exit_code: int = 0,
        mutate_source_repo: Path | None = None,
    ) -> None:
        self._agent_exit_code = agent_exit_code
        self._agent_timed_out = agent_timed_out
        self._verifier_exit_code = verifier_exit_code
        self._mutate_source_repo = mutate_source_repo
        self.agent_runs = 0
        self.verifier_runs = 0

    def assert_available(self) -> None:
        return

    def run(self, config: SandboxConfig) -> RunResult:
        if config.run_id.endswith("-verify"):
            self.verifier_runs += 1
            return RunResult(
                exit_code=self._verifier_exit_code,
                stdout="verify\n",
                stderr="",
                duration_ms=5,
            )
        self.agent_runs += 1
        if self._mutate_source_repo is not None:
            (self._mutate_source_repo / "hello.txt").write_text("mutated source\n")
        (config.workspace / "hello.txt").write_text("patched\n")
        return RunResult(
            exit_code=self._agent_exit_code,
            stdout="ok\n",
            stderr="",
            duration_ms=12,
            timed_out=self._agent_timed_out,
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
    assert manifest["integrity"]["patch.diff"] == sha256_file(result.run_dir / "patch.diff")
    assert report["run_summary"]["status"] == "completed"
    assert report["run_summary"]["head_sha"]
    assert report["artifact_integrity"]["events_jsonl"] == manifest["integrity"]["events.jsonl"]
    assert report["artifact_integrity"]["patch_diff"] == manifest["integrity"]["patch.diff"]
    assert "report_json" not in report["artifact_integrity"]
    assert report["resource_usage"]["sample_count"] == 1
    assert {event["type"] for event in events} >= {
        "RUN_COMPLETED",
        "REPORT_GENERATION_STARTED",
    }


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


def test_verifier_skipped_when_agent_exits_nonzero(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    backend = FakeDockerBackend(agent_exit_code=7, verifier_exit_code=0)
    orchestrator = RunOrchestrator()
    orchestrator._docker = backend
    result = orchestrator.execute(
        RunConfig(
            repo=repo,
            agent_command=["fake-agent"],
            image="fake-image",
            verify_command=["fake-verify"],
            runs_dir=tmp_path / "runs",
        )
    )

    events = _read_event_types(result.run_dir)
    assert result.status == RunStatus.AGENT_FAILED
    assert result.verifier_exit_code is None
    assert backend.verifier_runs == 0
    assert "VERIFICATION_STARTED" not in events


def test_verifier_skipped_when_agent_times_out(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    backend = FakeDockerBackend(agent_timed_out=True, verifier_exit_code=0)
    orchestrator = RunOrchestrator()
    orchestrator._docker = backend
    result = orchestrator.execute(
        RunConfig(
            repo=repo,
            agent_command=["fake-agent"],
            image="fake-image",
            verify_command=["fake-verify"],
            runs_dir=tmp_path / "runs",
        )
    )

    events = _read_event_types(result.run_dir)
    assert result.status == RunStatus.TIMED_OUT
    assert result.verifier_exit_code is None
    assert backend.verifier_runs == 0
    assert "VERIFICATION_STARTED" not in events


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


def test_report_write_failure_removes_partial_report_files(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    original_write_text = ArtifactStore.write_text

    def fail_report_html_write(self, name: str, content: str) -> None:
        if name == "report.html":
            (self.run_dir / "report.html").write_text("partial")
            raise OSError("forced report html write failure")
        original_write_text(self, name, content)

    monkeypatch.setattr(ArtifactStore, "write_text", fail_report_html_write)
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
    assert result.status == RunStatus.COMPLETED
    assert manifest["status"] == "completed"
    assert manifest["report_status"] == "failed: forced report html write failure"
    assert not (result.run_dir / "report.json").exists()
    assert not (result.run_dir / "report.html").exists()
    assert manifest["integrity"]["report.json"] == ""


def test_report_failure_does_not_override_invariant_violation(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    original_write_text = ArtifactStore.write_text

    def fail_report_html_write(self, name: str, content: str) -> None:
        if name == "report.html":
            (self.run_dir / "report.html").write_text("partial")
            raise OSError("forced report html write failure")
        original_write_text(self, name, content)

    monkeypatch.setattr(ArtifactStore, "write_text", fail_report_html_write)
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
    assert result.status == RunStatus.INVARIANT_VIOLATION
    assert manifest["status"] == "invariant_violation"
    assert not (result.run_dir / "report.json").exists()
    assert not (result.run_dir / "report.html").exists()


def test_merge_status_preserves_higher_priority_status() -> None:
    assert (
        merge_status(RunStatus.INVARIANT_VIOLATION, RunStatus.FAILED)
        == RunStatus.INVARIANT_VIOLATION
    )
    assert merge_status(RunStatus.COMPLETED, RunStatus.FAILED) == RunStatus.FAILED


def _read_event_types(run_dir: Path) -> set[str]:
    return {
        json.loads(line)["type"]
        for line in (run_dir / "events.jsonl").read_text().splitlines()
        if line.strip()
    }
