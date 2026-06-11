"""Policy data models — Pydantic v2, extra=forbid, schema versioned."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

POLICY_SCHEMA_VERSION = "1.0"


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"
    ALLOW_SANDBOX_ONLY = "allow_sandbox_only"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RuleMatch(BaseModel):
    """Match condition for a policy rule. Exactly one of the optional fields
    should be populated, depending on the rule's applies_to target."""

    model_config = ConfigDict(extra="forbid")

    regex: str | None = None
    path: str | None = None
    flag: str | None = None
    docker_param: str | None = None


class PolicyRule(BaseModel):
    """A single policy rule. Unknown fields are rejected (fail-closed)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    applies_to: str
    match: RuleMatch
    decision: PolicyDecision
    severity: RiskLevel
    reason: str


class PolicyRuleset(BaseModel):
    """A versioned collection of policy rules."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = POLICY_SCHEMA_VERSION
    rules: list[PolicyRule]


class PolicyResult(BaseModel):
    """The result of evaluating a single rule against an input."""

    rule_id: str
    decision: PolicyDecision
    severity: RiskLevel
    reason: str
    matched: bool

    @classmethod
    def not_matched(cls, rule: PolicyRule) -> PolicyResult:
        return cls(
            rule_id=rule.id,
            decision=PolicyDecision.ALLOW,
            severity=rule.severity,
            reason=f"Rule {rule.id} did not match",
            matched=False,
        )

    @classmethod
    def hit(cls, rule: PolicyRule) -> PolicyResult:
        return cls(
            rule_id=rule.id,
            decision=rule.decision,
            severity=rule.severity,
            reason=rule.reason,
            matched=True,
        )
