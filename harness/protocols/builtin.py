"""Built-in benchmark protocols."""
from . import ProtocolDef, PhaseDef

DIRECT_NO_TESTS = ProtocolDef(
    name="direct_no_tests",
    description="LLM gets the stage spec only. No tests provided. Implement until done.",
    provides_spec=True,
    provides_training_tests=False,
    added_instructions="Implement the following specification directly. "
        "You may run the engine to test it manually, but no automated tests are provided.\n\n"
        "IMPORTANT constraints for this task:\n"
        "- Do NOT write a plan or design document before coding. Start implementing immediately.\n"
        "- Do NOT create test files or a test suite. No unit tests, no integration tests, no test scripts.\n"
        "- Do NOT create TODO lists, architecture docs, or README files.\n"
        "- Focus purely on writing the implementation code that satisfies the specification.",
)

DIRECT_SPEED = ProtocolDef(
    name="direct_speed",
    description="LLM gets the stage spec only. No tests provided. Instructed to optimize for speed.",
    provides_spec=True,
    provides_training_tests=False,
    added_instructions="Implement the following specification directly. "
        "You may run the engine to test it manually, but no automated tests are provided.\n\n"
        "IMPORTANT constraints for this task:\n"
        "- Do NOT write a plan or design document before coding. Start implementing immediately.\n"
        "- Do NOT create test files or a test suite. No unit tests, no integration tests, no test scripts.\n"
        "- Do NOT create TODO lists, architecture docs, or README files.\n"
        "- Focus purely on writing the implementation code that satisfies the specification.\n"
        "- Be sure to optimize the code for speed.",
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

SEQUENTIAL_PIPELINE = ProtocolDef(
    name="sequential_pipeline",
    description="4-phase: plan -> implement -> review -> fix, each fresh context.",
    provides_spec=True,
    provides_training_tests=True,
    phases=[
        PhaseDef(
            name="plan",
            prompt_template="Read CURRENT_STAGE.md. Write a detailed implementation plan "
                "to PLAN.md (data structures, functions, edge cases). Do NOT write code.",
            permission_mode="acceptEdits",
        ),
        PhaseDef(
            name="implement",
            prompt_template="Read PLAN.md and CURRENT_STAGE.md. Implement the plan. "
                "Run tests in tests/ and iterate until they pass.",
            permission_mode="acceptEdits",
        ),
        PhaseDef(
            name="review",
            prompt_template="Review the implementation against CURRENT_STAGE.md. "
                "Write a critique to REVIEW.md with specific bugs and improvements. "
                "Do NOT modify implementation code.",
            permission_mode="acceptEdits",
        ),
        PhaseDef(
            name="fix",
            prompt_template="Read REVIEW.md. Fix each issue. Run tests in tests/ to verify. "
                "Delete PLAN.md and REVIEW.md when done.",
            permission_mode="acceptEdits",
        ),
    ],
)

PLAN_PARALLEL_IMPLEMENT = ProtocolDef(
    name="plan_parallel_implement",
    description="Planner decomposes work, parallel agents implement, integrator merges.",
    provides_spec=True,
    provides_training_tests=True,
    phases=[
        PhaseDef(
            name="plan",
            prompt_template="Read CURRENT_STAGE.md. Break the work into 2-3 independent "
                "sub-tasks targeting different files. Write TASK_1.md, TASK_2.md, TASK_3.md. "
                "Do NOT write implementation code.",
            permission_mode="acceptEdits",
        ),
        PhaseDef(
            name="implement",
            prompt_template="unused",  # parallel_prompts takes over
            permission_mode="acceptEdits",
            parallel_prompts=[
                "Read TASK_1.md. Implement exactly what it describes. Only modify files it mentions.",
                "Read TASK_2.md. Implement exactly what it describes. Only modify files it mentions.",
                "Read TASK_3.md. Implement exactly what it describes. Only modify files it mentions.",
            ],
        ),
        PhaseDef(
            name="integrate",
            prompt_template="Multiple agents implemented separate tasks. Review all changes, "
                "resolve conflicts, run tests in tests/, and fix failures.",
            permission_mode="acceptEdits",
        ),
    ],
)

PROTOCOLS = [
    DIRECT_NO_TESTS,
    DIRECT_SPEED,
    DIRECT_MODULAR,
    DIRECT_LOOKAHEAD,
    DIRECT_SELF_TEST,
    DIRECT_TESTS_PROVIDED,
    PLAN_AND_IMPLEMENT,
    HUMAN_SUPERVISED,
    SEQUENTIAL_PIPELINE,
    PLAN_PARALLEL_IMPLEMENT,
]
