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

"""Unit tests for the Tech Interviewer Agent tools."""

import pytest
from app.tools import fetch_question, get_hint, execute_code_sandbox


def test_fetch_question_by_topic():
    """Test fetching a question filtered by topic."""
    result = fetch_question(topic="Arrays")
    assert result["status"] == "success"
    assert result["question_id"] == "two-sum"
    assert "Two Sum" in result["title"]
    assert "starter_code" in result


def test_fetch_question_fallback():
    """Test fallback behavior when no matching topic exists."""
    result = fetch_question(topic="NonExistentTopic")
    assert result["status"] == "success"
    assert "question_id" in result


def test_get_hint_progression():
    """Test retrieving sequential progressive hints."""
    # First hint
    h1 = get_hint(question_id="two-sum", hint_index=0)
    assert h1["status"] == "success"
    assert h1["hint_number"] == 1
    assert h1["has_more_hints"] is True

    # Out of bounds hint index
    h_out = get_hint(question_id="two-sum", hint_index=99)
    assert h_out["status"] == "success"
    assert h_out["has_more_hints"] is False


def test_execute_code_sandbox_correct_solution():
    """Test executing a correct solution for Two Sum."""
    valid_code = """
def two_sum(nums: list[int], target: int) -> list[int]:
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []
"""
    res = execute_code_sandbox(question_id="two-sum", code=valid_code)
    assert res["status"] == "success"
    assert res["all_passed"] is True
    assert res["passed_tests"] == res["total_tests"]


def test_execute_code_sandbox_failing_solution():
    """Test executing a solution that produces incorrect outputs."""
    wrong_code = """
def two_sum(nums: list[int], target: int) -> list[int]:
    return [0, 0]
"""
    res = execute_code_sandbox(question_id="two-sum", code=wrong_code)
    assert res["status"] == "success"
    assert res["all_passed"] is False
    assert res["passed_tests"] < res["total_tests"]


def test_execute_code_sandbox_syntax_error():
    """Test executing invalid Python code."""
    broken_code = """
def two_sum(nums, target)
    return "missing colon"
"""
    res = execute_code_sandbox(question_id="two-sum", code=broken_code)
    assert res["status"] == "error"
    assert res["error_type"] == "Compilation/SyntaxError"
    assert res["all_passed"] is False
