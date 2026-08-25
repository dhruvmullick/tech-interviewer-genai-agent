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

"""Unit tests for History Compactor and Asynchronous Memory Store."""

import asyncio
import pytest
from app.memory.compactor import InterviewHistoryCompactor
from app.memory.async_memory import AsyncInterviewMemoryStore, InterviewSessionState


def test_compactor_threshold_logic():
    """Test that compaction triggers only when turn threshold is exceeded."""
    compactor = InterviewHistoryCompactor(max_turns_before_compaction=3, keep_recent_turns=1)
    history = [
        {"role": "user", "content": "Turn 1"},
        {"role": "model", "content": "Turn 2"},
    ]
    assert compactor.should_compact(history) is False

    history.append({"role": "user", "content": "Turn 3"})
    history.append({"role": "model", "content": "Turn 4"})
    assert compactor.should_compact(history) is True


def test_compactor_summary_extraction():
    """Test that older turns are summarized while preserving recent turns."""
    compactor = InterviewHistoryCompactor(max_turns_before_compaction=2, keep_recent_turns=1)
    history = [
        {"role": "user", "content": "I want an array problem", "tool_calls": []},
        {"role": "model", "content": "Here is Two Sum", "tool_calls": [{"name": "fetch_question", "args": {"topic": "Arrays"}}]},
        {"role": "user", "content": "I am working on my solution", "tool_calls": []},
    ]
    summary, preserved = compactor.compact_history(history)
    assert len(preserved) == 1
    assert preserved[0]["content"] == "I am working on my solution"
    assert "Two Sum" in summary or "Candidate asked" in summary


@pytest.mark.asyncio
async def test_async_memory_store_turn_recording():
    """Test async memory store turn recording and session caching."""
    store = AsyncInterviewMemoryStore()
    session_id = "test-session-123"

    state = await store.get_session_state(session_id)
    assert state.session_id == session_id
    assert len(state.turns) == 0

    store.record_turn_async(
        session_id=session_id,
        user_input="Can I have a hint?",
        agent_response="Use a Hash Map.",
        tool_calls=[{"name": "get_hint", "args": {"question_id": "two-sum"}}],
    )
    # Give event loop a tick to process background tasks
    await asyncio.sleep(0.05)

    updated_state = await store.get_session_state(session_id)
    assert len(updated_state.turns) >= 1
