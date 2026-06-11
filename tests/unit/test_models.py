"""Tests for domain models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from patchguard.models.enums import CapabilityTier, RunStatus
from patchguard.models.events import EventEnvelope, EventType
from patchguard.models.manifest import (
    MANIFEST_SCHEMA_VERSION,
    IntegrityMap,
    Manifest,
    RepoInfo,
)


class TestRunStatus:
    def test_all_statuses_defined(self) -> None:
        expected = {
            "created", "preparing", "running", "verifying",
            "completed", "failed", "timed_out", "cancelled", "policy_blocked",
        }
        assert set(RunStatus) == expected

    def test_status_is_string(self) -> None:
        assert RunStatus.CREATED == "created"
        assert isinstance(RunStatus.CREATED, str)


class TestCapabilityTier:
    def test_tiers_defined(self) -> None:
        expected = {
            "tier_0_process_wrapper",
            "tier_1_structured_events",
            "tier_2_enforcement",
        }
        assert set(CapabilityTier) == expected


class TestEventEnvelope:
    def test_create_minimal_event(self) -> None:
        event = EventEnvelope.create(
            event_id="evt_001",
            run_id="run_001",
            sequence=1,
            source="test",
            type=EventType.RUN_CREATED,
        )
        assert event.schema_version == "1.0"
        assert event.event_id == "evt_001"
        assert event.run_id == "run_001"
        assert event.sequence == 1
        assert event.type == EventType.RUN_CREATED
        assert event.payload == {}

    def test_create_event_with_payload(self) -> None:
        event = EventEnvelope.create(
            event_id="evt_002",
            run_id="run_002",
            sequence=2,
            source="sandbox.docker",
            type=EventType.PROCESS_EXITED,
            payload={"exit_code": 0, "duration_ms": 42821},
        )
        assert event.payload == {"exit_code": 0, "duration_ms": 42821}

    def test_sequence_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            EventEnvelope(
                event_id="e",
                run_id="r",
                sequence=0,
                timestamp="t",
                source="s",
                type=EventType.RUN_CREATED,
            )

    def test_reject_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            EventEnvelope(
                schema_version="1.0",
                event_id="e",
                run_id="r",
                sequence=1,
                timestamp="t",
                source="s",
                type=EventType.RUN_CREATED,
                bogus_field=True,  # type: ignore[call-arg]
            )

    def test_serialize_to_jsonl(self) -> None:
        event = EventEnvelope.create(
            event_id="evt_003",
            run_id="run_003",
            sequence=1,
            source="test",
            type=EventType.RUN_CREATED,
        )
        line = json.dumps(event.model_dump(), ensure_ascii=False, sort_keys=True)
        parsed = json.loads(line)
        assert parsed["event_id"] == "evt_003"
        assert parsed["sequence"] == 1

    def test_timestamp_format(self) -> None:
        event = EventEnvelope.create(
            event_id="e1",
            run_id="r1",
            sequence=1,
            source="test",
            type=EventType.RUN_CREATED,
        )
        # Should be ISO 8601 with Z suffix
        assert event.timestamp.endswith("Z")
        assert "T" in event.timestamp


class TestManifest:
    def test_create_minimal_manifest(self) -> None:
        m = Manifest.create(run_id="run_test")
        assert m.schema_version == MANIFEST_SCHEMA_VERSION
        assert m.run_id == "run_test"
        assert m.status == RunStatus.CREATED
        assert m.capability_tier == CapabilityTier.PROCESS_WRAPPER
        assert m.created_at != ""

    def test_reject_unknown_top_level_fields(self) -> None:
        with pytest.raises(ValidationError):
            Manifest(
                schema_version="1.0",
                run_id="r",
                created_at="2026-01-01T00:00:00.000Z",
                bogus=True,  # type: ignore[call-arg]
            )

    def test_reject_unknown_repo_fields(self) -> None:
        with pytest.raises(ValidationError):
            RepoInfo(
                source_path="/tmp",
                head_sha="abc",
                mystery="x",  # type: ignore[call-arg]
            )

    def test_status_transitions(self) -> None:
        m = Manifest.create(run_id="run_test")
        assert m.status == RunStatus.CREATED
        m.status = RunStatus.RUNNING
        assert m.status == RunStatus.RUNNING
        m.status = RunStatus.COMPLETED
        assert m.status == RunStatus.COMPLETED

    def test_serialization_roundtrip(self) -> None:
        m = Manifest.create(run_id="run_round")
        m.repo = RepoInfo(
            source_path="/tmp/repo",
            head_sha="abc123",
            dirty_before=False,
        )
        data = m.model_dump()
        m2 = Manifest(**data)
        assert m2.run_id == "run_round"
        assert m2.repo.head_sha == "abc123"

    def test_integrity_map_set(self) -> None:
        im = IntegrityMap()
        im.set("events.jsonl", "sha256:abc")
        im.set("patch.diff", "sha256:def")
        im.set("report.json", "sha256:ghi")
        assert im.events_jsonl == "sha256:abc"
        assert im.patch_diff == "sha256:def"
        assert im.report_json == "sha256:ghi"

    def test_manifest_completed_at(self) -> None:
        m = Manifest.create(run_id="run_comp")
        assert m.completed_at == ""
        m.completed_at = "2026-06-11T14:00:00.000Z"
        assert m.completed_at == "2026-06-11T14:00:00.000Z"
