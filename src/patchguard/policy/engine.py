"""PolicyEngine — loads rules, evaluates against configuration, returns findings."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml

from patchguard.policy.models import (
    POLICY_SCHEMA_VERSION,
    PolicyDecision,
    PolicyResult,
    PolicyRule,
    PolicyRuleset,
)
from patchguard.policy.rules import evaluate_docker_config, evaluate_text_input


class PolicyEngine:
    """Loads and evaluates a set of policy rules.

    For MVP (Tier 0): evaluates Docker sandbox configuration before
    container creation. Does NOT intercept agent tool calls.
    """

    def __init__(self, rules: Sequence[PolicyRule] | None = None) -> None:
        self._rules = list(rules) if rules else []

    @classmethod
    def from_yaml(cls, path: Path) -> PolicyEngine:
        """Load rules from a YAML file. Rejects unknown fields (fail-closed)."""
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("Policy YAML must be a dict with 'schema_version' and 'rules'")
        ruleset = PolicyRuleset(**data)
        if ruleset.schema_version != POLICY_SCHEMA_VERSION:
            raise ValueError(
                f"Unknown policy schema version: {ruleset.schema_version}"
            )
        return cls(rules=ruleset.rules)

    @classmethod
    def load_defaults(cls) -> PolicyEngine:
        """Load the built-in default rules."""
        default_path = Path(__file__).parent / "defaults.yaml"
        return cls.from_yaml(default_path)

    @property
    def rules(self) -> list[PolicyRule]:
        return list(self._rules)

    def evaluate_sandbox(
        self,
        *,
        network: str = "none",
        privileged: bool = False,
        mounts: list[str] | None = None,
    ) -> list[PolicyResult]:
        """Evaluate all rules against the given Docker sandbox configuration.

        Returns a list of PolicyResult, one per rule.
        """
        results: list[PolicyResult] = []
        for rule in self._rules:
            result = evaluate_docker_config(
                rule,
                network=network,
                privileged=privileged,
                mounts=mounts,
            )
            results.append(result)
        return results

    def evaluate_command(self, command: str) -> list[PolicyResult]:
        """Evaluate all rules against a command string.

        For Tier 0, this is informational only — enforcement happens
        in Tier 2 with PreToolUse hooks.
        """
        results: list[PolicyResult] = []
        for rule in self._rules:
            if rule.applies_to in ("bash", "command", "shell"):
                result = evaluate_text_input(rule, command)
                results.append(result)
        return results

    def any_denied(self, results: list[PolicyResult]) -> bool:
        return any(
            r.matched and r.decision == PolicyDecision.DENY for r in results
        )

    def deny_reasons(self, results: list[PolicyResult]) -> list[str]:
        return [
            f"[{r.severity.value.upper()}] {r.reason}"
            for r in results
            if r.matched and r.decision == PolicyDecision.DENY
        ]

    def findings(self, results: list[PolicyResult]) -> list[str]:
        """Return human-readable findings for matched rules."""
        return [
            f"[{r.severity.value.upper()}] {r.rule_id}: {r.reason}"
            for r in results
            if r.matched
        ]
