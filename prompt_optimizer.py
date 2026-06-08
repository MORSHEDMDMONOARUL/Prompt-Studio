from __future__ import annotations

import argparse
import http.server
import json
import math
import os
import re
import socketserver
from pathlib import Path
from typing import Iterable

import requests


NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODELS = [
    "nvidia/nvidia-nemotron-nano-9b-v2",
    "meta/llama-3.1-8b-instruct",
    "nvidia/llama-3.1-nemotron-nano-8b-v1",
    "qwen/qwen3-next-80b-a3b-instruct",
]
DEFAULT_TIMEOUT = 90
DEFAULT_MAX_PROMPT_CHARS = 12000
APP_NAME = "Prompt Studio"
REQUIRED_PROMPT_SECTIONS = [
    "# Role",
    "# Project Context",
    "# Pre-Build Instructions",
    "# Objective",
    "# Project Identity",
    "# Target Users",
    "# Core Features",
    "# User Flow",
    "# Technical Requirements",
    "# Runtime and Configuration",
    "# UI/UX Requirements",
    "# Data, API, and Integration Requirements",
    "# Reference and Research Protocol",
    "# Constraints and Assumptions",
    "# Critical Constraints",
    "# Deliverables",
    "# Implementation Phases",
    "# Startup and Run Sequence",
    "# Testing and Validation",
    "# Acceptance Criteria",
    "# Done When",
    "# Execution Protocol",
    "# Input",
]
PROMPT_PROFILES = {
    "project_brief": {
        "label": "Project Brief",
        "description": "Balanced project brief with practical scope, milestones, and validation.",
        "focus": "Keep the structure strong but not overly long; balance product context, implementation clarity, UX, milestone checks, and validation.",
        "task": "Turn this rough idea into a professional build-ready software project prompt.",
    },
    "coding_agent": {
        "label": "Coding Agent",
        "description": "Phased execution prompt for an AI coding assistant.",
        "focus": "Use the strongest phased build-spec structure: repository exploration, source/documentation study, scoped implementation phases, milestone checks, concrete files, tests, run commands, and self-review.",
        "task": "Turn this rough idea into a precise execution prompt for an AI coding agent.",
    },
    "product_spec": {
        "label": "Product Spec",
        "description": "Product-facing spec with strategy, milestones, risks, and acceptance criteria.",
        "focus": "Emphasize target users, product strategy, jobs to be done, workflows, milestone plan, risks, measurable acceptance criteria, and launch-quality UX.",
        "task": "Turn this rough idea into a concise product specification for a buildable MVP.",
    },
}
PROTECTED_SEGMENT_PATTERNS = [
    re.compile(r"```[\s\S]*?```"),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"\bhttps?://\S+", re.I),
    re.compile(r"\b[\w.-]*[/\\][\w./\\-]+"),
    re.compile(r"\b[A-Z][A-Za-z0-9]*(?:_[A-Z][A-Za-z0-9]*)+\b"),
    re.compile(r"\b\w+\.\w+(?:\.\w+)*\(\)?"),
    re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)"),
    re.compile(r"\b\d+\.\d+\.\d+\b"),
]
COMPRESSION_REPLACEMENTS = [
    (re.compile(r"\bturn this rough idea into a professional build-ready software project prompt\b", re.I), "turn rough idea into a build-ready project prompt"),
    (re.compile(r"\bturn this rough idea into a precise execution prompt for an AI coding agent\b", re.I), "turn rough idea into a concise coding-agent prompt"),
    (re.compile(r"\bturn this rough idea into a concise product specification for a buildable MVP\b", re.I), "turn rough idea into a concise MVP spec"),
    (re.compile(r"\bthe user has a rough project idea and wants it turned into a real, working software project rather than a simple explanation or mockup\b", re.I), "turn rough idea into a working software project, not a simple explanation or mockup"),
    (re.compile(r"\bthe user wants to turn a rough idea into a real, working software project\b", re.I), "turn rough idea into a working software project"),
    (re.compile(r"\bthe project can be run locally from the provided instructions\b", re.I), "project runs locally from documented steps"),
    (re.compile(r"\bthe main workflow works without manual code edits\b", re.I), "main workflow works without manual edits"),
    (re.compile(r"\bthe ui is clear enough for a first-time user\b", re.I), "UI is clear for a new user"),
    (re.compile(r"\bthe code is organized, readable, and ready to extend\b", re.I), "code stays organized, readable, and extensible"),
    (re.compile(r"\bidentify the likely users, their goal, and the problem this project solves for them\b", re.I), "identify users, goals, and solved problem"),
    (re.compile(r"\bdefine the smallest complete feature set needed for a useful first version\b", re.I), "define smallest useful feature set"),
    (re.compile(r"\binclude the main workflow, supporting screens or commands\b", re.I), "include main workflow and supporting screens/commands"),
    (re.compile(r"\bdescribe the primary path from first launch to successful completion\b", re.I), "describe path from launch to success"),
    (re.compile(r"\binclude alternate paths for invalid input, no data, slow external services, unavailable APIs, and recovery after failure\b", re.I), "include invalid input, no data, slow/unavailable APIs, recovery"),
    (re.compile(r"\bchoose a simple, appropriate stack\b", re.I), "choose simple fit-for-purpose stack"),
    (re.compile(r"\bimplement the project with clean structure, readable code, and clear separation between UI, logic, data handling, and configuration\b", re.I), "use clean structure; separate UI, logic, data, config"),
    (re.compile(r"\bcreate a polished, practical interface that a first-time user can understand\b", re.I), "create polished practical UI for new users"),
    (re.compile(r"\bprioritize clarity, responsive layout, accessible contrast, helpful labels, obvious next actions, and complete loading/error/empty states\b", re.I), "prioritize clarity, responsive layout, accessible contrast, labels, next actions, states"),
    (re.compile(r"\buse real local data or real API calls when required\b", re.I), "use real local data/API calls when needed"),
    (re.compile(r"\bif external services are needed, load secrets from environment variables, document setup clearly, and handle integration failure gracefully\b", re.I), "for external services, load secrets from env, document setup, handle failures"),
    (re.compile(r"\bmake reasonable assumptions where details are missing and list them before implementation\b", re.I), "state reasonable assumptions before implementation"),
    (re.compile(r"\bdo not invent private facts or claim real deployment/integration unless completed\b", re.I), "do not invent private facts or claim unbuilt deployment/integration"),
    (re.compile(r"\bprovide the working source code, setup instructions, run commands, sample data if useful, and a short explanation of the implementation\b", re.I), "provide source, setup, run commands, useful sample data, short implementation note"),
    (re.compile(r"\bverify the main workflow works locally\b", re.I), "verify main workflow locally"),
    (re.compile(r"\binclude focused tests or manual test steps for the critical path, edge cases, validation, and failure states\b", re.I), "include focused tests/manual steps for critical path, edge cases, validation, failures"),
    (re.compile(r"\bbefore final delivery, self-review the result like a senior engineer\b", re.I), "before delivery, self-review like senior engineer"),
    (re.compile(r"\bconfirm the implementation matches the original idea\b", re.I), "confirm implementation matches idea"),
    (re.compile(r"\bconfirm the app or tool runs locally\b", re.I), "confirm app/tool runs locally"),
    (re.compile(r"\bconfirm the main user workflow works\b", re.I), "confirm main user workflow works"),
    (re.compile(r"\bconfirm the output satisfies the acceptance criteria\b", re.I), "confirm output meets acceptance criteria"),
    (re.compile(r"\bfix any obvious issue before presenting the final answer\b", re.I), "fix obvious issues before final answer"),
    (re.compile(r"\bsecurity, privacy, and configuration assumptions are stated\b", re.I), "security/privacy/config assumptions stated"),
    (re.compile(r"\bany limitations or follow-up improvements are clearly stated\b", re.I), "limitations/follow-ups stated"),
    (re.compile(r"\berror states, empty states, and loading states are handled\b", re.I), "error, empty, and loading states are handled"),
    (re.compile(r"\bvalidation, error handling, empty states, and loading states\b", re.I), "validation, errors, empty/loading states"),
    (re.compile(r"\bempty, loading, validation, and failure states\b", re.I), "empty/loading, validation, and failure states"),
    (re.compile(r"\bvalidation, and failure states\b", re.I), "validation/failure states"),
    (re.compile(r"\berror, empty, and loading states\b", re.I), "error/empty/loading states"),
    (re.compile(r"\bsetup instructions\b", re.I), "setup steps"),
    (re.compile(r"\bacceptance criteria\b", re.I), "acceptance checks"),
    (re.compile(r"\bimplementation requirements\b", re.I), "build requirements"),
    (re.compile(r"\btechnical requirements\b", re.I), "tech requirements"),
    (re.compile(r"\bdata handling\b", re.I), "data"),
    (re.compile(r"\bprofessional build-ready\b", re.I), "build-ready"),
    (re.compile(r"\breal, working\b", re.I), "working"),
    (re.compile(r"\bfirst-time user\b", re.I), "new user"),
    (re.compile(r"\bend-to-end\b", re.I), "E2E"),
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bmake sure to\b", re.I), "ensure"),
    (re.compile(r"\bwhere appropriate\b", re.I), "when useful"),
    (re.compile(r"\bwhere relevant\b", re.I), "when relevant"),
    (re.compile(r"\brather than\b", re.I), "not"),
]
FILLER_WORDS = re.compile(
    r"\b(?:just|really|basically|actually|simply|essentially|generally|quite|very|clearly|obvious|obviously)\b",
    re.I,
)
PLEASANTRIES = re.compile(
    r"\b(?:please|kindly|thank you|thanks|sure|certainly|of course|happy to|i'?d be happy)\b[,.]?\s*",
    re.I,
)
HEDGES = re.compile(
    r"\b(?:perhaps|maybe|might|could potentially|would like to|i think|in my opinion|it seems|it appears)\b\s*",
    re.I,
)
LEADING_PHRASES = re.compile(
    r"^(?:you should|you must|the builder should|the developer should|make sure to|remember to)\s+",
    re.I,
)
ARTICLES = re.compile(r"\b(?:a|an|the)\s+(?=[a-z])", re.I)
LINE_BULLET_PREFIX = re.compile(r"^(\s*(?:[-*+]|(?:\d+\.))\s+)(.*)$")
LINE_BLOCKQUOTE_PREFIX = re.compile(r"^(\s*>\s+)(.*)$")
LINE_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
TOKEN_ESTIMATE_DIVISOR = 4


