"""Protocol definitions for the benchmark.

Each protocol defines how a stage should be executed, what files the LLM sees,
and what instructions the human operator gets.
"""
from dataclasses import dataclass, field
from typing import Optional


# Default tools that are always allowed in headless mode.
# These cover common dev operations without being dangerous.
DEFAULT_ALLOWED_TOOLS = [
    # File operations (Claude built-in tools)
    "Read",
    "Edit",
    "Write",
    "Glob",
    "Grep",
    # Git (needed for parallel task merge conflict tracking)
    "Bash(git add *)",
    "Bash(git commit *)",
    "Bash(git status *)",
    "Bash(git diff *)",
    "Bash(git log *)",
    "Bash(git branch *)",
    "Bash(git checkout *)",
    "Bash(git merge *)",
    "Bash(git tag *)",
    "Bash(git stash *)",
    # Common safe dev tools
    "Bash(wc *)",
    "Bash(head *)",
    "Bash(tail *)",
    "Bash(sort *)",
    "Bash(uniq *)",
    "Bash(diff *)",
    "Bash(cat *)",
    "Bash(ls *)",
    "Bash(find *)",
    "Bash(mkdir *)",
    "Bash(cp *)",
    "Bash(mv *)",
    "Bash(rm *)",
    "Bash(touch *)",
    "Bash(chmod *)",
    "Bash(echo *)",
    "Bash(printf *)",
    "Bash(test *)",
    "Bash([ *)",
    "Bash(true)",
    "Bash(false)",
    # Python
    "Bash(python3 *)",
    "Bash(python *)",
    "Bash(pytest *)",
    "Bash(python3 -m pytest *)",
    # C/C++
    "Bash(gcc *)",
    "Bash(g++ *)",
    "Bash(cc *)",
    "Bash(c++ *)",
    "Bash(make *)",
    "Bash(cmake *)",
    # Rust
    "Bash(cargo *)",
    "Bash(rustc *)",
    # Node/JS/TS
    "Bash(node *)",
    "Bash(npx *)",
    "Bash(tsc *)",
    # Go
    "Bash(go *)",
    # General
    "Bash(sed *)",
    "Bash(awk *)",
    "Bash(grep *)",
    "Bash(rg *)",
    "Bash(xargs *)",
]

# Tools that require explicit protocol opt-in
PACKAGE_INSTALL_TOOLS = [
    "Bash(pip install *)",
    "Bash(pip3 install *)",
    "Bash(npm install *)",
    "Bash(yarn add *)",
    "Bash(cargo add *)",
    "Bash(apt *)",
    "Bash(brew *)",
]

WEB_ACCESS_TOOLS = [
    "Bash(curl *)",
    "Bash(wget *)",
    "WebFetch",
    "WebSearch",
]


@dataclass
class ProtocolDef:
    name: str
    description: str
    # What the LLM/user sees
    provides_spec: bool = True
    provides_full_spec: bool = False  # If False, only stage spec (not full spec.md)
    provides_training_tests: bool = False
    llm_writes_tests: bool = False
    # Workflow
    planning_phase: bool = False
    planning_prompt: str = ""
    # Human involvement
    human_supervised: bool = False
    human_instructions: str = ""
    # Token budget per stage (0 = unlimited / up to human judgment)
    token_budget: int = 1_000_000
    # Additional instructions prepended to the spec
    added_instructions: str = ""
    # Model to use (default: Sonnet 4.6)
    model: str = "claude-sonnet-4-6"
    # Additional allowed tools beyond defaults (use Bash(...) patterns)
    extra_allowed_tools: list = field(default_factory=list)
    # Whether to allow package installation commands
    allow_package_install: bool = False
    # Whether to allow web access (curl, wget, WebFetch, WebSearch)
    allow_web_access: bool = False

    def get_allowed_tools(self) -> list:
        """Build the full list of --allowedTools for this protocol."""
        tools = list(DEFAULT_ALLOWED_TOOLS)
        if self.allow_package_install:
            tools.extend(PACKAGE_INSTALL_TOOLS)
        if self.allow_web_access:
            tools.extend(WEB_ACCESS_TOOLS)
        tools.extend(self.extra_allowed_tools)
        return tools


# ---- Concrete protocols for the vertical slice ----

DIRECT_NO_TESTS = ProtocolDef(
    name="direct_no_tests",
    description="LLM gets the stage spec only. No tests provided. Implement until done.",
    provides_spec=True,
    provides_training_tests=False,
    added_instructions="Implement the following specification. You may run the engine "
        "to test it manually, but no automated tests are provided.",
)

DIRECT_SELF_TEST = ProtocolDef(
    name="direct_self_test",
    description="LLM gets the stage spec and is asked to write tests first, then implement.",
    provides_spec=True,
    provides_training_tests=False,
    llm_writes_tests=True,
    added_instructions="First, write a set of tests for the following specification. "
        "Then implement the specification, iterating until your tests pass.",
)

DIRECT_TESTS_PROVIDED = ProtocolDef(
    name="direct_tests_provided",
    description="LLM gets the stage spec and training tests. Implement until tests pass.",
    provides_spec=True,
    provides_training_tests=True,
    added_instructions="Implement the following specification. A set of tests is provided "
        "in the tests/ directory. Iterate until all provided tests pass.",
)

PLAN_AND_IMPLEMENT = ProtocolDef(
    name="plan_and_implement",
    description="LLM reads spec, drafts a plan, then implements in a clean-ish context.",
    provides_spec=True,
    provides_training_tests=True,
    planning_phase=True,
    planning_prompt="Read the following specification carefully. Draft an implementation "
        "plan that describes: (1) what data structures you will use, (2) what the main "
        "code changes are, (3) what edge cases you anticipate. Do NOT write any code yet.",
    added_instructions="Now implement according to your plan. Tests are in tests/.",
)

HUMAN_SUPERVISED = ProtocolDef(
    name="human_supervised",
    description="Human breaks down the stage into sub-tasks and guides the LLM.",
    provides_spec=True,
    provides_training_tests=True,
    human_supervised=True,
    human_instructions="""You are supervising this stage. Steps:
1. Read the stage spec and the task breakdown (provided separately).
2. Give the LLM one sub-task at a time.
3. Review the output before moving to the next sub-task.
4. Decide when the stage is complete.
Your time is being tracked from when you start until you signal completion.""",
)

ALL_PROTOCOLS = {p.name: p for p in [
    DIRECT_NO_TESTS, DIRECT_SELF_TEST, DIRECT_TESTS_PROVIDED,
    PLAN_AND_IMPLEMENT, HUMAN_SUPERVISED,
]}
