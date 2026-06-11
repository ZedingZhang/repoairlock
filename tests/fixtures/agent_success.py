#!/usr/bin/env python3
"""Fixture agent: modifies a file and exits 0.

Simulates a coding agent that successfully patches a file.
Expects the workspace to contain hello.py.
"""
import sys
from pathlib import Path

workspace = Path("/workspace")
target = workspace / "hello.py"
if target.exists():
    content = target.read_text()
    content = content.replace("Hello, World!", "Hello, PatchGuard!")
    target.write_text(content)
    print(f"Patched {target.name}")
else:
    print("hello.py not found — creating it")
    target.write_text('print("Hello, PatchGuard!")\n')
sys.exit(0)