class OptimizationError(RuntimeError):
    pass


def load_dotenv(path: Path | None = None) -> None:
    path = path or Path(__file__).with_name(".env")
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_api_key() -> str | None:
    return os.getenv("NVIDIA_API_KEY") or os.getenv("NGC_API_KEY")


def get_max_prompt_chars() -> int:
    try:
        return int(os.getenv("PROMPT_MAX_CHARS", str(DEFAULT_MAX_PROMPT_CHARS)))
    except ValueError:
        return DEFAULT_MAX_PROMPT_CHARS


def parse_models(values: Iterable[str] | None) -> list[str]:
    raw_models: list[str] = []
    if values:
        for value in values:
            raw_models.extend(part.strip() for part in value.split(","))
    elif os.getenv("NVIDIA_MODELS"):
        raw_models.extend(part.strip() for part in os.getenv("NVIDIA_MODELS", "").split(","))
    else:
        raw_models.extend(DEFAULT_MODELS)

    models: list[str] = []
    seen: set[str] = set()
    for model in raw_models:
        if model and model not in seen:
            seen.add(model)
            models.append(model)
    return models


def parse_profile(value: object) -> str:
    key = str(value or "project_brief").strip()
    if key in PROMPT_PROFILES:
        return key
    return "project_brief"


def profile_payload(profile_key: str) -> dict[str, str]:
    profile = PROMPT_PROFILES[parse_profile(profile_key)]
    return {
        "key": parse_profile(profile_key),
        "label": profile["label"],
        "description": profile["description"],
    }


