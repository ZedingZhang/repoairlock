"""EventRecorder — writes structured events to a run's events.jsonl."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from patchguard.artifacts.store import ArtifactStore
from patchguard.models.enums import RunStatus
from patchguard.models.events import EventEnvelope, EventType
from patchguard.models.manifest import Manifest


class EventRecorder:
    """Records structured events into a run's events.jsonl.

    Maintains a monotonic sequence counter and generates unique event IDs.
    """

    def __init__(self, store: ArtifactStore, run_id: str) -> None:
        self._store = store
        self._run_id = run_id
        self._sequence = 0

    @property
    def sequence(self) -> int:
        return self._sequence

    def record(
        self,
        *,
        type: EventType,
        source: str,
        payload: dict[str, object] | None = None,
    ) -> EventEnvelope:
        """Record a single event, incrementing the sequence counter."""
        self._sequence += 1
        event = EventEnvelope.create(
            event_id=_generate_event_id(),
            run_id=self._run_id,
            sequence=self._sequence,
            source=source,
            type=type,
            payload=payload or {},
        )
        self._store.append_event(event.model_dump())
        return event


def record_run_created(recorder: EventRecorder, manifest: Manifest) -> None:
    """Write the RUN_CREATED event and initial manifest."""
    recorder.record(
        type=EventType.RUN_CREATED,
        source="harness.core",
    )


def record_run_failed(
    recorder: EventRecorder,
    manifest: Manifest,
    error_message: str,
    phase: str,
) -> None:
    """Write a RUN_FAILED event and finalize the manifest in best-effort."""
    manifest.status = RunStatus.FAILED
    manifest.completed_at = _now_iso()
    recorder.record(
        type=EventType.RUN_FAILED,
        source="harness.core",
        payload={"error": error_message, "phase": phase},
    )


def _now_iso() -> str:
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _generate_event_id() -> str:
    return f"evt_{secrets.token_hex(8)}"
