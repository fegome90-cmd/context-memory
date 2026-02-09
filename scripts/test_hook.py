#!/usr/bin/env python3
"""Simple test hook to verify execution."""

import sys
import json
from pathlib import Path

# Log to file for debugging
log_file = Path("/tmp/cm_hook_execution.log")
log_file.parent.mkdir(parents=True, exist_ok=True)

with open(log_file, "a") as f:
    f.write("\n=== HOOK CALLED ===\n")
    try:
        # Read stdin
        input_data = json.load(sys.stdin)
        f.write(f"Input received: {json.dumps(input_data)[:500]}\n")
    except Exception as e:
        f.write(f"Error: {e}\n")

# Exit successfully
sys.exit(0)