def build_messages(user_prompt: str, profile_key: str) -> list[dict[str, str]]:
    profile = PROMPT_PROFILES[parse_profile(profile_key)]
    required_headings = "\n".join(f"      {section}" for section in REQUIRED_PROMPT_SECTIONS)
    system = f"""
    You are {APP_NAME}, a senior software developer, product thinker, and prompt architect.
    Your job is to transform a user's rough idea into a professional, build-ready prompt
    that an AI coding agent or engineering team can use to create a real working project.
    Use a disciplined prompt-template style inspired by mature prompt-optimization tools and
    phased implementation specs: explicit role, project identity, pre-build instructions,
    runtime/configuration expectations, reference-study protocol, milestone checks,
    non-negotiable constraints, startup/run sequence, testing checklist, and done-when criteria.

    Optimization profile: {profile["label"]}
    Profile focus: {profile["focus"]}

    Return only valid JSON with these keys:
    - optimized_prompt: the final improved prompt, written as a polished project brief
    - why_it_is_better: a short explanation in plain English
    - checklist: an array of 4 to 7 short improvements made

    The optimized_prompt must:
    - Sound like it was written by a senior software developer or professional product team.
    - Convert vague ideas into a complete real-project request.
    - Use clear Markdown sections with these exact headings:
{required_headings}
    - Start the builder with a strong pre-build instruction block: inspect existing code first,
      preserve the user's intent, make reasonable assumptions, and implement end-to-end.
    - Define explicit project identity, objective, target users, and what success means.
    - Include concrete implementation expectations, not abstract advice.
    - Include runtime and configuration expectations when relevant: commands, environment variables,
      local setup, secrets handling, and dependency constraints.
    - Include reference-repo, source-code, or documentation study instructions when useful. Tell the
      builder to verify current docs or inspect referenced repos before integrating unfamiliar APIs.
    - Use a phase-based implementation plan with milestone checks. Each phase should have an outcome
      or verification step, especially for the Coding Agent profile.
    - Include critical constraints and non-negotiables: avoid hallucinated APIs, avoid hardcoded secrets,
      preserve lightweight architecture when requested, and avoid unrelated scope creep.
    - Include a startup/run sequence when the idea involves an app, service, script, workflow, or UI.
    - Include edge cases, error handling, empty states, loading states, and security/privacy notes where relevant.
    - Include measurable acceptance criteria wherever the user's idea allows it.
    - Include a concise Done When checklist that states exactly when the work is finished.
    - Include a self-review instruction in the Execution Protocol: before final delivery, verify the app runs,
      the main workflow works, and the output matches the acceptance criteria.
    - Tell the builder to make reasonable assumptions and state them.
    - Tell the builder to implement the project end-to-end, not just explain it.
    - Keep the user's original intent, domain, and constraints.
    - Avoid over-scoping into enterprise complexity unless the user's idea clearly needs it.
    - Avoid fake claims such as deployed URLs, real integrations, payments, or notifications unless the builder actually implements them.

    Rules:
    - Preserve the user's original intent.
    - Add missing project context, feature scope, output format, constraints, and success criteria.
    - Do not invent private facts.
    - Do not turn every prompt into a mega-spec. Match depth to the idea and profile:
      Project Brief is balanced, Coding Agent is the most phased and operational,
      Product Spec is product-facing with strategy, risks, milestones, and acceptance criteria.
    - Keep the final prompt ready to copy into an AI coding assistant.
    - If information is missing, write reasonable assumptions instead of asking questions, unless the missing
      information would block implementation.
    """
    user = f"{profile['task']}\n\nRough idea:\n{user_prompt}"
    return [
        {"role": "system", "content": "\n".join(line.rstrip() for line in system.splitlines()).strip()},
        {"role": "user", "content": user},
    ]


