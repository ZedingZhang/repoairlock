"""ReportGenerator — produces report.json and report.html from run artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from patchguard.analysis.diff_metrics import compute_diff_metrics
from patchguard.analysis.quality_score import compute_quality_findings
from patchguard.analysis.trajectory_metrics import compute_trajectory_metrics


class ReportGenerator:
    """Reads run artifacts and produces structured report data + HTML.

    Key design rules:
    - Report explicitly shows capability tier
    - Report states what conclusions CANNOT be drawn at this tier
    - Failed runs also generate reports
    - Report includes replay instructions
    """

    def __init__(self, run_dir: Path, run_id: str) -> None:
        self._run_dir = run_dir
        self._run_id = run_id

    def generate(self) -> dict[str, object]:
        """Generate the report dict ready for JSON serialization and HTML rendering."""
        manifest = self._load_manifest()
        patch_content = self._read_file("patch.diff")
        events_path = self._run_dir / "events.jsonl"

        capability_tier = manifest.get("capability_tier", "tier_0_process_wrapper")
        sandbox = manifest.get("sandbox", {})

        # Compute metrics
        diff_metrics = compute_diff_metrics(patch_content)
        trajectory_metrics = compute_trajectory_metrics(events_path)
        findings = compute_quality_findings(
            capability_tier=str(capability_tier),
            diff_metrics=diff_metrics,
            trajectory_metrics=trajectory_metrics,
            sandbox_config=sandbox,
        )

        # Safety posture
        safety = {
            "unsafe_local_execution": sandbox.get("unsafe_local_execution", False),
            "network_mode": sandbox.get("network", "none"),
            "read_only_rootfs": sandbox.get("read_only_rootfs", True),
            "privileged": False,  # never allowed
            "sensitive_env_passed": [],  # names only, never values
            "source_workspace_unchanged": (
                manifest.get("repo", {}).get("source_fingerprint_before", "")
                == manifest.get("repo", {}).get("source_fingerprint_after", "")
                and manifest.get("repo", {}).get("source_fingerprint_before", "") != ""
            ),
        }

        # Integrity
        integrity = manifest.get("integrity", {})

        report: dict[str, object] = {
            "report_schema_version": "1.0",
            "run_id": self._run_id,
            "capability_tier": capability_tier,
            "capability_tier_description": _tier_description(str(capability_tier)),
            "capability_visibility_limits": _visibility_limits(str(capability_tier)),
            "run_summary": {
                "status": manifest.get("status", "unknown"),
                "created_at": manifest.get("created_at", ""),
                "completed_at": manifest.get("completed_at", ""),
                "repo_path": manifest.get("repo", {}).get("source_path", ""),
                "head_sha": manifest.get("repo", {}).get("head_sha", "")[:12],
            },
            "adapter": manifest.get("adapter", {}),
            "safety_posture": safety,
            "sandbox_config": {
                "image": sandbox.get("image", ""),
                "network": sandbox.get("network", ""),
                "cpus": sandbox.get("cpus", ""),
                "memory": sandbox.get("memory", ""),
                "pids_limit": sandbox.get("pids_limit", ""),
                "timeout_seconds": sandbox.get("timeout_seconds", ""),
            },
            "repository_change_summary": diff_metrics,
            "verification_result": {
                "verifier_configured": trajectory_metrics.get("verifier_configured", False),
                "verifier_exit_code": trajectory_metrics.get("verifier_exit_code"),
                "verifier_passed": trajectory_metrics.get("verifier_passed"),
            },
            "resource_usage": trajectory_metrics.get("resource_summary", {}),
            "run_metrics": {
                "wall_time_ms": trajectory_metrics.get("wall_time_ms", 0),
                "agent_exit_code": trajectory_metrics.get("agent_exit_code", -1),
                "timed_out": trajectory_metrics.get("timed_out", False),
                "cleanup_success": trajectory_metrics.get("cleanup_success", False),
            },
            "quality_findings": findings,
            "policy_findings": [],
            "artifact_integrity": {
                "events_jsonl": integrity.get("events.jsonl", ""),
                "patch_diff": integrity.get("patch.diff", ""),
                "report_json": integrity.get("report.json", ""),
            },
            "replay_instructions": {
                "command": f"patchguard replay {self._run_id}",
                "note": (
                    "Replay does NOT re-invoke the agent. "
                    "It validates artifact integrity and "
                    "applies the patch to a fresh worktree."
                ),
            },
        }

        return report

    def generate_html(self, report: dict[str, object]) -> str:
        """Render report dict to an HTML string using Jinja2."""
        from jinja2 import Template

        template_path = Path(__file__).parent / "templates" / "report.html.j2"
        if template_path.exists():
            tmpl = Template(template_path.read_text())
            return tmpl.render(**report)

        # Fallback inline template
        return _inline_html(report)

    def _load_manifest(self) -> dict[str, Any]:
        import json
        mf = self._run_dir / "manifest.json"
        if not mf.exists():
            return {}
        data: dict[str, Any] = json.loads(mf.read_text())
        return data

    def _read_file(self, name: str) -> str:
        p = self._run_dir / name
        if p.exists():
            return p.read_text()
        return ""


def _tier_description(tier: str) -> str:
    descriptions = {
        "tier_0_process_wrapper": (
            "Process Wrapper: PatchGuard observes and records process-level "
            "data (stdout, stderr, exit code, resources). It does NOT observe "
            "internal agent tool calls, LLM prompts, or reasoning steps."
        ),
        "tier_1_structured_events": (
            "Structured Events: PatchGuard imports agent tool-call traces for "
            "per-step observability."
        ),
        "tier_2_enforcement": (
            "Enforcement: PatchGuard intercepts and can block individual tool "
            "calls before execution."
        ),
    }
    return descriptions.get(tier, "Unknown capability tier.")


def _visibility_limits(tier: str) -> str:
    if tier == "tier_0_process_wrapper":
        return (
            "This report CANNOT confirm: whether the agent inspected all relevant "
            "files, whether it reasoned correctly about the fix, how many LLM "
            "turns were used, whether any tool calls failed silently, or whether "
            "the agent performed unnecessary work. These require Tier 1+ adapter."
        )
    return ""


def _inline_html(report: dict[str, Any]) -> str:
    """Minimal inline HTML template (used when report.html.j2 is absent)."""
    run_summary: Any = report.get("run_summary", {})
    status = run_summary.get("status", "unknown") if isinstance(run_summary, dict) else "unknown"
    run_id = report.get("run_id", "")
    tier = report.get("capability_tier", "")
    limits = report.get("capability_visibility_limits", "")
    ri: Any = report.get("replay_instructions", {})
    replay_cmd = ri.get("command", "") if isinstance(ri, dict) else ""
    status_class = "passed" if status == "completed" else "failed"
    css = (
        "body{font-family:system-ui,sans-serif;max-width:800px;"
        "margin:2rem auto;padding:0 1rem;line-height:1.6}"
        "h1{border-bottom:2px solid #333}h2{margin-top:2rem}"
        ".meta{display:grid;grid-template-columns:200px 1fr;gap:.5rem}"
        ".label{font-weight:bold}.passed{color:green}.failed{color:red}"
        ".note{background:#fff3cd;padding:1rem;"
        "border-left:4px solid #ffc107;margin:1rem 0}"
    )  # noqa: E501
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>PatchGuard Report — {run_id}</title>
<style>{css}</style></head>
<body>
<h1>PatchGuard Run Report</h1>
<div class="meta">
<div class="label">Run ID</div><div>{run_id}</div>
<div class="label">Status</div><div class="{status_class}">{status}</div>
<div class="label">Capability Tier</div><div>{tier}</div>
</div>
<div class="note"><strong>Visibility Limits:</strong> {limits}</div>
<h2>Replay</h2><pre>{replay_cmd}</pre>
<p><em>Generated by PatchGuard v0.1.0</em></p>
</body></html>"""
