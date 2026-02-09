#!/usr/bin/env python3
"""
Precommit hook to validate JSONL bundle files.

Checks:
1. Valid JSON on each line
2. No secrets in content (AWS keys, API tokens, etc.)
3. Handles empty lines gracefully
4. File exists check

Exit codes:
    0 = All files valid
    1 = Errors found
"""
import json
import re
import sys
from pathlib import Path


# Secret patterns to detect
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key
    re.compile(r"sk-[a-z0-9]{48}"),  # OpenAI/Anthropic API key
    re.compile(r"Bearer\s+[a-zA-Z0-9]{20,}"),  # Bearer tokens
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub personal access token
    re.compile(r"xoxb-[0-9]{12}-[0-9]{12}-[0-9]{24}"),  # Slack bot token
]


def check_for_secrets(text: str) -> list[str]:
    """Check text for known secret patterns."""
    found = []
    for pattern in SECRET_PATTERNS:
        matches = pattern.findall(text)
        for match in matches:
            # Truncate long matches for display
            display = match[:50] + "..." if len(match) > 50 else match
            found.append(f"Potential secret: {display}")
    return found


def check_jsonl_file(file_path: Path) -> tuple[int, list[str]]:
    """
    Validate a JSONL file.

    Returns:
        (exit_code, errors)
        exit_code: 0 if valid, 1 if errors
        errors: list of error messages
    """
    errors = []

    # Check if file exists
    if not file_path.exists():
        return 1, [f"File not found: {file_path}"]

    # Check if it's a file (not directory, etc)
    if not file_path.is_file():
        return 1, [f"Not a file: {file_path}"]

    try:
        content = file_path.read_text()
    except OSError as e:
        return 1, [f"Cannot read {file_path}: {e}"]

    lines = content.splitlines()
    for line_num, line in enumerate(lines, start=1):
        # Skip empty lines
        if not line.strip():
            continue

        # Validate JSON
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"Line {line_num}: Invalid JSON - {e}")
            continue

        # Check for secrets in all string values
        text_content = json.dumps(data)
        secrets = check_for_secrets(text_content)
        for secret in secrets:
            errors.append(f"Line {line_num}: {secret}")

    if errors:
        return 1, errors
    return 0, []


def main():
    """Entry point for precommit hook."""
    if len(sys.argv) < 2:
        print("Usage: check_bundle_integrity.py <file.jsonl> [...]", file=sys.stderr)
        sys.exit(1)

    exit_code = 0
    all_errors = []

    for file_arg in sys.argv[1:]:
        file_path = Path(file_arg)

        # Only check JSONL files
        if not file_path.suffix == ".jsonl":
            continue

        code, errors = check_jsonl_file(file_path)

        if code != 0:
            exit_code = code
            print(f"\n❌ {file_path}:", file=sys.stderr)
            for error in errors:
                print(f"   {error}", file=sys.stderr)
            all_errors.extend(errors)

    if exit_code != 0:
        print(f"\n❌ Bundle integrity check failed", file=sys.stderr)
        print(f"   Found {len(all_errors)} error(s)", file=sys.stderr)
        sys.exit(exit_code)

    sys.exit(0)


if __name__ == "__main__":
    main()
