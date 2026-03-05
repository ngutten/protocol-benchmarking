"""Special stage types: translate, refactor, and removal.

These stages don't have spec .md files.  Instead, prompts are generated from
pipeline configuration parameters.  Each type defines:
  - How to build the prompt
  - Which tests to run (carried forward from earlier stages)
  - How to set up the workspace
"""


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

TRANSLATE_PROMPT = """\
Translate the entire codebase from its current language to {target}.

Requirements:
- All existing tests must still pass after translation.
- Preserve the same public API and behavior.
- Translate all source files (not test files).
- Update any build/run commands as needed for the new language.
- Do NOT modify test files — they should work against the translated code.
"""

REFACTOR_PROMPT = """\
Refactor the codebase: {target}

Requirements:
- All existing tests must still pass after refactoring.
- Preserve the same public API and behavior.
- Do NOT modify test files.
"""

REMOVAL_PROMPT = """\
Remove the "{target}" feature from the codebase.

Requirements:
- Tests for OTHER features must still pass.
- Remove all code related to the "{target}" feature.
- Clean up any dead code left behind.
- Do NOT modify test files.
"""


# ---------------------------------------------------------------------------
# Stage type registry
# ---------------------------------------------------------------------------

STAGE_TYPES = {
    "translate": {
        "prompt_template": TRANSLATE_PROMPT,
        "tests": "same",       # run same tests as before
        "description": "Translate codebase to {target}",
    },
    "refactor": {
        "prompt_template": REFACTOR_PROMPT,
        "tests": "same",       # run same tests as before
        "description": "Refactor: {target}",
    },
    "removal": {
        "prompt_template": REMOVAL_PROMPT,
        "tests": "exclude_target",  # run other stages' tests only
        "description": "Remove feature: {target}",
    },
}


def is_special_stage(stage_entry) -> bool:
    """Check if a pipeline stage entry is a special type (not a feature stage)."""
    if isinstance(stage_entry, dict):
        # Check for explicit type field: {type: translate, target: ...}
        if stage_entry.get("type") in STAGE_TYPES:
            return True
        # Check for shorthand: {translate: {target: ...}}
        return any(k in STAGE_TYPES for k in stage_entry)
    return False


def parse_special_stage(stage_entry: dict) -> dict:
    """Parse a special stage entry from pipeline config.

    Handles formats like:
      - {type: translate, target: "c++", id: translate_cpp}
      - {translate: {target: "c++"}}       (shorthand from task.yaml)
      - {refactor: {target: "split into..."}}

    Returns dict with keys: type, target, id
    """
    # Explicit type field
    if "type" in stage_entry and stage_entry["type"] in STAGE_TYPES:
        return {
            "type": stage_entry["type"],
            "target": stage_entry.get("target", ""),
            "id": stage_entry.get("id", f"{stage_entry['type']}_{stage_entry.get('target', 'unknown')[:20]}"),
        }

    # Shorthand: {translate: {target: "c++"}} or {refactor: {target: "..."}}
    for stype in STAGE_TYPES:
        if stype in stage_entry:
            params = stage_entry[stype]
            if isinstance(params, dict):
                target = params.get("target", "")
            else:
                target = str(params)
            # Build a slug-safe ID
            slug = target.lower().replace(" ", "_").replace("+", "plus")[:30]
            return {
                "type": stype,
                "target": target,
                "id": stage_entry.get("id", f"{stype}_{slug}"),
            }

    raise ValueError(f"Unknown special stage format: {stage_entry}")


def build_prompt(stage_type: str, target: str) -> str:
    """Build the prompt for a special stage type."""
    if stage_type not in STAGE_TYPES:
        raise ValueError(f"Unknown stage type: {stage_type}")
    return STAGE_TYPES[stage_type]["prompt_template"].format(target=target)


def get_test_strategy(stage_type: str) -> str:
    """Return the test strategy for a special stage type.

    Returns:
        "same" — run the same tests as the previous stage
        "exclude_target" — run all tests except those for the removed feature
    """
    if stage_type not in STAGE_TYPES:
        return "same"
    return STAGE_TYPES[stage_type]["tests"]


def get_stage_description(stage_type: str, target: str) -> str:
    """Human-readable description for a special stage."""
    if stage_type not in STAGE_TYPES:
        return f"{stage_type}: {target}"
    return STAGE_TYPES[stage_type]["description"].format(target=target)
