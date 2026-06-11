"""Trajectory metrics — computes run-time metrics from events.jsonl and resource samples."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compute_trajectory_metrics(
    events_path: Path,
    resource_samples: list[Any] | None = None,
) -> dict[str, object]:
    """Compute run-time metrics from events and resource data.

    For Tier 0, metrics are limited to process-level observables.
    """
    events = _load_events(events_path)

    wall_time_ms = _compute_wall_time(events)
    exit_code = _find_field(events, "PROCESS_EXITED", "exit_code", -1)
    timed_out = _find_field(events, "PROCESS_EXITED", "timed_out", False)
    cleanup_success = not _has_event(events, "CLEANUP_FAILED")

    patch_bytes = _find_field(events, "PATCH_EXPORTED", "patch_bytes", 0)

    verifier_configured = _has_event(events, "VERIFICATION_STARTED")
    verifier_exit_code = _find_field(events, "VERIFICATION_FINISHED", "exit_code", -1)
    verifier_passed = _find_field(events, "VERIFICATION_FINISHED", "passed", False)
    verifier_exit_code = -1 if not verifier_configured else verifier_exit_code

    # Resource aggregates
    resource_summary = _aggregate_resources(resource_samples or [])

    return {
        "wall_time_ms": wall_time_ms,
        "agent_exit_code": exit_code,
        "timed_out": timed_out,
        "cleanup_success": cleanup_success,
        "patch_bytes": patch_bytes,
        "verifier_configured": verifier_configured,
        "verifier_exit_code": verifier_exit_code if verifier_configured else None,
        "verifier_passed": verifier_passed if verifier_configured else None,
        "resource_summary": resource_summary,
    }


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _compute_wall_time(events: list[dict[str, object]]) -> int:
    """Compute wall time from RUN_CREATED to final event."""
    t0 = ""
    t1 = ""
    for e in events:
        etype = e.get("type", "")
        if etype == "RUN_CREATED" and not t0:
            t0 = str(e.get("timestamp", ""))
    # Use last event's timestamp
    for e in reversed(events):
        etype = e.get("type", "")
        if etype in ("RUN_COMPLETED", "RUN_FAILED", "RUN_TIMED_OUT", "RUN_CANCELLED"):
            t1 = str(e.get("timestamp", ""))
            break
    if not t0 or not t1:
        return 0
    try:
        from datetime import datetime
        fmt = "%Y-%m-%dT%H:%M:%S"
        ts0 = datetime.strptime(t0[:19], fmt)
        ts1 = datetime.strptime(t1[:19], fmt)
        ms0 = int(t0[20:23]) if len(t0) > 20 else 0
        ms1 = int(t1[20:23]) if len(t1) > 20 else 0
        return int((ts1 - ts0).total_seconds() * 1000) + (ms1 - ms0)
    except (ValueError, IndexError):
        return 0


def _find_field(
    events: list[dict[str, object]], event_type: str, field: str, default: object
) -> object:
    for e in events:
        if e.get("type") == event_type:
            payload = e.get("payload", {})
            if isinstance(payload, dict) and field in payload:
                return payload[field]
    return default


def _has_event(events: list[dict[str, object]], event_type: str) -> bool:
    return any(e.get("type") == event_type for e in events)


def _aggregate_resources(samples: list[Any]) -> dict[str, object]:
    if not samples:
        return {
            "peak_memory_bytes": 0,
            "avg_cpu_percent": 0.0,
            "peak_pids": 0,
            "network_rx_bytes": 0,
            "network_tx_bytes": 0,
            "sample_count": 0,
        }
    peak_mem = max((s.get("memory_bytes", 0) for s in samples if isinstance(s, dict)), default=0)
    cpu_vals = [s.get("cpu_percent", 0.0) for s in samples if isinstance(s, dict)]
    avg_cpu = sum(cpu_vals) / max(len(samples), 1)
    peak_pids = max((s.get("pids_current", 0) for s in samples if isinstance(s, dict)), default=0)
    net_rx = sum(s.get("network_rx_bytes", 0) for s in samples if isinstance(s, dict))
    net_tx = sum(s.get("network_tx_bytes", 0) for s in samples if isinstance(s, dict))
    return {
        "peak_memory_bytes": peak_mem,
        "avg_cpu_percent": round(avg_cpu, 2),
        "peak_pids": peak_pids,
        "network_rx_bytes": int(net_rx),
        "network_tx_bytes": int(net_tx),
        "sample_count": len(samples),
    }