def call_model(api_key: str, model: str, user_prompt: str, profile_key: str, timeout: int) -> dict[str, object]:
    payload = {
        "model": model,
        "messages": build_messages(user_prompt, profile_key),
        "temperature": 0.22,
        "top_p": 0.9,
        "max_tokens": 4200,
        "stream": False,
    }
    response = requests.post(
        NVIDIA_ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        detail = response.text[:500].replace("\n", " ")
        raise OptimizationError(f"{model}: HTTP {response.status_code}: {detail}")

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OptimizationError(f"{model}: unexpected response shape") from exc

    parsed = parse_json_response(content)
    parsed["model"] = model
    return parsed


def parse_json_response(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "optimized_prompt": text.strip(),
            "why_it_is_better": "The model returned a direct optimized prompt instead of JSON, so the server repaired it into the required structure.",
            "checklist": ["Clarified the request", "Improved structure", "Made the output easier to use"],
        }

    optimized = str(data.get("optimized_prompt", "")).strip()
    if not optimized:
        optimized = str(data.get("prompt", "")).strip() or text.strip()

    checklist = data.get("checklist", [])
    if not isinstance(checklist, list):
        checklist = [str(checklist)]

    return {
        "optimized_prompt": optimized,
        "why_it_is_better": str(data.get("why_it_is_better", "")).strip(),
        "checklist": [str(item).strip() for item in checklist if str(item).strip()],
    }


def normalize_project_prompt(optimized_prompt: str, original_prompt: str, profile_key: str = "project_brief") -> str:
    cleaned = optimized_prompt.strip()
    role_index = cleaned.find("# Role")
    if role_index > 0:
        cleaned = cleaned[role_index:].strip()

    cleaned = cleaned.replace("**optimized_prompt**", "").strip()
    cleaned = cleaned.replace("optimized_prompt:", "").strip()

    if "# Role" not in cleaned:
        return build_structured_prompt_from_text(original_prompt, cleaned, profile_key)

    for section in REQUIRED_PROMPT_SECTIONS:
        if section not in cleaned:
            cleaned = add_missing_section(cleaned, section, original_prompt)

    return cleaned.strip()


def add_missing_section(prompt: str, section: str, original_prompt: str) -> str:
    block_map = {
        "# Pre-Build Instructions": "# Pre-Build Instructions\nBefore writing code, inspect the existing project structure, identify the active stack, preserve the user's intent, and state reasonable assumptions. Implement the result end-to-end instead of only explaining an approach.\n",
        "# Project Identity": "# Project Identity\nName the project, describe its purpose in one or two sentences, and define the primary outcome the finished project must deliver.\n",
        "# User Flow": "# User Flow\nDescribe the primary end-to-end workflow from first visit to successful completion, including important alternative paths, validation, empty states, loading states, and failure states.\n",
        "# Runtime and Configuration": "# Runtime and Configuration\nSpecify expected runtime, setup commands, environment variables, dependency constraints, local data or service requirements, and how secrets must be loaded without hardcoding them.\n",
        "# Reference and Research Protocol": "# Reference and Research Protocol\nWhen unfamiliar libraries, APIs, repo patterns, or external documentation are relevant, inspect the source or official docs first and adapt the implementation to verified behavior. Do not hallucinate APIs or configuration names.\n",
        "# Data, API, and Integration Requirements": "# Data, API, and Integration Requirements\nSpecify what data must be stored, where it comes from, how API keys or secrets should be configured, and how integrations should fail gracefully.\n",
        "# Constraints and Assumptions": "# Constraints and Assumptions\nMake reasonable assumptions where the original idea is underspecified. State those assumptions clearly and avoid claiming completed deployment or real integrations unless they are implemented.\n",
        "# Critical Constraints": "# Critical Constraints\nList the non-negotiables: preserve the requested architecture, keep scope practical, avoid unrelated refactors, avoid hardcoded secrets, and do not claim unverified integrations or deployment.\n",
        "# Implementation Phases": "# Implementation Phases\nBreak the build into clear phases with milestone checks, such as project inspection, data/model design, core implementation, UI or workflow polish, integration handling, and final verification.\n",
        "# Startup and Run Sequence": "# Startup and Run Sequence\nDocument the exact setup and run sequence the builder should provide, including install commands, environment setup, server or script commands, and the local URL or command to verify.\n",
        "# Testing and Validation": "# Testing and Validation\nVerify the main workflow locally. Include manual test cases or automated tests for the critical path, input validation, edge cases, integration failure, responsive layout, and regression risk.\n",
        "# Done When": "# Done When\nThe work is done only when the app or tool runs locally, the primary workflow passes, required states are handled, tests or manual checks are documented, and the final answer names any remaining limitations.\n",
        "# Execution Protocol": "# Execution Protocol\nBefore final delivery, self-review the implementation like a senior engineer: confirm it runs locally, confirm the main workflow works, compare it against the acceptance criteria, and fix obvious issues before presenting the result.\n",
        "# Input": f"# Input\nOriginal user idea: {original_prompt.strip()}\n",
    }
    block = block_map.get(section, f"{section}\nDefine this section clearly based on the original project idea.\n")
    insert_before = {
        "# Pre-Build Instructions": "# Objective",
        "# Project Identity": "# Target Users",
        "# User Flow": "# Technical Requirements",
        "# Runtime and Configuration": "# UI/UX Requirements",
        "# Reference and Research Protocol": "# Constraints and Assumptions",
        "# Critical Constraints": "# Deliverables",
        "# Implementation Phases": "# Startup and Run Sequence",
        "# Startup and Run Sequence": "# Testing and Validation",
        "# Testing and Validation": "# Acceptance Criteria",
        "# Done When": "# Execution Protocol",
        "# Execution Protocol": "# Input",
    }

    anchor = insert_before.get(section)
    if anchor and anchor in prompt:
        return prompt.replace(anchor, f"{block}\n{anchor}", 1)

    if section == "# Input":
        return f"{prompt.rstrip()}\n\n{block}"
    return f"{prompt.rstrip()}\n\n{block}"


def build_structured_prompt_from_text(original_prompt: str, model_text: str, profile_key: str = "project_brief") -> str:
    profile = PROMPT_PROFILES[parse_profile(profile_key)]
    useful_model_text = model_text.strip()
    if not useful_model_text:
        useful_model_text = "Use the original project idea as the source of truth and infer a practical first version."

    return f"""# Role
Act as a senior software developer, product-minded implementation lead, and pragmatic UI/UX reviewer.

# Project Context
The user wants to turn a rough idea into a real, working software project. Treat this as a practical implementation request, not a brainstorming exercise. Use the {profile["label"]} profile: {profile["focus"]}

# Pre-Build Instructions
- Inspect the existing files, architecture, dependencies, and conventions before changing code.
- Preserve the user's original intent and keep the scope practical for a complete first version.
- Make reasonable assumptions when details are missing and state them before implementation.
- Implement the project end-to-end; do not stop at advice, pseudocode, or a mockup unless the user explicitly asks for that.
- Verify unfamiliar APIs, libraries, repo patterns, and setup steps against source code or official documentation before relying on them.

# Objective
Build the following idea end-to-end:

{original_prompt.strip()}

# Project Identity
- Working name: infer a concise product or project name from the idea unless the user provided one.
- Purpose: define what the finished project helps the user accomplish.
- Success signal: state the primary outcome that proves the project works.

# Target Users
Identify the primary users, their needs, and the problem the product solves.

# Core Features
Use the following model analysis as a starting point, then refine it into the smallest complete product:

{useful_model_text}

# User Flow
Describe and implement the main path a user follows from opening the project to completing the core task. Include empty, loading, validation, and failure states.

# Technical Requirements
Choose a simple, appropriate tech stack. Keep the code organized, readable, maintainable, and easy to run locally. Match existing architecture and local conventions when working inside an existing repository.

# Runtime and Configuration
- Document install, setup, and run commands.
- Use environment variables for secrets, API keys, model names, endpoints, ports, and other deploy-specific values.
- Provide sensible local defaults where safe.
- Handle missing configuration with clear errors and recovery steps.

# UI/UX Requirements
Build a clear, responsive, accessible interface with obvious actions and polished visual hierarchy.

# Data, API, and Integration Requirements
Use real local data or API calls where appropriate. Load secrets from environment variables and handle API failure gracefully.

# Reference and Research Protocol
- If the user names a GitHub repo, library, API, paper, dataset, or documentation source, study it before designing the implementation.
- Prefer official docs, primary source code, or repository examples for technical behavior.
- Note the specific patterns or constraints learned from references and adapt the build to them.
- Do not hallucinate API names, configuration keys, pricing, current model names, or repository behavior.

# Constraints and Assumptions
Make reasonable assumptions where details are missing and state them clearly. Do not invent private facts or claim real deployment unless it is actually completed.

# Critical Constraints
- Keep the solution aligned with the user's requested stack, provider, architecture, and level of complexity.
- Do not hardcode secrets or commit generated credentials.
- Avoid unrelated rewrites, broad refactors, or enterprise features that are not needed for the first useful version.
- Preserve existing user work and avoid destructive operations unless explicitly requested.
- If something cannot be completed, state the blocker and the closest verified result.

# Deliverables
Provide working source code, setup instructions, run commands, sample data if useful, and a concise implementation summary.

# Implementation Phases
1. Discovery: inspect the project or requirements, list assumptions, and identify the smallest complete scope.
2. Foundation: set up the runtime, configuration, data model, and core architecture needed for the workflow.
3. Core Build: implement the main user workflow and the essential features.
4. Integration and States: connect real data or APIs when needed and handle loading, empty, validation, error, and failure paths.
5. Polish and Accessibility: refine layout, copy, responsiveness, keyboard behavior, and accessible contrast.
6. Verification: run the app or tool, execute tests or manual checks, fix obvious issues, and summarize what changed.

# Startup and Run Sequence
Provide the exact sequence a user should follow to run the project locally, including dependency installation, environment setup, start commands, test commands, and the local URL or command output that confirms success.

# Testing and Validation
Verify the main workflow locally. Include manual test cases or automated tests for the critical path, edge cases, validation, integration failure behavior, responsive layout, and regression risk.

# Acceptance Criteria
- The project runs locally from the documented commands.
- The main workflow works end-to-end.
- The UI is understandable for a first-time user.
- The code is organized and ready to extend.
- Error, empty, and loading states are handled.
- Runtime/configuration assumptions are documented.
- Milestone checks and final verification steps are completed.

# Done When
- The requested project behavior is implemented, not merely described.
- The startup/run sequence has been tested or clearly documented.
- The primary workflow passes from first launch to successful completion.
- Required error, empty, loading, and validation states are covered.
- Tests or manual checks are included for the critical path.
- Remaining limitations are named honestly.

# Execution Protocol
Before final delivery, self-review the implementation like a senior engineer. Confirm the app runs, the main workflow works, and the result satisfies the acceptance criteria. Fix obvious issues before presenting the final answer.

# Input
Original user idea: {original_prompt.strip()}"""


def optimize_prompt(user_prompt: str, profile_key: str, models: list[str], timeout: int) -> dict[str, object]:
    api_key = get_api_key()
    if not api_key:
        raise OptimizationError("NVIDIA_API_KEY is missing. Add it to .env or your environment.")

    errors: list[str] = []
    for model in models:
        try:
            return call_model(api_key, model, user_prompt, profile_key, timeout)
        except (requests.RequestException, OptimizationError) as exc:
            errors.append(str(exc))

    raise OptimizationError("All NVIDIA models failed:\n" + "\n".join(f"- {error}" for error in errors))


def fallback_optimize(user_prompt: str, profile_key: str) -> dict[str, object]:
    prompt = user_prompt.strip()
    profile = PROMPT_PROFILES[parse_profile(profile_key)]
    optimized = f"""# Role
Act as a senior software developer, product-minded implementation lead, and pragmatic UI/UX reviewer.

# Project Context
The user has a rough project idea and wants it turned into a real, working software project rather than a simple explanation or mockup. Use the {profile["label"]} profile: {profile["focus"]}

# Pre-Build Instructions
- Inspect any existing project files, architecture, dependencies, and conventions before making changes.
- Preserve the user's original intent and convert it into an implementation-ready request.
- Make reasonable assumptions where details are missing and state them before implementation.
- Implement the result end-to-end, including setup, core workflow, validation, and verification.
- Study referenced repositories, docs, APIs, or examples before integrating their patterns.
- Keep the depth appropriate for the idea: balanced for Project Brief, operational and phased for Coding Agent, product-facing for Product Spec.

# Objective
Build the following idea end-to-end:

{prompt}

# Project Identity
- Working name: infer a concise product or project name from the idea unless the user provided one.
- Purpose: define what the finished project does and why it matters.
- Success signal: identify the primary outcome that proves the project works.

# Target Users
Identify the likely users, their goal, and the problem this project solves for them.

# Core Features
Define the smallest complete feature set needed for a useful first version. Include the main workflow, supporting screens or commands, validation, error handling, empty states, and loading states.

# User Flow
Describe the primary path from first launch to successful completion. Include alternate paths for invalid input, no data, slow external services, unavailable APIs, and recovery after failure.

# Technical Requirements
Choose a simple, appropriate stack. Implement the project with clean structure, readable code, and clear separation between UI, logic, data handling, and configuration. Keep the scope aligned with the {profile["label"]} profile: {profile["focus"]}

# Runtime and Configuration
- Document required runtime versions, install commands, start commands, test commands, and local URLs or command outputs.
- Load secrets, API keys, model names, endpoints, ports, and environment-specific values from configuration or environment variables.
- Provide safe defaults for local development where possible.
- Handle missing or invalid configuration with clear errors and recovery steps.

# UI/UX Requirements
Create a polished, practical interface that a first-time user can understand. Prioritize clarity, responsive layout, accessible contrast, helpful labels, obvious next actions, and complete loading/error/empty states.

# Data, API, and Integration Requirements
Use real local data or real API calls when required. If external services are needed, load secrets from environment variables, document setup clearly, and handle integration failure gracefully.

# Reference and Research Protocol
- If the user provides a GitHub repo, library, API, paper, dataset, or documentation source, inspect the relevant source before designing the final implementation.
- Prefer official documentation, repository examples, and primary source code over guesses.
- Extract only the patterns that help this project: architecture ideas, prompt/token strategy, UI expectations, API behavior, or test approach.
- Do not hallucinate API names, current model names, config keys, repository behavior, or integration results.

# Constraints and Assumptions
Make reasonable assumptions where details are missing and list them before implementation. Do not invent private facts or claim real deployment/integration unless completed.

# Critical Constraints
- Preserve the requested provider, stack, architecture, and lightweight scope unless the user explicitly changes them.
- Do not hardcode secrets, credentials, or private tokens.
- Avoid unrelated rewrites, broad refactors, or extra features that do not serve the first useful version.
- Work with existing files and user changes instead of reverting them.
- If a requirement cannot be completed, explain the blocker and provide the closest verified result.

# Deliverables
Provide the working source code, setup instructions, run commands, sample data if useful, and a short explanation of the implementation.

# Implementation Phases
1. Discovery and assumptions: inspect the repo or requirements, identify constraints, and define the smallest complete scope.
2. Foundation: establish runtime setup, configuration, data structures, and file/module boundaries.
3. Core workflow: implement the main user journey and essential feature set.
4. Integration and resilience: connect real data or APIs where needed and cover empty, loading, validation, error, and failure states.
5. Polish: refine UX, responsiveness, accessibility, copy, and professional presentation.
6. Verification: run the app or tool, execute tests or manual checks, fix obvious issues, and summarize the result.

# Startup and Run Sequence
Provide exact commands for setup, configuration, starting the app or tool, running tests, and confirming the project works locally. Include expected local URL, terminal output, or file output when applicable.

# Testing and Validation
Verify the main workflow works locally. Include focused tests or manual test steps for the critical path, edge cases, validation, integration failure states, responsive layout, and regression risks.

# Acceptance Criteria
- The project can be run locally from the provided instructions.
- The main workflow works without manual code edits.
- The UI is clear enough for a first-time user.
- The code is organized, readable, and ready to extend.
- Error states, empty states, and loading states are handled.
- Security, privacy, and configuration assumptions are stated.
- Phase milestones have verification checks.
- Any limitations or follow-up improvements are clearly stated.

# Done When
- The requested behavior is implemented end-to-end.
- The startup/run sequence is documented and verified where possible.
- The primary workflow passes from launch to successful completion.
- Required loading, empty, validation, and failure states are handled.
- Tests or manual checks cover the critical path.
- The final answer summarizes changes, verification, and any remaining limitations.

# Execution Protocol
Before final delivery, self-review the result like a senior engineer:
1. Confirm the implementation matches the original idea.
2. Confirm the app or tool runs locally.
3. Confirm the main user workflow works.
4. Confirm the output satisfies the acceptance criteria.
5. Fix any obvious issue before presenting the final answer.

# Input
Original user idea: {prompt}"""
    return {
        "optimized_prompt": optimized,
        "why_it_is_better": "Local fallback converted the rough idea into a structured engineering prompt with role, workflow, constraints, deliverables, validation, and a self-review protocol.",
        "checklist": [
            "Added expert role framing",
            "Added structured prompt sections",
            "Defined implementation requirements",
            "Added workflow and state handling",
            "Added testing and validation",
            "Added self-review protocol",
        ],
        "model": "local-fallback",
    }


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / TOKEN_ESTIMATE_DIVISOR))


