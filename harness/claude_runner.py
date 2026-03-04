"""Claude Code invocation for headless and interactive benchmark runs."""
import shlex
import subprocess
import time
from .token_usage import parse_claude_json_output, get_session_token_usage


def _build_base_cmd(protocol, permission_mode="acceptEdits"):
    """Build the base claude command with model, permissions, and allowed tools.

    Args:
        protocol: ProtocolDef instance.
        permission_mode: One of "plan", "acceptEdits", "default", "dontAsk".

    Returns:
        List of command parts (without -p / prompt).
    """
    cmd = ["claude"]
    cmd.extend(["--model", protocol.model])
    cmd.extend(["--permission-mode", permission_mode])

    for tool in protocol.get_allowed_tools():
        cmd.extend(["--allowedTools", tool])

    cmd.extend(["--output-format", "json"])
    return cmd


def _expand_custom_command(protocol, prompt, work_dir):
    """Expand {prompt} and {work_dir} placeholders in a custom_command.

    Returns a new list with placeholders substituted.
    """
    expanded = []
    for part in protocol.custom_command:
        expanded.append(
            part.replace("{prompt}", prompt).replace("{work_dir}", str(work_dir))
        )
    return expanded


def _run_claude_p(cmd, work_dir, timeout=None):
    """Execute a claude -p command and return parsed output + timing.

    Returns (parsed_dict, wall_time_seconds).
    """
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=timeout,
        )
        wall_time = time.time() - start
        return parse_claude_json_output(result.stdout), wall_time
    except subprocess.TimeoutExpired:
        wall_time = time.time() - start
        return {
            "result": "TIMEOUT",
            "session_id": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "is_error": True,
        }, wall_time


def _backfill_usage(parsed):
    """If JSON output had no usage, try session JSONL as fallback."""
    if parsed["total_tokens"] == 0 and parsed.get("session_id"):
        session_usage = get_session_token_usage(parsed["session_id"])
        if session_usage["total_tokens"] > 0:
            parsed.update(session_usage)


def _merge_token_data(a, b):
    """Sum token fields from two parsed dicts into a."""
    for key in ("input_tokens", "output_tokens", "total_tokens",
                "cache_read_tokens", "cache_creation_tokens"):
        a[key] = a.get(key, 0) + b.get(key, 0)


