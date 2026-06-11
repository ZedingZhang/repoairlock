"""Domain enums for PatchGuard."""

from enum import StrEnum


class RunStatus(StrEnum):
    CREATED = "created"
    PREPARING = "preparing"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    POLICY_BLOCKED = "policy_blocked"


class CapabilityTier(StrEnum):
    PROCESS_WRAPPER = "tier_0_process_wrapper"
    STRUCTURED_EVENTS = "tier_1_structured_events"
    ENFORCEMENT = "tier_2_enforcement"