def with_protected_segments(text: str, transform) -> str:
    segments: list[str] = []
    working = text
    for pattern in PROTECTED_SEGMENT_PATTERNS:
        def stash(match: re.Match[str]) -> str:
            index = len(segments)
            segments.append(match.group(0))
            return f"\uE000{index}\uE001"

        working = pattern.sub(stash, working)

    compressed = transform(working)
    for index, segment in enumerate(segments):
        compressed = compressed.replace(f"\uE000{index}\uE001", segment)
    return compressed


def compress_prose_fragment(text: str) -> str:
    if not text.strip():
        return text

    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()) :]
    core = text.strip()

    def transform(value: str) -> str:
        value = LEADING_PHRASES.sub("", value)
        value = PLEASANTRIES.sub("", value)
        value = HEDGES.sub("", value)
        for pattern, replacement in COMPRESSION_REPLACEMENTS:
            value = pattern.sub(replacement, value)
        value = FILLER_WORDS.sub("", value)
        value = ARTICLES.sub("", value)
        value = re.sub(r"\s+([,.;:!?])", r"\1", value)
        value = re.sub(r"[ \t]{2,}", " ", value)
        value = re.sub(r"\s*/\s*", "/", value)
        value = re.sub(r"\s+\+\s+", " + ", value)
        return value.strip()

    compact = with_protected_segments(core, transform)
    if not compact:
        return text
    return f"{leading}{compact}{trailing}"