def run_headless(work_dir, prompt, protocol, timeout=None):
    """Run Claude Code in headless mode via `claude -p`.

    If the protocol defines a custom_command, that command is used instead
    of the internally generated claude invocation.  The placeholders
    {prompt} and {work_dir} in custom_command elements are substituted.

    For protocols with a planning phase (and no custom_command), this runs
    TWO invocations:
      1. Plan phase: --permission-mode plan with the planning prompt
      2. Implementation phase: --permission-mode acceptEdits with the
         implementation prompt, starting fresh

    For protocols without planning, runs a single invocation with
    --permission-mode acceptEdits.

    Args:
        work_dir: Working directory for the Claude session.
        prompt: The implementation prompt (used for non-planning protocols
                or as the second prompt for planning protocols).
        protocol: ProtocolDef instance (for model, tools, planning config).
        timeout: Max seconds to wait per invocation (None = no limit).

    Returns:
        Dict with session_id, result, input_tokens, output_tokens,
        total_tokens, cache_read_tokens, cache_creation_tokens, is_error,
        wall_time_seconds.
    """
    total_wall = 0.0

    # Aggregate token data across invocations
    combined = {
        "session_id": "",
        "result": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "is_error": False,
        "wall_time_seconds": 0.0,
    }

    # --- Custom command path: delegate entirely to the user-defined command ---
    if protocol.custom_command:
        cmd = _expand_custom_command(protocol, prompt, work_dir)
        parsed, wall_time = _run_claude_p(cmd, work_dir, timeout=timeout)
        _backfill_usage(parsed)
        combined.update(parsed)
        combined["wall_time_seconds"] = wall_time
        return combined

    if protocol.planning_phase and protocol.planning_prompt:
        # --- Phase 1: Planning (read-only) ---
        plan_cmd = _build_base_cmd(protocol, permission_mode="plan")
        plan_cmd.extend(["-p", protocol.planning_prompt])

        plan_parsed, plan_wall = _run_claude_p(plan_cmd, work_dir, timeout=timeout)
        _backfill_usage(plan_parsed)
        total_wall += plan_wall

        _merge_token_data(combined, plan_parsed)

        if plan_parsed.get("is_error"):
            combined["is_error"] = True
            combined["result"] = f"PLAN_ERROR: {plan_parsed.get('result', '')}"
            combined["wall_time_seconds"] = total_wall
            return combined

        # Store plan result for context (the CLAUDE.md already has the plan prompt,
        # and Claude will see the planning output in its session history if we resume,
        # but since we're doing a fresh -p call, we embed the plan in the prompt)
        plan_result = plan_parsed.get("result", "")

        # --- Phase 2: Implementation (with edits) ---
        impl_prompt = f"Here is the plan from the planning phase:\n\n{plan_result}\n\n{prompt}"
        impl_cmd = _build_base_cmd(protocol, permission_mode="acceptEdits")
        impl_cmd.extend(["-p", impl_prompt])

        impl_parsed, impl_wall = _run_claude_p(impl_cmd, work_dir, timeout=timeout)
        _backfill_usage(impl_parsed)
        total_wall += impl_wall

        _merge_token_data(combined, impl_parsed)
        combined["session_id"] = impl_parsed.get("session_id", "")
        combined["result"] = impl_parsed.get("result", "")
        combined["is_error"] = impl_parsed.get("is_error", False)

    else:
        # --- Single invocation: straight to implementation ---
        cmd = _build_base_cmd(protocol, permission_mode="acceptEdits")
        cmd.extend(["-p", prompt])

        parsed, wall_time = _run_claude_p(cmd, work_dir, timeout=timeout)
        _backfill_usage(parsed)
        total_wall += wall_time

        combined.update(parsed)

    combined["wall_time_seconds"] = total_wall
    return combined


def run_interactive(work_dir, prompt, protocol, session_id=None):
    """Run an interactive Claude session with human operator.

    Prints instructions, waits for the human to complete the session,
    then scrapes token usage from the session JSONL.

    If the protocol defines a custom_command, it is shown to the operator
    (with placeholders expanded) instead of the default claude command.

    Args:
        work_dir: Working directory for the Claude session.
        prompt: Description of what the session should accomplish.
        protocol: ProtocolDef instance (for model info in printed instructions).
        session_id: Optional session ID to resume.

    Returns:
        Same dict shape as run_headless.
    """
    print(f"\n{'='*60}")
    print("INTERACTIVE CLAUDE SESSION")
    print(f"{'='*60}")
    print(f"\nModel: {protocol.model}")
    print(f"Working directory: {work_dir}")
    print(f"\nPrompt for this stage:\n{prompt}")

    if protocol.custom_command:
        expanded = _expand_custom_command(protocol, prompt, work_dir)
        print(f"\nRun your custom command:")
        print(f"  {shlex.join(expanded)}")
    elif session_id:
        print(f"\nResume previous session:")
        print(f"  claude --resume {session_id}")
    else:
        print(f"\nStart a new session:")
        print(f"  cd {work_dir} && claude --model {protocol.model}")

    print(f"\nPaste the session ID here when done (or leave blank):")

    start = time.time()
    entered_id = input("Session ID> ").strip()
    wall_time = time.time() - start

    sid = entered_id or session_id or ""

    # Try to get token usage from session JSONL
    usage = get_session_token_usage(sid) if sid else {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }

    return {
        "session_id": sid,
        "result": "interactive_session",
        "is_error": False,
        "wall_time_seconds": wall_time,
        **usage,
    }
