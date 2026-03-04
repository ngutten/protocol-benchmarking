"""Protocol definitions for the benchmark.

Each protocol defines how a stage should be executed, what files the LLM sees,
and what instructions the human operator gets.

Protocols are auto-discovered from Python files in this directory.  Any module
that defines a module-level ``PROTOCOLS`` list (containing ProtocolDef instances)
will have those protocols registered automatically.  Users can drop new .py
files here to add custom protocols.
"""
import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Tool lists
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ProtocolDef dataclass
# ---------------------------------------------------------------------------

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
    # Custom command line (list of strings) to use instead of internally
    # generated claude commands.  When set, the harness will invoke this
    # command for each stage instead of building a `claude` invocation.
    # The placeholder {prompt} in any element will be replaced with the
    # stage prompt, and {work_dir} with the workspace path.
    custom_command: Optional[list] = None

    def get_allowed_tools(self) -> list:
        """Build the full list of --allowedTools for this protocol."""
        tools = list(DEFAULT_ALLOWED_TOOLS)
        if self.allow_package_install:
            tools.extend(PACKAGE_INSTALL_TOOLS)
        if self.allow_web_access:
            tools.extend(WEB_ACCESS_TOOLS)
        tools.extend(self.extra_allowed_tools)
        return tools


# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------

def _discover_protocols() -> dict:
    """Scan all modules in this package for a ``PROTOCOLS`` list.

    Each module may define::

        PROTOCOLS = [ProtocolDef(...), ProtocolDef(...)]

    Returns a dict mapping protocol name -> ProtocolDef.
    """
    found = {}
    package_path = __path__
    for importer, modname, ispkg in pkgutil.iter_modules(package_path):
        mod = importlib.import_module(f".{modname}", __package__)
        protocol_list = getattr(mod, "PROTOCOLS", None)
        if protocol_list is None:
            continue
        for proto in protocol_list:
            if not isinstance(proto, ProtocolDef):
                continue
            if proto.name in found:
                raise ValueError(
                    f"Duplicate protocol name '{proto.name}' "
                    f"(from module '{modname}', already registered)"
                )
            found[proto.name] = proto
    return found


ALL_PROTOCOLS = _discover_protocols()
