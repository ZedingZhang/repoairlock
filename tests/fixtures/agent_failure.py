#!/usr/bin/env python3
"""Fixture agent: exits with non-zero code.

Simulates a coding agent that encounters an error.
"""
import sys

print("Agent encountered an error", file=sys.stderr)
sys.exit(1)
