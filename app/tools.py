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

"""Tools module for the Tech Interviewer GenAI Agent.

Provides tools for:
1. Question retrieval (Problem Librarian)
2. Hint generation (Problem Librarian)
3. Python Sandbox execution with test-case validation (Code Evaluator)
4. Human-In-The-Loop submission confirmation (Lead Interviewer)
"""

import json
import logging
import os
import sys
from typing import Any
from pydantic import BaseModel, Field
from google.adk.tools import ToolContext

logger = logging.getLogger("tech_interviewer.tools")
logger.setLevel(logging.INFO)

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "questions.json")


def _load_questions() -> list[dict[str, Any]]:
    """Helper to load questions from the json data file."""
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# =====================================================================
# 1. Question Fetching Tool & Schemas
# =====================================================================


class FetchQuestionSchema(BaseModel):
    """Schema for querying a question."""

    topic: str | None = Field(
        None, description="Topic of the question (e.g., Arrays, Strings, Dynamic Programming)."
    )
    difficulty: str | None = Field(
        None, description="Difficulty level ('Easy', 'Medium', 'Hard')."
    )


def fetch_question(
    topic: str | None = None,
    difficulty: str | None = None,
) -> dict[str, Any]:
    """Retrieves an interview coding question based on topic and difficulty preferences.

    Args:
        topic: Optional topic filter (e.g. 'Arrays', 'Strings', 'Dynamic Programming').
        difficulty: Optional difficulty filter ('Easy', 'Medium', 'Hard').

    Returns:
        A dictionary containing question details (id, title, topic, difficulty, description, starter_code).
    """
    logger.info({"event": "tool_start", "tool": "fetch_question", "topic": topic, "difficulty": difficulty})
    questions = _load_questions()
    if not questions:
        return {"status": "error", "message": "No questions available in the question bank."}

    matched = []
    for q in questions:
        match_topic = True if not topic else (topic.lower() in q.get("topic", "").lower())
        match_diff = True if not difficulty else (difficulty.lower() == q.get("difficulty", "").lower())
        if match_topic and match_diff:
            matched.append(q)

    # Fallback to any matched or default first question
    selected = matched[0] if matched else questions[0]

    result = {
        "status": "success",
        "question_id": selected["id"],
        "title": selected["title"],
        "topic": selected["topic"],
        "difficulty": selected["difficulty"],
        "description": selected["description"],
        "starter_code": selected["starter_code"],
    }
    logger.info({"event": "tool_success", "tool": "fetch_question", "question_id": selected["id"]})
    return result


# =====================================================================
# 2. Hint Tool & Schemas
# =====================================================================


class GetHintSchema(BaseModel):
    """Schema for requesting a hint."""

    question_id: str = Field(..., description="Unique ID of the question.")
    hint_index: int = Field(0, description="0-indexed hint number (0 for 1st hint, 1 for 2nd hint, etc.).")


def get_hint(question_id: str, hint_index: int = 0) -> dict[str, Any]:
    """Retrieves a progressive hint for a specific question to guide the candidate.

    Args:
        question_id: The unique ID of the question.
        hint_index: 0-indexed number indicating which progressive hint to retrieve.

    Returns:
        A dictionary containing the hint text and whether further hints are available.
    """
    logger.info({"event": "tool_start", "tool": "get_hint", "question_id": question_id, "hint_index": hint_index})
    questions = _load_questions()
    target = next((q for q in questions if q["id"] == question_id), None)

    if not target:
        return {"status": "error", "message": f"Question with ID '{question_id}' not found."}

    hints = target.get("hints", [])
    if not hints:
        return {"status": "success", "hint": "No specific hints available for this problem.", "has_more_hints": False}

    if hint_index >= len(hints):
        return {
            "status": "success",
            "hint": hints[-1],
            "message": "All progressive hints have already been provided.",
            "has_more_hints": False,
        }

    return {
        "status": "success",
        "hint": hints[hint_index],
        "hint_number": hint_index + 1,
        "total_hints": len(hints),
        "has_more_hints": (hint_index + 1) < len(hints),
    }


# =====================================================================
# 3. Python Sandbox Code Execution Tool
# =====================================================================


class ExecuteCodeSchema(BaseModel):
    """Schema for running candidate code against test cases."""

    question_id: str = Field(..., description="The unique ID of the question being solved.")
    code: str = Field(..., description="The candidate's Python solution code.")


