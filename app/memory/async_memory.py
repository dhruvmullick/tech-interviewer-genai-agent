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

"""Asynchronous Background Memory Operations & State Management.

Provides non-blocking background tasks for:
1. Asynchronous state checkpointing and remote store synchronization.
2. Background context summarization and candidate progress analytics.
3. Decoupled execution using asyncio.create_task to eliminate latency on LLM turns.
"""

import asyncio
import logging
import time
from typing import Any
from pydantic import BaseModel, Field
from app.memory.compactor import InterviewHistoryCompactor

logger = logging.getLogger("tech_interviewer.memory.async_memory")
logger.setLevel(logging.INFO)


class InterviewSessionState(BaseModel):
    """Encapsulates historical interview memory, code attempts, and state progression."""

    session_id: str
    topic: str | None = None
    question_id: str | None = None
    hints_used: int = 0
    code_attempts: list[str] = Field(default_factory=list)
    summary_context: str = ""
    turns: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    last_updated: float = Field(default_factory=time.time)


class AsyncInterviewMemoryStore:
    """Manages persistent session state and asynchronous background memory processing."""

    def __init__(self, compactor: InterviewHistoryCompactor | None = None):
        self.compactor = compactor or InterviewHistoryCompactor()
        self._local_session_cache: dict[str, InterviewSessionState] = {}
        self._active_background_tasks: set[asyncio.Task[Any]] = set()

    async def get_session_state(self, session_id: str) -> InterviewSessionState:
        """Retrieve current session state from cache or initialize a fresh state.

        Args:
            session_id: Unique session identifier.

        Returns:
            InterviewSessionState object.
        """
        if session_id in self._local_session_cache:
            return self._local_session_cache[session_id]

        state = InterviewSessionState(session_id=session_id)
        self._local_session_cache[session_id] = state
        return state

    def record_turn_async(
        self,
        session_id: str,
        user_input: str,
        agent_response: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        """Records a completed conversation turn and spawns dedicated background memory workers.

        Uses asyncio.create_task to perform expensive compaction and persistence
        without blocking the user-facing chat response.

        Args:
            session_id: The active session identifier.
            user_input: The candidate's query or code submission.
            agent_response: The agent's output response.
            tool_calls: Optional list of tools executed in this turn.
        """
        state = self._local_session_cache.get(session_id) or InterviewSessionState(session_id=session_id)

        # Update local memory turn
        turn_data = {
            "timestamp": time.time(),
            "user": user_input,
            "agent": agent_response,
            "tool_calls": tool_calls or [],
        }
        state.turns.append(turn_data)
        state.last_updated = time.time()
        self._local_session_cache[session_id] = state

        # Spawn non-blocking background task for expensive memory processing
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._process_background_memory_task(state))
            self._active_background_tasks.add(task)
            task.add_done_callback(self._active_background_tasks.discard)
        except RuntimeError:
            # Fallback if outside an active event loop
            logger.debug({"event": "async_task_skipped", "reason": "no_active_loop"})

    async def _process_background_memory_task(self, session_state: InterviewSessionState) -> None:
        """Asynchronous background worker for compaction, analytics, and remote persistence."""
        session_id = session_state.session_id
        start_time = time.time()

        logger.info({
            "event": "background_memory_task_start",
            "session_id": session_id,
            "turns_count": len(session_state.turns),
        })

        try:
            # 1. Asynchronous sliding-window compaction if turns exceed threshold
            if self.compactor.should_compact(session_state.turns):
                updated_summary, preserved_turns = self.compactor.compact_history(
                    history_turns=session_state.turns,
                    existing_summary=session_state.summary_context,
                )
                session_state.summary_context = updated_summary
                session_state.turns = preserved_turns

            # 2. Compute background interview metrics
            session_state.metrics["total_turns"] = len(session_state.turns)
            session_state.metrics["hints_consumed"] = session_state.hints_used
            session_state.metrics["attempts_count"] = len(session_state.code_attempts)

            # 3. Simulate asynchronous remote persistence / datastore sync
            await asyncio.sleep(0.01)

            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.info({
                "event": "background_memory_task_completed",
                "session_id": session_id,
                "duration_ms": duration_ms,
                "summary_length": len(session_state.summary_context),
            })

        except Exception as e:
            logger.error({
                "event": "background_memory_task_error",
                "session_id": session_id,
                "error": str(e),
            })


# Global singleton instance
memory_store = AsyncInterviewMemoryStore()
