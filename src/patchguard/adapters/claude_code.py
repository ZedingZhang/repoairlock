"""ClaudeCodeAdapter — Tier 2 adapter with PreToolUse policy enforcement.

Generates temporary, run-scoped hook configurations that enable
PatchGuard to intercept and potentially block Claude Code tool calls
before execution. Does NOT modify the user's global Claude Code settings.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Sequence
from pathlib import Path

from patchguard.adapters.base import AdapterLaunchSpec, AgentAdapter
from patchguard.models.enums import CapabilityTier


class ClaudeCodeAdapter(AgentAdapter):
    """Tier 2 adapter for Claude Code.

    Generates PreToolUse + PostToolUse hook configurations that route
    through a PatchGuard hook handler for policy enforcement and event
    recording. All hook config is scoped to the current run only.
    """

    name = "claude_code"
    version = "0.2.0"

    def __init__(self, *, claude_bin: str = "claude") -> None:
        self._claude = claude_bin

    def build_launch_spec(
        self,
        *,
        workspace: Path,
        user_command: Sequence[str],
        run_id: str,
    ) -> AdapterLaunchSpec:
        """Generate hook config and return launch spec with --settings flag.

        The user_command is passed as the task prompt to Claude Code.
        """
        # Generate temporary hook configuration
        hooks_dir = Path(tempfile.mkdtemp(prefix=f"patchguard-hooks-{run_id}-"))
        settings_path = hooks_dir / "settings.json"
        handler_path = hooks_dir / "hook_handler.py"

        # Write hook handler script
        handler_path.write_text(_HOOK_HANDLER_SCRIPT)

        # Write settings with hooks
        settings = _generate_hook_settings(handler_path)
        settings_path.write_text(json.dumps(settings, indent=2))

        # Build launch arguments
        argv = [
            self._claude,
            "--settings", str(settings_path),
            "--print",  # non-interactive mode
            "--output-format", "stream-json",
        ] + list(user_command)

        redacted = [
            self._claude,
            "--settings", str(settings_path),
            "--print",
            "--output-format", "stream-json",
        ] + list(user_command)

        return AdapterLaunchSpec(
            argv=argv,
            env={},
            capability_tier=CapabilityTier.ENFORCEMENT,
            redacted_argv=redacted,
        )


def _generate_hook_settings(handler_path: Path) -> dict[str, object]:
    """Generate Claude Code hook settings for PreToolUse and PostToolUse."""
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{
                        "type": "command",
                        "command": f"python3 {handler_path}",
                    }],
                },
                {
                    "matcher": "Edit",
                    "hooks": [{
                        "type": "command",
                        "command": f"python3 {handler_path}",
                    }],
                },
                {
                    "matcher": "Write",
                    "hooks": [{
                        "type": "command",
                        "command": f"python3 {handler_path}",
                    }],
                },
            ],
            "PostToolUse": [
                {
                    "matcher": "",
                    "hooks": [{
                        "type": "command",
                        "command": f"python3 {handler_path}",
                    }],
                },
            ],
        },
    }


# -- Hook handler script (embedded as a string, written to temp file at run time) --

_HOOK_HANDLER_SCRIPT = r'''#!/usr/bin/env python3
"""PatchGuard PreToolUse / PostToolUse hook handler.

Reads hook input from stdin (JSON), checks tools against policy engine,
records events, and returns allow/deny decisions.

Environment variables expected:
  PATCHGUARD_EVENTS_PATH — path to the run's events.jsonl
  PATCHGUARD_RUN_ID — the run ID for event recording
"""

import json
import os
import secrets
import sys
from datetime import datetime, timezone


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print(json.dumps({"decision": "allow"}))
            return
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        print(json.dumps({"decision": "allow"}))
        return

    hook_event = hook_input.get("hook_event_name", "")
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    run_id = os.environ.get("PATCHGUARD_RUN_ID", "unknown")
    events_path = os.environ.get("PATCHGUARD_EVENTS_PATH", "")

    if hook_event == "PreToolUse":
        _handle_pre_tool_use(tool_name, tool_input, run_id, events_path)
    elif hook_event in ("PostToolUse", "PostToolUseFailure"):
        _handle_post_tool_use(
            tool_name, tool_input, run_id, events_path,
            success=(hook_event == "PostToolUse"),
        )
    else:
        print(json.dumps({"decision": "allow"}))


def _handle_pre_tool_use(tool_name, tool_input, run_id, events_path):
    # Evaluate against policy
    command = tool_input.get("command", "")
    file_path = tool_input.get("file_path", "")

    # Build evaluation text based on tool type
    if tool_name == "Bash":
        eval_text = command or ""
    elif tool_name in ("Edit", "Write"):
        # For file tools, construct a pseudo-command to match write rules
        eval_text = f"echo content > {file_path}" if file_path else ""
    else:
        eval_text = command or ""

    # Load policy engine and evaluate
    try:
        from patchguard.policy.engine import PolicyEngine
        engine = PolicyEngine.load_defaults()
        results = engine.evaluate_command(eval_text)
        deny_reasons = engine.deny_reasons(results)
        findings = engine.findings(results)
    except Exception:
        deny_reasons = []
        findings = []

    # Record TOOL_REQUESTED event
    _record_event(
        events_path, run_id, "TOOL_REQUESTED",
        {"tool_name": tool_name, "tool_input": str(tool_input)[:500]},
    )

    if deny_reasons:
        # Record TOOL_DENIED
        _record_event(
            events_path, run_id, "TOOL_DENIED",
            {"tool_name": tool_name, "reasons": deny_reasons},
        )
        for finding in findings:
            _record_event(
                events_path, run_id, "POLICY_MATCHED",
                {"finding": finding},
            )
        print(json.dumps({
            "decision": "deny",
            "reason": "; ".join(deny_reasons),
        }))
    else:
        _record_event(
            events_path, run_id, "TOOL_ALLOWED",
            {"tool_name": tool_name},
        )
        print(json.dumps({"decision": "allow"}))


def _handle_post_tool_use(tool_name, tool_input, run_id, events_path, success):
    event_type = "TOOL_COMPLETED" if success else "TOOL_FAILED"
    _record_event(
        events_path, run_id, event_type,
        {"tool_name": tool_name},
    )


def _record_event(events_path, run_id, event_type, payload):
    if not events_path:
        return
    evt = {
        "schema_version": "1.0",
        "event_id": f"evt_{secrets.token_hex(8)}",
        "run_id": run_id,
        "sequence": _next_seq(),
        "timestamp": _now_iso(),
        "source": "hook.handler",
        "type": event_type,
        "payload": payload,
    }
    try:
        with open(events_path, "a") as f:
            f.write(json.dumps(evt, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
    except Exception:
        pass


_seq = [0]


def _next_seq():
    _seq[0] += 1
    return _seq[0]


def _now_iso():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


if __name__ == "__main__":
    main()
'''
