"""Quality score — placeholder module.

v0.3 will introduce an experimental process_quality_score.
MVP explicitly does NOT output a pseudo-precise total score.
"""

from __future__ import annotations


def compute_quality_findings(
    *,
    capability_tier: str,
    diff_metrics: dict[str, object],
    trajectory_metrics: dict[str, object],
    sandbox_config: dict[str, object],
) -> list[str]:
    """Return a list of quality findings as human-readable strings.

    Currently returns capability-tier-aware boilerplate. Will be expanded
    in v0.3 with heuristic rules (churn, repeated failures, etc.).
    """
    findings: list[str] = []

    # Capability tier notice
    if capability_tier == "tier_0_process_wrapper":
        findings.append(
            "Tier 0 (Process Wrapper): agent internal tool calls, "
            "LLM token usage, and per-command reasoning are NOT observable. "
            "Quality conclusions are limited to process-level metrics."
        )

    # Safety findings
    network = sandbox_config.get("network", "none")
    if network == "none":
        findings.append("Network was disabled — no data exfiltration risk via network.")
    else:
        findings.append(f"Network mode: {network} — agent had network access.")

    # Patch findings
    files = diff_metrics.get("files_changed", 0)
    if isinstance(files, int) and files == 0:
        findings.append("No files were changed by the agent.")
    touched = diff_metrics.get("touched_sensitive_paths", [])
    if isinstance(touched, list) and touched:
        findings.append(f"Agent touched sensitive paths: {touched}")

    # Verifier
    verifier_passed = trajectory_metrics.get("verifier_passed")
    if verifier_passed is True:
        findings.append("Verification passed — agent changes passed the user-supplied verifier.")
    elif verifier_passed is False:
        findings.append("Verification FAILED — agent changes did NOT pass the verifier.")

    return findings
