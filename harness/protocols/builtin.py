"""Built-in benchmark protocols."""
from . import ProtocolDef, PhaseDef

_DIRECT_NO_TESTS_INSTRUCTIONS = (
    "Implement the following specification directly. "
    "You may run the engine to test it manually, but no automated tests are provided.\n\n"
    "IMPORTANT constraints for this task:\n"
    "- Do NOT write a plan or design document before coding. Start implementing immediately.\n"
    "- Do NOT create test files or a test suite. No unit tests, no integration tests, no test scripts.\n"
    "- Do NOT create TODO lists, architecture docs, or README files.\n"
    "- Focus purely on writing the implementation code that satisfies the specification."
)

DIRECT_NO_TESTS = ProtocolDef(
    name="direct_no_tests",
    description="LLM gets the stage spec only. No tests provided. Implement until done.",
    provides_spec=True,
    provides_training_tests=False,
    added_instructions=_DIRECT_NO_TESTS_INSTRUCTIONS,
)

_DIRECT_NULL_PROMPT_INSTRUCTIONS = (
    _DIRECT_NO_TESTS_INSTRUCTIONS
    + "\n- Writing any test file invalidates this run."
)

DIRECT_NULL_PROMPT = ProtocolDef(
    name="direct_null_prompt",
    description="Same as direct_no_tests, but the instructions replace the default Claude Code system prompt via --system-prompt.",
    provides_spec=True,
    provides_training_tests=False,
    system_prompt=_DIRECT_NULL_PROMPT_INSTRUCTIONS,
    added_instructions=_DIRECT_NULL_PROMPT_INSTRUCTIONS,
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
    planning_prompt="Read the following specification carefully. Write an implementation "
        "plan to PLAN.md that describes: (1) what data structures you will use, (2) what the main "
        "code changes are, (3) what edge cases you anticipate. Do NOT write any code yet — "
        "only write the plan to PLAN.md.",
    added_instructions="Read PLAN.md, then implement according to the plan. Tests are in tests/.",
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
                "Do NOT read any tests, write any tests, or run any tests of the code at this point!",
            permission_mode="acceptEdits",
        ),
        PhaseDef(
            name="review",
            prompt_template="Review the implementation against CURRENT_STAGE.md, and check it against the tests in tests/"
                "Write a critique to REVIEW.md with specific bugs and improvements. "
                "Do NOT modify implementation code or iterate against the tests.",
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

COMPRESSED_ADVERSARIAL = ProtocolDef(
    name="compressed_adversarial",
    description="2-phase: plan+(sub-implement) -> review+fix, each fresh context.",
    provides_spec=True,
    provides_training_tests=True,
    phases=[
        PhaseDef(
            name="plan_implement",
            prompt_template="Read CURRENT_STAGE.md. First plan out how you will do this then implement the plan using sub-agents. "
				"When iterating against the tests in tests/, use sub-agents to do so and have them report back. "
				"Keep actual coding out of your context as much as possible.",
            permission_mode="acceptEdits",
        ),
        PhaseDef(
            name="review_fix",
            prompt_template="Review the implementation against CURRENT_STAGE.md, and check it against the tests in tests/"
                "Spawn sub-agents to fix any bugs or problems you find.",
            permission_mode="acceptEdits",
        ),
    ],
)

QUALITATIVE_ADVERSARIAL = ProtocolDef(
    name="qualitative_adversarial",
    description="Focus adversarial critique on structural aspects, not unit tests",
    provides_spec=True,
    provides_training_tests=False,
    phases=[
        PhaseDef(
            name="implement",
            prompt_template="Read CURRENT_STAGE.md and implement it. Focus on implementation. While you may run the program to verify its behavior, no tests are provided and you should not write your own unit tests. "
                "You should not unit-test individual features in isolation. Take care to make the code correct and efficient - use vectorization instead of for loops, re-use methods, avoid duplication.\n"
                "- Do NOT run pytest or equivalent testing code, or write individual test files. This will be recorded and will invalidate the run. ",
            permission_mode="acceptEdits",
        ),
        PhaseDef(
            name="review",
            prompt_template="You have been provided code that attempts to implement CURRENT_STAGE.md.  "
                 "Make sure the approach to CURRENT_STAGE.md is complete and satisfies the intent of the spec rather than just ticking boxes - it will be exposed to tests which have not been provided, so you are looking at ways it could fail. "
                 "Trace the code flow and logic, but do NOT write code here or run the program. You should take a critical but neutral stance - don't assume competency from the other coder, do not sugarcoat issues or try to balance criticisms with compliments. "
                 "In particular, flag code paths that silently discard or ignore inputs, inefficient approaches - for loops that should be vectorized for example, branches that silently fall through, functions that return None or default for unhandled cases, parameters that exist in one code path but not a parallel one, and code which is present but not wired up (and other stubs). "
                 "Do not be overly concerned with abstract code quality. Write your critique to REVIEW.md.",
            permission_mode="acceptEdits",
        ),
         PhaseDef(
            name="fix",
            prompt_template="Read REVIEW.md and fix each issue. Delete REVIEW.md when done.",
            permission_mode="acceptEdits",
        ),
   ],
)

OBSERVATION_FOCUS = ProtocolDef(
    name="observation_focus",
    description="Focus on making code paths observable and checking code logic over tests",
    provides_spec=True,
    provides_training_tests=False,
    phases=[
        PhaseDef(
            name="implement",
            prompt_template="Read CURRENT_STAGE.md and implement it. As you implement it, you should include debug messages tied to a debug mode flag to let you monitor the code function and check on the state. "
                "If this is not the first stage, make sure to re-enable the debug flag, as it is set to false at the end of each stage. "
                "Do not write individual tests, but instead come up with a few fully integrated scenarios and do complete runs while watching the debug output. "
                "Check the debug output against your expectations, and if encountering a bug or surprise don't just guess and check unless its very simple - add diagnostics to help you track down and understand the issue. "
                "When the code is ready to submit, disable the debug flag but leave all the debug hooks in the codebase for future stages. ",
            permission_mode="acceptEdits",
        ),
   ],
)

PROTOCOLS = [
    DIRECT_NO_TESTS,
    DIRECT_NULL_PROMPT,
    DIRECT_SPEED,
    DIRECT_MODULAR,
    DIRECT_LOOKAHEAD,
    DIRECT_SELF_TEST,
    DIRECT_TESTS_PROVIDED,
    PLAN_AND_IMPLEMENT,
    HUMAN_SUPERVISED,
    SEQUENTIAL_PIPELINE,
    PLAN_PARALLEL_IMPLEMENT,
    COMPRESSED_ADVERSARIAL,
    QUALITATIVE_ADVERSARIAL,
    OBSERVATION_FOCUS
]
