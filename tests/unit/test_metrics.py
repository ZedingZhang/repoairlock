"""Tests for diff metrics, trajectory metrics, quality findings, and report generation."""

from __future__ import annotations

import json
from pathlib import Path

from agentfence.analysis.diff_metrics import _is_sensitive, compute_diff_metrics
from agentfence.analysis.quality_score import compute_quality_findings
from agentfence.analysis.trajectory_metrics import (
    compute_trajectory_metrics,
)
from agentfence.reporting.generator import ReportGenerator


def _write_events(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(evt) for evt in lines))


TS = "2026-06-11T00:00:"
E0 = {"type": "RUN_CREATED", "timestamp": f"{TS}00.000Z", "payload": {}}
EXIT = {"type": "PROCESS_EXITED", "timestamp": f"{TS}05.000Z",
        "payload": {"exit_code": 0}}
PATCH = {"type": "PATCH_EXPORTED", "timestamp": f"{TS}05.500Z",
         "payload": {"patch_bytes": 200}}
COMP = {"type": "RUN_COMPLETED", "timestamp": f"{TS}06.000Z", "payload": {}}
FAIL = {"type": "RUN_FAILED", "timestamp": f"{TS}01.500Z", "payload": {}}


class TestDiffMetrics:
    def test_empty_patch(self) -> None:
        m = compute_diff_metrics("")
        assert m["files_changed"] == 0
        assert m["lines_added"] == 0
        assert m["lines_deleted"] == 0

    def test_single_file_patch(self) -> None:
        patch = (
            "diff --git a/hello.py b/hello.py\n"
            "--- a/hello.py\n"
            "+++ b/hello.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-old line\n"
            "+new line\n"
        )
        m = compute_diff_metrics(patch)
        assert m["files_changed"] == 1
        assert m["lines_added"] == 1
        assert m["lines_deleted"] == 1

    def test_multiple_files(self) -> None:
        patch = (
            "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n"
            "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-x\n+y\n"
        )
        m = compute_diff_metrics(patch)
        assert m["files_changed"] == 2
        assert m["lines_added"] == 2
        assert m["lines_deleted"] == 2

    def test_new_file(self) -> None:
        patch = (
            "diff --git a/new.py b/new.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/new.py\n"
            "@@ -0,0 +1 @@\n"
            "+print('hello')\n"
        )
        m = compute_diff_metrics(patch)
        assert m["files_added"] == 1

    def test_deleted_file(self) -> None:
        patch = (
            "diff --git a/old.py b/old.py\n"
            "deleted file mode 100644\n"
            "--- a/old.py\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n"
            "-print('bye')\n"
        )
        m = compute_diff_metrics(patch)
        assert m["files_deleted"] == 1

    def test_changed_paths(self) -> None:
        patch = "\n".join([
            "diff --git a/src/main.py b/src/main.py",
            "--- a/src/main.py", "+++ b/src/main.py",
            "@@ -1 +1 @@", "-a", "+b",
        ])
        m = compute_diff_metrics(patch)
        assert "src/main.py" in m["changed_paths"]

    def test_sensitive_path_detection(self) -> None:
        patch = "\n".join([
            "diff --git a/.git/hooks/pre-commit b/.git/hooks/pre-commit",
            "--- a/.git/hooks/pre-commit", "+++ b/.git/hooks/pre-commit",
            "@@ -1 +1 @@", "-a", "+b",
        ])
        m = compute_diff_metrics(patch)
        assert len(m["touched_sensitive_paths"]) > 0

    def test_is_sensitive_helper(self) -> None:
        assert _is_sensitive(".git/hooks/pre-commit")
        assert _is_sensitive(".env")
        assert _is_sensitive("secrets/config.json")
        assert not _is_sensitive("src/main.py")
        assert not _is_sensitive("README.md")


class TestTrajectoryMetrics:
    def test_empty_events(self, tmp_path: Path) -> None:
        events = tmp_path / "events.jsonl"
        events.write_text("")
        m = compute_trajectory_metrics(events)
        assert m["wall_time_ms"] == 0
        assert m["agent_exit_code"] == -1

    def test_basic_events(self, tmp_path: Path) -> None:
        events = tmp_path / "events.jsonl"
        _write_events(events, [E0, EXIT, PATCH, COMP])
        m = compute_trajectory_metrics(events)
        assert m["agent_exit_code"] == 0
        assert m["patch_bytes"] == 200
        assert m["wall_time_ms"] > 0

    def test_failed_run(self, tmp_path: Path) -> None:
        events = tmp_path / "events.jsonl"
        fe = {"type": "PROCESS_EXITED", "timestamp": f"{TS}01.000Z",
              "payload": {"exit_code": 1, "timed_out": False}}
        _write_events(events, [E0, fe, FAIL])
        m = compute_trajectory_metrics(events)
        assert m["agent_exit_code"] == 1
        assert not m["timed_out"]

    def test_verifier_metrics(self, tmp_path: Path) -> None:
        events = tmp_path / "events.jsonl"
        vs = {"type": "VERIFICATION_STARTED", "payload": {}}
        vf = {"type": "VERIFICATION_FINISHED",
              "payload": {"exit_code": 0, "passed": True}}
        _write_events(events, [E0, vs, vf, COMP])
        m = compute_trajectory_metrics(events)
        assert m["verifier_configured"] is True
        assert m["verifier_exit_code"] == 0
        assert m["verifier_passed"] is True

    def test_resource_samples_from_events(self, tmp_path: Path) -> None:
        events = tmp_path / "events.jsonl"
        sample_a = {
            "type": "RESOURCE_SAMPLE",
            "payload": {
                "cpu_percent": 10.0,
                "memory_bytes": 100,
                "network_rx_bytes": 5,
                "network_tx_bytes": 7,
                "pids_current": 2,
            },
        }
        sample_b = {
            "type": "RESOURCE_SAMPLE",
            "payload": {
                "cpu_percent": 30.0,
                "memory_bytes": 250,
                "network_rx_bytes": 11,
                "network_tx_bytes": 13,
                "pids_current": 4,
            },
        }
        _write_events(events, [E0, sample_a, sample_b, COMP])
        m = compute_trajectory_metrics(events)
        resources = m["resource_summary"]
        assert resources["sample_count"] == 2
        assert resources["peak_memory_bytes"] == 250
        assert resources["avg_cpu_percent"] == 20.0
        assert resources["peak_pids"] == 4
        assert resources["network_rx_bytes"] == 16
        assert resources["network_tx_bytes"] == 20


