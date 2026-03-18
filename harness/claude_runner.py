"""Claude Code invocation for headless and interactive benchmark runs."""
import shlex
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from .token_usage import parse_claude_json_output, get_session_token_usage, get_denied_tool_calls


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


def _collect_denied(session_ids):
    """Collect denied tool calls across one or more session IDs."""
    denied = []
    for sid in session_ids:
        if sid:
            denied.extend(get_denied_tool_calls(sid))
    return denied


@dataclass
class PhaseResult:
    """Result data from a single phase execution."""
    phase_name: str
    session_ids: list = field(default_factory=list)
    result: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    wall_time_seconds: float = 0.0
    is_error: bool = False
    sub_results: list = None  # For parallel phases

    def to_dict(self):
        d = {
            "phase_name": self.phase_name,
            "session_ids": self.session_ids,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "wall_time_seconds": self.wall_time_seconds,
            "is_error": self.is_error,
        }
        if self.sub_results is not None:
            d["sub_results"] = [sr.to_dict() for sr in self.sub_results]
        return d


class _SafeFormatDict(dict):
    """Dict subclass that returns the key placeholder for missing keys.

    Used with str.format_map() so that template strings with unresolved
    placeholders (e.g. {future_var}) don't raise KeyError.
    """
    def __missing__(self, key):
        return "{" + key + "}"


def _run_phase(phase, prompt_text, work_dir, protocol, timeout):
    """Execute a single phase as a ``claude -p`` call and return a PhaseResult.

    Extracts the existing "build cmd, run, backfill" pattern into a reusable
    function.
    """
    model = phase.model or protocol.model
    perm = phase.permission_mode or "acceptEdits"

    # Build command — use the protocol's tool list, but override model/permission
    cmd = ["claude"]
    cmd.extend(["--model", model])
    cmd.extend(["--permission-mode", perm])
    for tool in protocol.get_allowed_tools():
        cmd.extend(["--allowedTools", tool])
    cmd.extend(["--output-format", "json"])
    cmd.extend(["-p", prompt_text])

    phase_timeout = phase.timeout or timeout
    parsed, wall_time = _run_claude_p(cmd, work_dir, timeout=phase_timeout)
    _backfill_usage(parsed)

    pr = PhaseResult(
        phase_name=phase.name,
        session_ids=[parsed.get("session_id", "")],
        result=parsed.get("result", ""),
        input_tokens=parsed.get("input_tokens", 0),
        output_tokens=parsed.get("output_tokens", 0),
        total_tokens=parsed.get("total_tokens", 0),
        cache_read_tokens=parsed.get("cache_read_tokens", 0),
        cache_creation_tokens=parsed.get("cache_creation_tokens", 0),
        wall_time_seconds=wall_time,
        is_error=parsed.get("is_error", False),
    )
    return pr


