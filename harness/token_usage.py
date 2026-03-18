"""Token usage and session analysis from Claude Code JSON output and session JSONL files."""
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


# Patterns that indicate a permission/security denial (not a normal runtime error)
_DENIAL_PATTERNS = [
    re.compile(r"This command requires approval"),
    re.compile(r"Permission to use \S+ has been denied"),
    re.compile(r"Permission for this tool use was denied"),
    re.compile(r"Output redirection to .+ was blocked"),
    re.compile(r"Command contains .+"),  # security blocks (substitution, bypass, etc.)
    re.compile(r"This Bash command contains multiple operations"),
]


def _is_permission_denial(error_text: str) -> bool:
    """Check if a tool_result error looks like a permission/security denial."""
    for pat in _DENIAL_PATTERNS:
        if pat.search(error_text):
            return True
    return False


def _find_session_file(session_id: str) -> Path | None:
    """Locate a session JSONL file by session ID."""
    if not session_id:
        return None
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None
    for dirpath, _, filenames in os.walk(claude_dir):
        for fname in filenames:
            if fname == f"{session_id}.jsonl":
                return Path(dirpath) / fname
    return None


def get_denied_tool_calls(session_id: str) -> list:
    """Parse a session JSONL for tool calls that were denied by permissions.

    Returns a list of dicts, each with:
        tool: str       — tool name that was attempted (e.g. "Bash", "WebSearch")
        input_summary: str — abbreviated input (command or first 120 chars)
        error: str      — the denial message (first 200 chars)
    """
    session_file = _find_session_file(session_id)
    if not session_file or not session_file.exists():
        return []

    # Two-pass: first collect all tool_use blocks by ID, then match denials
    tool_uses = {}  # tool_use_id -> {tool, input_summary}
    denied = []

    with open(session_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            content = (
                msg.get("message", {}).get("content")
                if isinstance(msg.get("message"), dict)
                else msg.get("content")
            )
            if not isinstance(content, list):
                continue

            for block in content:
                btype = block.get("type")

                if btype == "tool_use":
                    tool_id = block.get("id", "")
                    tool_name = block.get("name", "unknown")
                    inp = block.get("input", {})
                    if isinstance(inp, dict):
                        summary = inp.get("command", inp.get("query",
                                  inp.get("url", str(inp))))
                    else:
                        summary = str(inp)
                    tool_uses[tool_id] = {
                        "tool": tool_name,
                        "input_summary": str(summary)[:120],
                    }

                elif btype == "tool_result" and block.get("is_error"):
                    error_text = str(block.get("content", ""))
                    if _is_permission_denial(error_text):
                        tool_id = block.get("tool_use_id", "")
                        tool_info = tool_uses.get(tool_id, {
                            "tool": "unknown",
                            "input_summary": "",
                        })
                        denied.append({
                            "tool": tool_info["tool"],
                            "input_summary": tool_info["input_summary"],
                            "error": error_text[:200],
                        })

    return denied