class TestQualityFindings:
    def test_tier0_notice(self) -> None:
        findings = compute_quality_findings(
            capability_tier="tier_0_process_wrapper",
            diff_metrics={},
            trajectory_metrics={},
            sandbox_config={},
        )
        assert any("Tier 0" in f for f in findings)

    def test_network_disabled_finding(self) -> None:
        findings = compute_quality_findings(
            capability_tier="tier_0_process_wrapper",
            diff_metrics={},
            trajectory_metrics={},
            sandbox_config={"network": "none"},
        )
        assert any("no data exfiltration" in f.lower() for f in findings)

    def test_network_enabled_finding(self) -> None:
        findings = compute_quality_findings(
            capability_tier="tier_0_process_wrapper",
            diff_metrics={},
            trajectory_metrics={},
            sandbox_config={"network": "bridge"},
        )
        assert any("had network access" in f.lower() for f in findings)

    def test_verifier_passed(self) -> None:
        findings = compute_quality_findings(
            capability_tier="tier_0_process_wrapper",
            diff_metrics={},
            trajectory_metrics={"verifier_passed": True},
            sandbox_config={},
        )
        assert any("verification passed" in f.lower() for f in findings)

    def test_verifier_failed(self) -> None:
        findings = compute_quality_findings(
            capability_tier="tier_0_process_wrapper",
            diff_metrics={},
            trajectory_metrics={"verifier_passed": False},
            sandbox_config={},
        )
        assert any("verification failed" in f.lower() for f in findings)

    def test_sensitive_paths(self) -> None:
        findings = compute_quality_findings(
            capability_tier="tier_0_process_wrapper",
            diff_metrics={"touched_sensitive_paths": [".env"]},
            trajectory_metrics={},
            sandbox_config={},
        )
        assert any("sensitive path" in f.lower() for f in findings)


def _mk_mf(run_id: str, status: str = "completed") -> dict:
    return {
        "schema_version": "1.0", "run_id": run_id,
        "created_at": "2026-06-11T00:00:00.000Z", "status": status,
        "capability_tier": "tier_0_process_wrapper",
        "repo": {"source_path": "/x", "head_sha": "abc",
                 "source_fingerprint_before": "",
                 "source_fingerprint_after": ""},
        "adapter": {"name": "command", "version": "0.1.0"},
        "sandbox": {"image": "img", "network": "none"},
        "artifacts": {},
        "integrity": {"events.jsonl": "", "patch.diff": "",
                      "report.json": ""},
    }


def _setup_run_dir(tmp_path: Path, run_id: str, status: str = "completed") -> Path:
    d = tmp_path / run_id
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps(_mk_mf(run_id, status)))
    (d / "events.jsonl").write_text("")
    (d / "patch.diff").write_text("")
    return d


class TestReportGenerator:
    def test_generate_empty_run(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path, "run_test")
        gen = ReportGenerator(run_dir, "run_test")
        report = gen.generate()
        assert report["run_id"] == "run_test"
        assert report["capability_tier"] == "tier_0_process_wrapper"
        assert "capability_visibility_limits" in report
        assert "replay_instructions" in report
        assert report["replay_instructions"]["command"] == "agentfence replay run_test"

    def test_generate_html(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path, "run_html")
        gen = ReportGenerator(run_dir, "run_html")
        report = gen.generate()
        html = gen.generate_html(report)
        assert "<!DOCTYPE html>" in html
        assert "run_html" in html
        assert "tier_0_process_wrapper" in html
        assert "Known Visibility Limits" in html
        assert "agentfence replay run_html" in html

    def test_report_for_failed_run(self, tmp_path: Path) -> None:
        run_dir = _setup_run_dir(tmp_path, "run_fail", status="failed")
        gen = ReportGenerator(run_dir, "run_fail")
        report = gen.generate()
        assert report["run_summary"]["status"] == "failed"
        html = gen.generate_html(report)
        assert "FAILED" in html
