#!/usr/bin/env python3
"""Fixture agent: sleeps indefinitely to trigger timeout."""
import time

print("Agent starting (will timeout)...")
time.sleep(99999)
print("This should never print")
