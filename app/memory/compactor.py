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

"""History Compactor for Interview Context Management.

Implements token-aware sliding window compaction that summarizes older conversational turns,
condenses verbose code executions and hint interactions, and preserves candidate progress metrics.
"""

import logging
from typing import Any

logger = logging.getLogger("tech_interviewer.memory.compactor")
logger.setLevel(logging.INFO)


class InterviewHistoryCompactor:
    """Manages chat history compaction to maintain optimal LLM context size during long interviews."""

    def __init__(
        self,
        max_turns_before_compaction: int = 6,
        keep_recent_turns: int = 2,
    ):
        """Initialize compactor parameters.

        Args:
            max_turns_before_compaction: Maximum full turns before triggering compaction.
            keep_recent_turns: Number of recent turns to preserve in full fidelity.
        """
        self.max_turns = max_turns_before_compaction
        self.keep_recent = keep_recent_turns

    def should_compact(self, history_turns: list[dict[str, Any]]) -> bool:
        """Evaluate if conversation history exceeds threshold for compaction."""
        return len(history_turns) > self.max_turns

    def compact_history(
        self,
        history_turns: list[dict[str, Any]],
        existing_summary: str | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Compact older history turns into a concise executive summary of the interview.

        Args:
            history_turns: Full chronological list of conversation turn objects.
            existing_summary: Previously accumulated summary string.

        Returns:
            Tuple of (updated_summary_string, preserved_recent_turns).
        """
        if not self.should_compact(history_turns):
            return existing_summary or "", history_turns

        turns_to_compact = history_turns[: -self.keep_recent]
        recent_turns = history_turns[-self.keep_recent :]

        extracted_facts: list[str] = []
        if existing_summary:
            extracted_facts.append(f"Prior Context: {existing_summary}")

        for turn in turns_to_compact:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            tool_calls = turn.get("tool_calls", [])

            if role == "user":
                extracted_facts.append(f"Candidate asked/submitted: {content[:150]}")
            elif role == "model":
                summary_point = f"Interviewer responded: {content[:200]}..." if len(content) > 200 else content
                extracted_facts.append(summary_point)

            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.get("name", "tool")
                    args = tc.get("args", {})
                    extracted_facts.append(f"Tool executed: {tool_name}({args})")

        compacted_summary = " | ".join(extracted_facts)
        logger.info({
            "event": "history_compacted",
            "original_turns": len(history_turns),
            "preserved_turns": len(recent_turns),
            "summary_length": len(compacted_summary),
        })

        return compacted_summary, recent_turns
