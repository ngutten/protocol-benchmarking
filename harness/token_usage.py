"""Token usage parsing from Claude Code JSON output and session JSONL files."""
import json
import os
import re
from pathlib import Path


def parse_claude_json_output(output: str) -> dict:
    """Extract result, session_id, and usage from `claude -p --output-format json` output.

    Returns dict with keys: result, session_id, input_tokens, output_tokens,
    total_tokens, cache_read_tokens, cache_creation_tokens, is_error.
    """
    info = {
        "result": "",
        "session_id": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "is_error": False,
    }
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        info["is_error"] = True
        info["result"] = str(output)
        return info

    info["result"] = data.get("result", "")
    info["session_id"] = data.get("session_id", "")
    info["is_error"] = data.get("is_error", False)

    # Usage may be at top level or nested under "usage"
    usage = data.get("usage", data)
    info["input_tokens"] = usage.get("input_tokens", 0)
    info["output_tokens"] = usage.get("output_tokens", 0)
    info["cache_read_tokens"] = usage.get("cache_read_input_tokens", 0)
    info["cache_creation_tokens"] = usage.get("cache_creation_input_tokens", 0)
    info["total_tokens"] = info["input_tokens"] + info["output_tokens"]

    return info


def get_session_token_usage(session_id: str, project_dir: str = None) -> dict:
    """Parse a Claude session JSONL file for token usage.

    Searches for session files in ~/.claude/projects/<encoded-path>/<session_id>.jsonl
    and sums up all usage fields across messages.

    Returns dict with keys: input_tokens, output_tokens, total_tokens,
    cache_read_tokens, cache_creation_tokens.
    """
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }

    if not session_id:
        return usage

    # Search for session JSONL files
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return usage

    session_file = None
    for dirpath, _, filenames in os.walk(claude_dir):
        for fname in filenames:
            if fname == f"{session_id}.jsonl":
                session_file = Path(dirpath) / fname
                break
        if session_file:
            break

    if not session_file or not session_file.exists():
        return usage

    with open(session_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_usage = msg.get("message", {}).get("usage", {}) if isinstance(msg.get("message"), dict) else msg.get("usage", {})
            if msg_usage:
                usage["input_tokens"] += msg_usage.get("input_tokens", 0)
                usage["output_tokens"] += msg_usage.get("output_tokens", 0)
                usage["cache_read_tokens"] += msg_usage.get("cache_read_input_tokens", 0)
                usage["cache_creation_tokens"] += msg_usage.get("cache_creation_input_tokens", 0)

    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return usage