def compress_prompt_for_tokens(prompt: str) -> str:
    compressed_lines: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for line in prompt.splitlines():
        fence_match = LINE_FENCE_OPEN.match(line)
        if fence_match:
            marker = fence_match.group(1)
            marker_char = marker[0]
            if not in_fence:
                in_fence = True
                fence_char = marker_char
                fence_len = len(marker)
            elif marker_char == fence_char and len(marker) >= fence_len and not fence_match.group(2).strip():
                in_fence = False
                fence_char = ""
                fence_len = 0
            compressed_lines.append(line)
            continue

        if in_fence or line.startswith("#"):
            compressed_lines.append(line)
            continue

        bullet_match = LINE_BULLET_PREFIX.match(line)
        if bullet_match:
            compressed_lines.append(f"{bullet_match.group(1)}{compress_prose_fragment(bullet_match.group(2))}")
            continue

        quote_match = LINE_BLOCKQUOTE_PREFIX.match(line)
        if quote_match:
            compressed_lines.append(f"{quote_match.group(1)}{compress_prose_fragment(quote_match.group(2))}")
            continue

        compressed_lines.append(compress_prose_fragment(line))

    compressed = "\n".join(compressed_lines).strip()
    return compressed if compressed and compressed != prompt.strip() else prompt.strip()