def execute_code_sandbox(question_id: str, code: str) -> dict[str, Any]:
    """Safely executes candidate Python code against the question's predefined test cases.

    Args:
        question_id: The ID of the question to test against.
        code: The Python code submitted by the candidate.

    Returns:
        A dictionary containing execution results, test case pass/fail counts, and runtime errors.
    """
    logger.info({"event": "tool_start", "tool": "execute_code_sandbox", "question_id": question_id})
    questions = _load_questions()
    target = next((q for q in questions if q["id"] == question_id), None)

    if not target:
        return {"status": "error", "message": f"Question '{question_id}' not found."}

    entry_point = target.get("entry_point")
    test_cases = target.get("test_cases", [])

    # Environment isolation for safe exec
    sandbox_globals: dict[str, Any] = {
        "__builtins__": {
            "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
            "enumerate": enumerate, "filter": filter, "float": float, "int": int,
            "isinstance": isinstance, "len": len, "list": list, "map": map,
            "max": max, "min": min, "range": range, "reversed": reversed,
            "round": round, "set": set, "slice": slice, "sorted": sorted,
            "str": str, "sum": sum, "tuple": tuple, "zip": zip,
        }
    }
    sandbox_locals: dict[str, Any] = {}

    try:
        # Execute user code definition
        exec(code, sandbox_globals, sandbox_locals)
    except Exception as e:
        logger.error({"event": "execution_syntax_error", "error": str(e)})
        return {
            "status": "error",
            "error_type": "Compilation/SyntaxError",
            "message": f"Error during code execution: {type(e).__name__}: {str(e)}",
            "passed_tests": 0,
            "total_tests": len(test_cases),
            "all_passed": False,
        }

    if entry_point not in sandbox_locals:
        return {
            "status": "error",
            "error_type": "EntryPointMissing",
            "message": f"Function '{entry_point}' was not found in the submitted code.",
            "passed_tests": 0,
            "total_tests": len(test_cases),
            "all_passed": False,
        }

    candidate_func = sandbox_locals[entry_point]
    test_results = []
    passed_count = 0

    for i, tc in enumerate(test_cases):
        inputs = tc.get("input", {})
        expected = tc.get("expected_output")
        try:
            actual = candidate_func(**inputs)
            passed = (actual == expected)
            if passed:
                passed_count += 1
            test_results.append({
                "test_case": i + 1,
                "input": inputs,
                "expected": expected,
                "actual": actual,
                "passed": passed,
            })
        except Exception as e:
            test_results.append({
                "test_case": i + 1,
                "input": inputs,
                "expected": expected,
                "error": f"{type(e).__name__}: {str(e)}",
                "passed": False,
            })

    all_passed = (passed_count == len(test_cases))
    logger.info({
        "event": "tool_success",
        "tool": "execute_code_sandbox",
        "passed_tests": passed_count,
        "total_tests": len(test_cases),
        "all_passed": all_passed,
    })

    return {
        "status": "success",
        "all_passed": all_passed,
        "passed_tests": passed_count,
        "total_tests": len(test_cases),
        "test_results": test_results,
        "optimal_complexity": target.get("optimal_complexity", {}),
    }


# =====================================================================
# 4. Human-In-The-Loop (HITL) Submission Tool
# =====================================================================


class FinalSubmissionSchema(BaseModel):
    """Schema for final code submission."""

    question_id: str = Field(..., description="ID of the question.")
    code: str = Field(..., description="Candidate's finalized code solution.")


def submit_final_solution(
    question_id: str,
    code: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Handles candidate final code submission with native Human-in-the-Loop (HITL) approval.

    Pauses execution on first call to ask user confirmation. Resumes once confirmed.
    """
    logger.info({"event": "tool_start", "tool": "submit_final_solution", "question_id": question_id})

    # SCENARIO 1: First call -> Pause execution and request user approval
    if not tool_context.tool_confirmation:
        tool_context.request_confirmation(
            hint=f"⚠️ Final Submission Confirmation: Are you ready to submit your code for '{question_id}' for official evaluation and grading?",
            payload={"question_id": question_id, "code_length": len(code)},
        )
        return {
            "status": "pending_confirmation",
            "message": "Awaiting user confirmation in UI before finalizing the evaluation.",
        }

    # SCENARIO 2: Resumed execution after user interaction
    if tool_context.tool_confirmation.confirmed:
        logger.info({"event": "submission_confirmed", "question_id": question_id})
        return {
            "status": "confirmed",
            "message": "Submission confirmed by candidate. Proceed to grade with Code Evaluator.",
            "question_id": question_id,
            "code": code,
        }
    else:
        logger.info({"event": "submission_rejected", "question_id": question_id})
        return {
            "status": "cancelled",
            "message": "Candidate chose not to submit yet. Allow them to continue working on their code.",
        }
