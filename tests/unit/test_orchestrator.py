"""Tests for RunOrchestrator behavior that do not require Docker."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agentfence.artifacts.integrity import sha256_file
from agentfence.core.orchestrator import RunConfig, RunOrchestrator
from agentfence.sandbox.base import ResourceSample, RunResult, SandboxConfig


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
    def assert_available(self) -> None:
        return

    def run(self, config: SandboxConfig) -> RunResult:
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
    assert report["run_summary"]["status"] == "completed"
    assert report["run_summary"]["head_sha"]
    assert report["resource_usage"]["sample_count"] == 1
    assert {event["type"] for event in events} >= {"RUN_COMPLETED", "REPORT_GENERATED"}
