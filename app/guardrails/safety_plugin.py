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

"""Security & Anti-Jailbreak Guardrails Plugin for the Tech Interviewer Agent.

Validates input prompts against prompt injection attacks, prevents unauthorized
solution leakage, and enforces interview integrity policies.
"""

import logging
import re
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger("tech_interviewer.guardrails.safety")
logger.setLevel(logging.INFO)

# Regex patterns targeting adversarial prompt overrides and answer leakage attempts
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+previous\s+(instructions|prompts|rules)", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are\s+now", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"bypass\s+(safety|security|rules|guardrails)", re.IGNORECASE),
    re.compile(r"reveal\s+(api\s*key|secret|password|tokens?)", re.IGNORECASE),
    re.compile(r"(print|give|show|write)\s+(me\s+)?(the\s+)?(complete\s+|full\s+|exact\s+)?(code\s+)?solution", re.IGNORECASE),
]


class GuardrailResult(BaseModel):
    """Result returned by safety validation."""

    is_safe: bool
    risk_category: Optional[str] = None
    sanitized_input: str
    message: Optional[str] = None


class InterviewSafetyGuardrail:
    """Enforces safety guardrails and policy constraints across all interviewer turns."""

    @classmethod
    def validate_input(cls, user_prompt: str) -> GuardrailResult:
        """Inspect and sanitize incoming candidate prompt for injection attacks or rule violations.

        Args:
            user_prompt: Raw user input text.

        Returns:
            GuardrailResult with safety status and categorization.
        """
        if not user_prompt or not user_prompt.strip():
            return GuardrailResult(
                is_safe=False,
                risk_category="EMPTY_INPUT",
                sanitized_input="",
                message="Input prompt cannot be empty.",
            )

        for pattern in INJECTION_PATTERNS:
            if pattern.search(user_prompt):
                logger.warning({
                    "event": "prompt_injection_blocked",
                    "pattern": pattern.pattern,
                    "prompt_snippet": user_prompt[:80],
                })
                return GuardrailResult(
                    is_safe=False,
                    risk_category="POLICY_VIOLATION",
                    sanitized_input="",
                    message=(
                        "Interviewer Note: I cannot bypass the interview process or reveal the full solution. "
                        "Let's focus on solving the problem together step-by-step! Would you like a hint instead?"
                    ),
                )

        return GuardrailResult(
            is_safe=True,
            sanitized_input=user_prompt.strip(),
        )

    @classmethod
    def validate_output_self_eval(cls, response_text: str) -> str:
        """Self-evaluates model output to ensure confidential secrets or system prompts were not leaked."""
        lowered = response_text.lower()
        if "api_key" in lowered or "gemini_api_key" in lowered:
            logger.error({"event": "output_leakage_detected", "type": "credential_leak"})
            return "I am here to guide your technical interview. Let's continue with the coding problem."
        return response_text
