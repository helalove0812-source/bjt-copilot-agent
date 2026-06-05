from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.types import HwConfig

from ai.action_recommender import recommend_actions
from ai.agent_orchestration import orchestrate_turn_with_llm
from ai.agent_step_review import review_agent_step_with_llm
from ai.assistant import summarize_execution_with_ai, summarize_plan_with_ai
from ai.autonomy import refine_plan_after_execution
from ai.conversation import AIConversationState, AIIntent, apply_intent_to_plan, interpret_user_message_with_debug
from ai.datasheet_lookup import lookup_datasheet_profile
from ai.rules import diagnose_context, diagnose_tags
from ai.safety import evaluate_execution_request
from ai.test_planner import TestPlan
from ai.tools import execute_plan, preflight_plan
from ai.transistor_db import TransistorProfile, lookup_transistor


@dataclass(frozen=True)
class AgentToolDescriptor:
    name: str
    layer: str
    description: str


@dataclass(frozen=True)
class AgentToolRegistry:
    """Capability boundary for BJTagent orchestration.

    TestAgent should depend on this registry instead of importing every domain
    function directly. That keeps the runtime small and makes future LLM tool
    selection or test doubles straightforward.
    """

    interpret_intent: Callable[
        [str, AIConversationState],
        tuple[AIIntent, bool, str, dict, dict],
    ]
    orchestrate_turn: Callable[..., object]
    review_step: Callable[..., object]
    apply_intent_to_plan: Callable[..., TestPlan]
    summarize_plan: Callable[[TestPlan, str], tuple[str, bool, str, dict]]
    refine_plan: Callable[..., object]
    evaluate_execution_request: Callable[..., object]
    execute_plan: Callable[..., dict]
    preflight_plan: Callable[..., dict]
    summarize_execution: Callable[[dict], tuple[str, bool, str, dict]]
    diagnose_context: Callable[..., str]
    diagnose_tags: Callable[..., list[str]]
    recommend_actions: Callable[..., list[dict]]
    lookup_transistor: Callable[[str], TransistorProfile]
    lookup_datasheet_profile: Callable[..., object]

    def describe(self) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor("orchestrate_turn", "orchestration", "Select the visible tool path for a turn with LLM assistance."),
            AgentToolDescriptor("review_step", "orchestration", "Review each visible agent step with LLM assistance."),
            AgentToolDescriptor("interpret_intent", "cognition", "Parse user text into a structured AIIntent."),
            AgentToolDescriptor("apply_intent_to_plan", "planning", "Create or modify a safe TestPlan from intent and state."),
            AgentToolDescriptor("lookup_datasheet_profile", "knowledge", "Search and extract datasheet ratings for unknown models."),
            AgentToolDescriptor("summarize_plan", "language", "Explain a generated plan with optional LLM assistance."),
            AgentToolDescriptor("refine_plan", "autonomy", "Adjust a plan from execution evidence and user intent."),
            AgentToolDescriptor("evaluate_execution_request", "safety", "Decide whether execution is allowed, denied, or needs confirmation."),
            AgentToolDescriptor("preflight_plan", "safety", "Produce dry-run hardware preflight checks."),
            AgentToolDescriptor("execute_plan", "execution", "Run a plan in simulation or confirmed hardware mode."),
            AgentToolDescriptor("summarize_execution", "language", "Explain execution results with optional LLM assistance."),
            AgentToolDescriptor("diagnose_context", "diagnosis", "Generate local diagnosis text from symptoms/logs/measurements."),
            AgentToolDescriptor("diagnose_tags", "diagnosis", "Map symptoms/logs/measurements to stable diagnosis tags."),
            AgentToolDescriptor("recommend_actions", "actions", "Convert diagnosis tags into structured next actions."),
            AgentToolDescriptor("lookup_transistor", "knowledge", "Read built-in or user-confirmed transistor profiles."),
        ]


def default_agent_tools() -> AgentToolRegistry:
    def _interpret_intent(
        text: str,
        state: AIConversationState,
        *,
        default_mode: str = "simulation",
    ) -> tuple[AIIntent, bool, str, dict, dict]:
        return interpret_user_message_with_debug(text, state, default_mode=default_mode)

    def _execute_plan(
        plan: TestPlan,
        *,
        mode: str = "simulation",
        output_dir: Path | None = None,
        allow_hardware: bool = False,
        token_valid: bool | None = None,
    ) -> dict:
        return execute_plan(
            plan,
            mode=mode,
            output_dir=output_dir,
            allow_hardware=allow_hardware,
            token_valid=token_valid,
        )

    return AgentToolRegistry(
        interpret_intent=_interpret_intent,
        orchestrate_turn=orchestrate_turn_with_llm,
        review_step=review_agent_step_with_llm,
        apply_intent_to_plan=apply_intent_to_plan,
        summarize_plan=summarize_plan_with_ai,
        refine_plan=refine_plan_after_execution,
        evaluate_execution_request=evaluate_execution_request,
        execute_plan=_execute_plan,
        preflight_plan=preflight_plan,
        summarize_execution=summarize_execution_with_ai,
        diagnose_context=diagnose_context,
        diagnose_tags=diagnose_tags,
        recommend_actions=recommend_actions,
        lookup_transistor=lookup_transistor,
        lookup_datasheet_profile=lookup_datasheet_profile,
    )