def token_savings_payload(full_prompt: str, compact_prompt: str) -> dict[str, object]:
    full_tokens = estimate_tokens(full_prompt)
    compact_tokens = estimate_tokens(compact_prompt)
    saved_tokens = max(0, full_tokens - compact_tokens)
    saved_percent = round((saved_tokens / full_tokens) * 100) if full_tokens else 0
    return {
        "full_tokens": full_tokens,
        "compact_tokens": compact_tokens,
        "saved_tokens": saved_tokens,
        "saved_percent": saved_percent,
        "full_characters": len(full_prompt),
        "compact_characters": len(compact_prompt),
        "method": "local conservative prose compression",
    }


def count_acceptance_items(prompt: str) -> int:
    match = re.search(r"# Acceptance Criteria\s*(.*?)(?:\n# |\Z)", prompt, re.S)
    if not match:
        return 0
    return len(re.findall(r"^\s*(?:[-*]|\d+\.)\s+", match.group(1), re.M))


def analyze_prompt_quality(prompt: str) -> dict[str, object]:
    missing_sections = [section for section in REQUIRED_PROMPT_SECTIONS if section not in prompt]
    acceptance_items = count_acceptance_items(prompt)
    checks = [
        {
            "label": "Required sections",
            "passed": not missing_sections,
            "detail": "All sections present" if not missing_sections else f"{len(missing_sections)} sections missing",
        },
        {
            "label": "Acceptance criteria",
            "passed": acceptance_items >= 4,
            "detail": f"{acceptance_items} measurable items",
        },
        {
            "label": "State handling",
            "passed": bool(re.search(r"\b(empty|loading|error|failure|validation|edge case)", prompt, re.I)),
            "detail": "Mentions edge, loading, validation, or failure states",
        },
        {
            "label": "Security and privacy",
            "passed": bool(re.search(r"\b(security|privacy|secret|api key|environment variable|permission)", prompt, re.I)),
            "detail": "Mentions configuration, privacy, or security handling",
        },
        {
            "label": "Testing guidance",
            "passed": "# Testing and Validation" in prompt and bool(re.search(r"\b(test|verify|manual|automated|workflow)", prompt, re.I)),
            "detail": "Includes validation expectations",
        },
        {
            "label": "Strategic phases",
            "passed": "# Implementation Phases" in prompt and bool(re.search(r"\b(phase|milestone|discovery|foundation|verification)", prompt, re.I)),
            "detail": "Includes phased work with milestone checks",
        },
        {
            "label": "Runtime sequence",
            "passed": "# Startup and Run Sequence" in prompt and bool(re.search(r"\b(install|setup|start|run|command|local)", prompt, re.I)),
            "detail": "Includes startup or run expectations",
        },
        {
            "label": "Reference protocol",
            "passed": "# Reference and Research Protocol" in prompt and bool(re.search(r"\b(documentation|official docs|source|repository|github|reference|verify)", prompt, re.I)),
            "detail": "Includes repo/docs study guidance",
        },
        {
            "label": "Done criteria",
            "passed": "# Done When" in prompt and bool(re.search(r"\b(done|complete|finished|passes|verified|limitations)", prompt, re.I)),
            "detail": "Includes explicit completion criteria",
        },
    ]
    section_score = round(((len(REQUIRED_PROMPT_SECTIONS) - len(missing_sections)) / len(REQUIRED_PROMPT_SECTIONS)) * 55)
    signal_score = sum(5 for check in checks[1:] if check["passed"])
    length_score = 9 if count_words(prompt) >= 220 else 4
    score = max(0, min(100, section_score + signal_score + length_score))
    return {
        "score": score,
        "grade": quality_grade(score),
        "missing_sections": missing_sections,
        "acceptance_items": acceptance_items,
        "checks": checks,
    }


