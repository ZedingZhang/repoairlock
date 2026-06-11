"""Policy rule evaluators — check inputs against individual rules.

For Tier 0, these check Docker sandbox configuration parameters,
not agent tool calls (that requires Tier 2).
"""

from __future__ import annotations

import re

from patchguard.policy.models import PolicyResult, PolicyRule


def evaluate_docker_param(rule: PolicyRule) -> PolicyResult:
    """Evaluate a rule against Docker configuration parameters.

    Rules with applies_to='docker' or 'mount' check specific Docker params.
    """
    flag = rule.match.flag
    if flag:
        return PolicyResult.hit(rule)

    path = rule.match.path
    if path:
        # Check if the path matches forbidden mount paths
        if path in ("/var/run/docker.sock", "/"):
            return PolicyResult.hit(rule)
        if path.endswith("docker.sock"):
            return PolicyResult.hit(rule)
        return PolicyResult.not_matched(rule)

    return PolicyResult.not_matched(rule)


def evaluate_text_input(rule: PolicyRule, command: str) -> PolicyResult:
    """Evaluate a rule against a text input (e.g., command string).

    Rules with applies_to='bash' or 'command' check regex patterns.
    """
    regex = rule.match.regex
    if not regex:
        return PolicyResult.not_matched(rule)

    try:
        if re.search(regex, command, re.IGNORECASE | re.DOTALL):
            return PolicyResult.hit(rule)
    except re.error:
        return PolicyResult.not_matched(rule)

    return PolicyResult.not_matched(rule)


def evaluate_docker_config(
    rule: PolicyRule,
    *,
    network: str = "none",
    privileged: bool = False,
    mounts: list[str] | None = None,
) -> PolicyResult:
    """Evaluate a rule against Docker sandbox configuration.

    This is the Tier 0 enforcement point: PatchGuard's own Docker
    parameters are checked before container creation.
    """
    # Check forbidden flags
    if rule.match.flag:
        if rule.match.flag == "--privileged" and privileged:
            return PolicyResult.hit(rule)
        if rule.match.flag == "--network host" and network == "host":
            return PolicyResult.hit(rule)
        if rule.match.flag == "--pid host":
            return PolicyResult.not_matched(rule)  # never set by PatchGuard
        if rule.match.flag == "--ipc host":
            return PolicyResult.not_matched(rule)  # never set by PatchGuard
        return PolicyResult.not_matched(rule)

    # Check forbidden mounts — match exact src= value
    if rule.match.path:
        for m in (mounts or []):
            target = f"src={rule.match.path}"
            # Match src=<path> when followed by , or end of string
            if target + "," in m or m.endswith(target):
                return PolicyResult.hit(rule)
        return PolicyResult.not_matched(rule)

    # Check Docker parameters
    if rule.match.docker_param:
        if rule.match.docker_param == "privileged" and privileged:
            return PolicyResult.hit(rule)
        if rule.match.docker_param == "host_network" and network == "host":
            return PolicyResult.hit(rule)
        return PolicyResult.not_matched(rule)

    return PolicyResult.not_matched(rule)