def _run_parallel_phase(phase, work_dir, protocol, timeout):
    """Execute parallel_prompts concurrently and return an aggregate PhaseResult.

    Wall time = max of sub-agents; tokens = sum.
    """
    prompts = phase.parallel_prompts or []
    sub_results = []

    def _run_one(idx, prompt_text):
        sub_phase_name = f"{phase.name}_{idx}"
        # Create a lightweight "sub-phase" to reuse _run_phase
        from .protocols import PhaseDef
        sub_phase = PhaseDef(
            name=sub_phase_name,
            prompt_template=prompt_text,
            permission_mode=phase.permission_mode,
            model=phase.model,
            timeout=phase.timeout,
        )
        return _run_phase(sub_phase, prompt_text, work_dir, protocol, timeout)

    with ThreadPoolExecutor(max_workers=len(prompts)) as executor:
        futures = {
            executor.submit(_run_one, i, p): i
            for i, p in enumerate(prompts)
        }
        for future in as_completed(futures):
            sub_results.append(future.result())

    # Sort by index-embedded name to keep deterministic order
    sub_results.sort(key=lambda r: r.phase_name)

    # Aggregate: wall time = max, tokens = sum
    agg = PhaseResult(
        phase_name=phase.name,
        session_ids=[],
        sub_results=sub_results,
    )
    for sr in sub_results:
        agg.session_ids.extend(sr.session_ids)
        agg.input_tokens += sr.input_tokens
        agg.output_tokens += sr.output_tokens
        agg.total_tokens += sr.total_tokens
        agg.cache_read_tokens += sr.cache_read_tokens
        agg.cache_creation_tokens += sr.cache_creation_tokens
        agg.is_error = agg.is_error or sr.is_error
    agg.wall_time_seconds = max((sr.wall_time_seconds for sr in sub_results), default=0.0)
    # Combine results text
    agg.result = "\n---\n".join(
        f"[{sr.phase_name}] {sr.result}" for sr in sub_results
    )
    return agg


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

    # Track session IDs from all invocations for denied-tool-call analysis
    all_session_ids = []

    # --- Custom command path: delegate entirely to the user-defined command ---
    if protocol.custom_command:
        cmd = _expand_custom_command(protocol, prompt, work_dir)
        parsed, wall_time = _run_claude_p(cmd, work_dir, timeout=timeout)
        _backfill_usage(parsed)
        combined.update(parsed)
        combined["wall_time_seconds"] = wall_time
        all_session_ids.append(parsed.get("session_id", ""))
        combined["denied_tool_calls"] = _collect_denied(all_session_ids)
        return combined

    # --- Multi-phase pipeline: iterate through protocol.phases ---
    if protocol.phases:
        phase_context = _SafeFormatDict(prompt=prompt, prev_result="")
        phase_breakdown = []

        for phase in protocol.phases:
            if phase.parallel_prompts:
                pr = _run_parallel_phase(phase, work_dir, protocol, timeout)
            else:
                prompt_text = phase.prompt_template.format_map(phase_context)
                pr = _run_phase(phase, prompt_text, work_dir, protocol, timeout)

            total_wall += pr.wall_time_seconds
            all_session_ids.extend(pr.session_ids)
            _merge_token_data(combined, {
                "input_tokens": pr.input_tokens,
                "output_tokens": pr.output_tokens,
                "total_tokens": pr.total_tokens,
                "cache_read_tokens": pr.cache_read_tokens,
                "cache_creation_tokens": pr.cache_creation_tokens,
            })
            phase_breakdown.append(pr.to_dict())

            # Update context for subsequent phases
            if pr.pass_result:
                phase_context[f"phase_{phase.name}"] = pr.result
                phase_context["prev_result"] = pr.result

            # Update combined result to reflect latest phase
            combined["session_id"] = pr.session_ids[-1] if pr.session_ids else ""
            combined["result"] = pr.result

            if pr.is_error:
                combined["is_error"] = True
                combined["result"] = f"PHASE_{phase.name.upper()}_ERROR: {pr.result}"
                break

        combined["wall_time_seconds"] = total_wall
        combined["denied_tool_calls"] = _collect_denied(all_session_ids)
        combined["phase_breakdown"] = phase_breakdown
        combined["all_session_ids"] = all_session_ids
        return combined

    elif protocol.planning_phase and protocol.planning_prompt:
        # --- Phase 1: Planning (read-only) ---
        plan_cmd = _build_base_cmd(protocol, permission_mode="plan")
        plan_cmd.extend(["-p", protocol.planning_prompt])

        plan_parsed, plan_wall = _run_claude_p(plan_cmd, work_dir, timeout=timeout)
        _backfill_usage(plan_parsed)
        total_wall += plan_wall
        all_session_ids.append(plan_parsed.get("session_id", ""))

        _merge_token_data(combined, plan_parsed)

        if plan_parsed.get("is_error"):
            combined["is_error"] = True
            combined["result"] = f"PLAN_ERROR: {plan_parsed.get('result', '')}"
            combined["wall_time_seconds"] = total_wall
            combined["denied_tool_calls"] = _collect_denied(all_session_ids)
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
        all_session_ids.append(impl_parsed.get("session_id", ""))

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
        all_session_ids.append(parsed.get("session_id", ""))

        combined.update(parsed)

    combined["wall_time_seconds"] = total_wall
    combined["denied_tool_calls"] = _collect_denied(all_session_ids)
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
