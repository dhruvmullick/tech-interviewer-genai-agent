# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Multi-Agent Orchestration for the Tech Interviewer GenAI Agent.

Architecture:
- Coordinator (Lead Interviewer): High-reasoning Gemini Flash model for conversation orchestration.
- Problem Librarian: Low-reasoning Gemini Flash model for fast question and hint lookups.
- Code Evaluator: Low-reasoning Gemini Flash model for structured code execution review.
"""

from google.adk.agents import Agent
from google.adk.apps import App, ResumabilityConfig
from google.adk.apps.app import EventsCompactionConfig
from google.adk.models import Gemini
from google.genai import types

from app.constitution import (
    COORDINATOR_CONSTITUTION,
    EVALUATOR_CONSTITUTION,
    LIBRARIAN_CONSTITUTION,
)
from app.tools import (
    fetch_question,
    get_hint,
    execute_code_sandbox,
    submit_final_solution,
)

# Models (Strategic Model Routing)
PRO_MODEL = "gemini-3.1-pro"
FLASH_MODEL = "gemini-3.6-flash"

# ============================================================================
# Sub-Agent 1: Problem Librarian (Low Latency / Fast Retrieval - Flash)
# ============================================================================
problem_librarian = Agent(
    name="problem_librarian",
    description="Specialized agent to query the question bank for coding problems, hidden test cases, and progressive hints.",
    model=Gemini(
        model=FLASH_MODEL,
        config=types.GenerateContentConfig(
            temperature=0.2,
        ),
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=LIBRARIAN_CONSTITUTION,
    tools=[
        fetch_question,
        get_hint,
    ],
)

# ============================================================================
# Sub-Agent 2: Code Evaluator (Deep Reasoning / Analytical Code Review - Pro)
# ============================================================================
code_evaluator = Agent(
    name="code_evaluator",
    description="Specialized agent to run candidate code in a sandbox, verify test cases, analyze Big-O complexity, and generate a scorecard.",
    model=Gemini(
        model=PRO_MODEL,
        config=types.GenerateContentConfig(
            temperature=0.1,
        ),
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=EVALUATOR_CONSTITUTION,
    tools=[
        execute_code_sandbox,
    ],
)

from google.adk.agents.callback_context import CallbackContext
from app.guardrails.safety_plugin import InterviewSafetyGuardrail
from app.memory.async_memory import memory_store


# ============================================================================
# ADK Lifecycle Callbacks: Security Guardrails & Asynchronous Memory
# ============================================================================
def pre_interview_guardrail_hook(ctx: CallbackContext) -> None:
    """Pre-turn guardrail hook inspecting candidate prompts for injection attacks."""
    user_prompt = ""
    if ctx.user_content and hasattr(ctx.user_content, "parts"):
        user_prompt = " ".join([p.text for p in ctx.user_content.parts if hasattr(p, "text") and p.text])
    elif isinstance(ctx.user_content, str):
        user_prompt = ctx.user_content

    if user_prompt:
        guard_res = InterviewSafetyGuardrail.validate_input(user_prompt)
        if not guard_res.is_safe:
            ctx.user_content = guard_res.message or "Interviewer policy violation detected."


def post_turn_memory_hook(ctx: CallbackContext) -> None:
    """Post-turn non-blocking memory hook dispatching background persistence & compaction."""
    session_id = ctx.session.id if ctx.session and hasattr(ctx.session, "id") else "default-session"
    user_prompt = ""
    if ctx.user_content and hasattr(ctx.user_content, "parts"):
        user_prompt = " ".join([p.text for p in ctx.user_content.parts if hasattr(p, "text") and p.text])
    elif isinstance(ctx.user_content, str):
        user_prompt = str(ctx.user_content)

    agent_output = str(ctx.output) if ctx.output else ""
    memory_store.record_turn_async(
        session_id=session_id,
        user_input=user_prompt,
        agent_response=agent_output,
    )


# ============================================================================
# Root Agent: Lead Technical Interviewer (Coordinator / Orchestration - Pro)
# ============================================================================
root_agent = Agent(
    name="lead_interviewer",
    description="Primary technical interviewer managing the interview stages, dialogue, hints, and final submission.",
    model=Gemini(
        model=PRO_MODEL,
        config=types.GenerateContentConfig(
            temperature=0.7,
        ),
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=COORDINATOR_CONSTITUTION,
    tools=[
        submit_final_solution,
    ],
    sub_agents=[
        problem_librarian,
        code_evaluator,
    ],
    before_agent_callback=pre_interview_guardrail_hook,
    after_agent_callback=post_turn_memory_hook,
)

# ============================================================================
# ADK Application Definition with Memory & HITL Resumability
# ============================================================================
app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=5,
        overlap_size=1,
    ),
)