def quality_grade(score: int) -> str:
    if score >= 92:
        return "Excellent"
    if score >= 82:
        return "Strong"
    if score >= 70:
        return "Usable"
    return "Needs work"


def normalize_checklist(items: object) -> list[str]:
    if not isinstance(items, list):
        items = [str(items)]
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if cleaned:
        return cleaned[:7]
    return [
        "Clarified the implementation role",
        "Added complete project sections",
        "Added validation and acceptance criteria",
        "Added workflow, state, and risk coverage",
    ]


def finalize_result(result: dict[str, object], original_prompt: str, profile_key: str) -> dict[str, object]:
    optimized = normalize_project_prompt(str(result.get("optimized_prompt", "")), original_prompt, profile_key)
    compact = compress_prompt_for_tokens(optimized)
    savings = token_savings_payload(optimized, compact)
    result["optimized_prompt"] = optimized
    result["compact_prompt"] = compact
    result["token_savings"] = savings
    result["why_it_is_better"] = str(result.get("why_it_is_better", "")).strip() or (
        "The rough idea was converted into a complete implementation brief with clearer scope, requirements, deliverables, validation, and acceptance criteria."
    )
    result["checklist"] = normalize_checklist(result.get("checklist", []))
    result["profile"] = profile_payload(profile_key)
    result["quality"] = analyze_prompt_quality(optimized)
    result["stats"] = {
        "input_characters": len(original_prompt),
        "output_characters": len(optimized),
        "output_words": count_words(optimized),
        "compact_characters": len(compact),
        "compact_words": count_words(compact),
        "required_sections": len(REQUIRED_PROMPT_SECTIONS),
        "estimated_output_tokens": savings["full_tokens"],
        "estimated_compact_tokens": savings["compact_tokens"],
    }
    return result


class PromptOptimizerHandler(http.server.SimpleHTTPRequestHandler):
    models: list[str] = DEFAULT_MODELS
    timeout: int = DEFAULT_TIMEOUT

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        if self.path == "/api/config":
            self.send_json(
                {
                    "app_name": APP_NAME,
                    "profiles": [profile_payload(key) for key in PROMPT_PROFILES],
                    "models": self.models,
                    "max_prompt_characters": get_max_prompt_chars(),
                    "endpoint": "nvidia-nim",
                    "strategy": "phased-build-spec",
                }
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/optimize":
            self.send_error(404, "Not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON request."}, status=400)
            return

        prompt = str(body.get("prompt", "")).strip()
        profile_key = parse_profile(body.get("profile"))
        if not prompt:
            self.send_json({"error": "Please enter a prompt to optimize."}, status=400)
            return
        max_prompt_chars = get_max_prompt_chars()
        if len(prompt) > max_prompt_chars:
            self.send_json(
                {"error": f"Prompt is too long. Keep it under {max_prompt_chars:,} characters."},
                status=413,
            )
            return

        try:
            result = optimize_prompt(prompt, profile_key, self.models, self.timeout)
            result["source"] = "nvidia"
        except OptimizationError as exc:
            result = fallback_optimize(prompt, profile_key)
            result["source"] = "fallback"
            result["warning"] = str(exc)

        self.send_json(finalize_result(result, prompt, profile_key))

    def send_json(self, data: dict[str, object], status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def run_server(port: int, models: list[str], timeout: int) -> None:
    app_dir = Path(__file__).parent / "prompt_app"
    PromptOptimizerHandler.models = models
    PromptOptimizerHandler.timeout = timeout
    handler = lambda *args, **kwargs: PromptOptimizerHandler(  # noqa: E731
        *args,
        directory=str(app_dir),
        **kwargs,
    )

    with ReusableTCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Prompt optimizer running at http://127.0.0.1:{port}/")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the NVIDIA-powered prompt optimizer web app.")
    parser.add_argument("--port", type=int, default=8765, help="Local web server port.")
    parser.add_argument("--model", action="append", help="Model to try. Repeat or use comma-separated names.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Seconds per model request.")
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    run_server(args.port, parse_models(args.model), args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
