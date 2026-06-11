"""Event models for AgentFence."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EVENT_SCHEMA_VERSION = "1.0"


class EventType(StrEnum):
    RUN_CREATED = "RUN_CREATED"
    RUN_PREPARING = "RUN_PREPARING"
    SOURCE_FINGERPRINT_CAPTURED = "SOURCE_FINGERPRINT_CAPTURED"
    WORKTREE_CREATED = "WORKTREE_CREATED"
    SANDBOX_STARTING = "SANDBOX_STARTING"
    PROCESS_STARTED = "PROCESS_STARTED"
    STDOUT_CHUNK = "STDOUT_CHUNK"
    STDERR_CHUNK = "STDERR_CHUNK"
    RESOURCE_SAMPLE = "RESOURCE_SAMPLE"
    PROCESS_EXITED = "PROCESS_EXITED"
    PATCH_EXPORTED = "PATCH_EXPORTED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_FINISHED = "VERIFICATION_FINISHED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    REPORT_GENERATED = "REPORT_GENERATED"
    WORKTREE_REMOVED = "WORKTREE_REMOVED"
    SANDBOX_REMOVED = "SANDBOX_REMOVED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"
    RUN_TIMED_OUT = "RUN_TIMED_OUT"
    RUN_CANCELLED = "RUN_CANCELLED"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
    # v0.2 Tier 2 events
    TOOL_REQUESTED = "TOOL_REQUESTED"
    TOOL_ALLOWED = "TOOL_ALLOWED"
    TOOL_DENIED = "TOOL_DENIED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    TOOL_FAILED = "TOOL_FAILED"
    POLICY_MATCHED = "POLICY_MATCHED"
    USER_CONFIRMATION_REQUIRED = "USER_CONFIRMATION_REQUIRED"


class EventPayload(BaseModel):
    """Base payload for an event. Specific event types extend with extra fields."""

    model_config = ConfigDict(extra="allow")


class EventEnvelope(BaseModel):
    """A single event record written to events.jsonl."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = Field(default="1.0")
    event_id: str
    run_id: str
    sequence: int = Field(ge=1)
    timestamp: str
    source: str
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        run_id: str,
        sequence: int,
        source: str,
        type: EventType,
        payload: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        ts = _now_iso()
        return cls(
            event_id=event_id,
            run_id=run_id,
            sequence=sequence,
            timestamp=ts,
            source=source,
            type=type,
            payload=payload or {},
        )


def _now_iso() -> str:
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
