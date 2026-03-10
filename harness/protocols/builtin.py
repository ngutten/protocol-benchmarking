"""Built-in benchmark protocols."""
from . import ProtocolDef

DIRECT_NO_TESTS = ProtocolDef(
    name="direct_no_tests",
    description="LLM gets the stage spec only. No tests provided. Implement until done.",
    provides_spec=True,
    provides_training_tests=False,
    added_instructions="Implement the following specification. You may run the engine "
        "to test it manually, but no automated tests are provided.",
)

DIRECT_MODULAR = ProtocolDef(
    name="direct_modular",
    description="LLM gets the stage spec only. No tests. Instructed to prioritize modularity.",
    provides_spec=True,
    provides_training_tests=False,
    added_instructions="Implement the following specification. You may run the engine "
        "to test it manually, but no automated tests are provided.\n\n"
        "Prioritize modularity, code isolation, and code reuse. Where possible "
        "build interfaces rather than entangled objects.",
)

DIRECT_LOOKAHEAD = ProtocolDef(
    name="direct_lookahead",
    description="LLM gets the stage spec plus full spec for lookahead. No tests provided.",
    provides_spec=True,
    provides_full_spec=True,
    provides_training_tests=False,
    added_instructions="Implement the following specification. You may run the engine "
        "to test it manually, but no automated tests are provided.\n\n"
        "IMPORTANT: The full specification (spec.md) is available for reference. It "
        "describes all stages of the project, including stages you have not yet "
        "implemented. Review the upcoming stages and design your implementation so "
        "that it will be easy to extend in later stages. Choose data structures, "
        "abstractions, and code organization that will accommodate future requirements. "
        "However, do NOT implement features from future stages — only implement what "
        "the current stage asks for.",
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

PROTOCOLS = [
    DIRECT_NO_TESTS,
    DIRECT_MODULAR,
    DIRECT_LOOKAHEAD,
    DIRECT_SELF_TEST,
    DIRECT_TESTS_PROVIDED,
    PLAN_AND_IMPLEMENT,
    HUMAN_SUPERVISED,
]
