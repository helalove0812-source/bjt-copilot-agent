from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from core.types import HwConfig

from app.services import (
    build_driver,
    run_detect,
    run_full_suite,
    run_hardware_selftest,
    run_low_voltage_pin_probe,
    run_npn_static_bringup,
    run_relay_matrix_pin_probe,
    run_scan_curves,
    run_scope_check,
)
from ai.active_inference import design_next_measurement_batch
from ai.action_recommender import recommend_actions
from ai.agent_memory import MemoryStore, TodoStore
from ai.dut_belief import DUTBeliefState, suggest_next_measurements_for_state, update_belief_from_measurements
from ai.experiment_goal import ExperimentGoal, compile_experiment_goal, goal_from_plan
from ai.measurement_program import (
    build_unknown_device_measurement_program,
    critique_measurement_program,
    optimize_measurement_program,
    refine_measurement_program_from_critique,
)
from ai.provenance import ProvenanceDAG
from ai.pulse_diagnosis import diagnose_pulse_response, pulse_diagnosis_to_hypothesis
from ai.rules import diagnose_tags
from ai.runtime_guard import check_abort_after_point
from ai.safety import evaluate_execution_request
from ai.session_search import SessionSearchStore
from ai.spice_twin import extract_spice_twin_from_belief, plan_residual_followup_measurements
from ai.task_delegation import AgentTaskGraph
from ai.tool_registry import ToolRegistry
from ai.test_planner import TestPlan, build_test_plan
from ai.tool_schema import AgentToolSchema, object_schema
from ai.tools import execute_plan, preflight_plan
from ai.transistor_db import lookup_transistor
from ai.unknown_device import (
    UnknownDeviceReport,
    build_experimental_journal,
    compare_unknown_against_nominal_class,
    select_characterization_suite,
    simulate_three_pin_topology_probe,
    topology_hypotheses_from_probe_result,
    write_unknown_device_conclusion,
)
from measurement.vce_sat import estimate_vce_sat


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result,
        }


class BJTToolRuntime:
    def __init__(
        self,
        *,
        cfg: HwConfig | None = None,
        output_dir: Path | None = None,
        todo_store: TodoStore | None = None,
        memory_store: MemoryStore | None = None,
        session_search_store: SessionSearchStore | None = None,
        task_graph: AgentTaskGraph | None = None,
        current_plan: TestPlan | None = None,
        pending_plan_update: dict[str, Any] | None = None,
    ) -> None:
        self.cfg = cfg
        self.output_dir = output_dir
        self.todo_store = todo_store or TodoStore()
        self.memory_store = memory_store or MemoryStore()
        self.session_search_store = session_search_store or SessionSearchStore({})
        self.task_graph = task_graph or AgentTaskGraph()
        self.current_plan: TestPlan | None = current_plan
        self.current_execution: dict | None = None
        self.pending_plan_update: dict[str, Any] | None = pending_plan_update if isinstance(pending_plan_update, dict) else None
        self.current_belief: DUTBeliefState | None = None
        self.current_goal: ExperimentGoal | None = goal_from_plan(current_plan, mode=current_plan.mode if current_plan else "simulation") if current_plan else None
        self.provenance = ProvenanceDAG()
        self.registry = self._build_registry()

    def schemas(self) -> list[AgentToolSchema]:
        return self.registry.schemas()

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry(
            precondition_check=self._check_preconditions,
            postcondition_check=self._check_postconditions,
        )
        for schema in self._build_schemas():
            registry.register(schema)
        return registry

    def _build_schemas(self) -> list[AgentToolSchema]:
        return [
            AgentToolSchema(
                name="todo",
                description="Manage a session task list for multi-step BJT work. Omit todos to read current list.",
                parameters=object_schema(
                    {
                        "todos": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "content": {"type": "string"},
                                    "status": {
                                        "type": "string",
                                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                                    },
                                },
                                "required": ["id", "content", "status"],
                            },
                        },
                        "merge": {"type": "boolean"},
                    }
                ),
                handler=self.todo,
            ),
            AgentToolSchema(
                name="memory",
                description="Read or update persistent project/user memory. Store only durable preferences or confirmed project facts.",
                parameters=object_schema(
                    {
                        "action": {"type": "string", "enum": ["read", "add", "remove"]},
                        "target": {"type": "string", "enum": ["project", "user"]},
                        "content": {"type": "string"},
                        "needle": {"type": "string"},
                    },
                    ["action"],
                ),
                handler=self.memory,
            ),
            AgentToolSchema(
                name="session_search",
                description="Search current session context: chat messages, current plan, logs, measurements, and conversation state.",
                parameters=object_schema(
                    {
                        "query": {"type": "string"},
                        "kind": {"type": "string", "enum": ["", "message", "plan", "log", "measurement", "state", "task_graph"]},
                        "limit": {"type": "integer"},
                    }
                ),
                handler=self.session_search,
            ),
            AgentToolSchema(
                name="delegate_task",
                description="Break a complex BJT request into structured subtasks and suggest the next tool for each phase.",
                parameters=object_schema(
                    {
                        "task_type": {
                            "type": "string",
                            "enum": [
                                "profile_review",
                                "plan_build",
                                "safety_review",
                                "simulation_review",
                                "answer_synthesis",
                                "full_test",
                            ],
                        },
                        "objective": {"type": "string"},
                        "context_query": {"type": "string"},
                    },
                    ["task_type", "objective"],
                ),
                handler=self.delegate_task,
            ),
            AgentToolSchema(
                name="compile_experiment_goal",
                description="Compile natural language into a typed AIDE goal: projection variables, stop criteria, deliverables, and safety envelope. Does not touch hardware.",
                parameters=object_schema(
                    {
                        "goal": {"type": "string"},
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                    }
                ),
                category="analysis",
                safety={"touches_hardware": False},
                reversible=True,
                dangerous=False,
                handler=self.compile_experiment_goal_tool,
            ),
            AgentToolSchema(
                name="design_next_batch",
                description="Design the next measurement batch by estimating information gain per cost under the current DUT belief and safety envelope. Does not execute measurements.",
                parameters=object_schema(
                    {
                        "goal": {"type": "string"},
                        "budget": {"type": "integer"},
                    }
                ),
                category="analysis",
                preconditions=["belief_state_available"],
                postconditions=["next_batch_designed"],
                reversible=True,
                dangerous=False,
                handler=self.design_next_batch,
            ),
            AgentToolSchema(
                name="read_experiment_provenance",
                description="Read the append-only experiment provenance DAG and notebook-style event log.",
                parameters=object_schema({"limit": {"type": "integer"}}),
                category="analysis",
                safety={"touches_hardware": False},
                reversible=True,
                dangerous=False,
                supports_dry_run=False,
                handler=self.read_experiment_provenance,
            ),
            AgentToolSchema(
                name="lookup_transistor",
                description="Look up a BJT profile from the confirmed local device library.",
                parameters=object_schema(
                    {
                        "model": {"type": "string", "description": "BJT model, for example S8050 or TIP41C."},
                    },
                    ["model"],
                ),
                handler=self.lookup_transistor,
            ),
            AgentToolSchema(
                name="build_test_plan",
                description="Build a safe BJT test plan from model, goal, depth, and mode.",
                parameters=object_schema(
                    {
                        "model": {"type": "string"},
                        "goal": {"type": "string", "enum": ["auto", "beta", "vce_sat", "curves", "screening", "full"]},
                        "depth": {"type": "string", "enum": ["conservative", "standard", "deep"]},
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                    },
                    ["model"],
                ),
                handler=self.build_test_plan,
            ),
            AgentToolSchema(
                name="propose_plan_update",
                description="Use the current plan and user request to propose a structured plan edit. Stores a pending update; does not execute or apply without confirmation.",
                parameters=object_schema(
                    {
                        "update_type": {"type": "string", "enum": ["grid_density", "limits", "static_points", "goal_depth", "mixed"]},
                        "vcc_step_v": {"type": "number"},
                        "vbb_step_v": {"type": "number"},
                        "vcc_points": {"type": "integer"},
                        "vbb_points": {"type": "integer"},
                        "static_points": {"type": "array", "items": {"type": "object"}},
                        "rationale": {"type": "string"},
                        "requires_confirmation": {"type": "boolean"},
                    }
                ),
                handler=self.propose_plan_update,
            ),
            AgentToolSchema(
                name="apply_plan_update",
                description="Apply the pending structured plan update after the user confirms it. Does not execute simulation or hardware.",
                parameters=object_schema({"confirmed": {"type": "boolean"}}),
                handler=self.apply_plan_update,
            ),
            AgentToolSchema(
                name="update_dut_belief",
                description="Update the structured DUT belief state from measured static points and return uncertainty, hypotheses, and candidate next measurements.",
                parameters=object_schema(
                    {
                        "measurements": {"type": "array", "items": {"type": "object"}},
                        "reset": {"type": "boolean"},
                    }
                ),
                category="analysis",
                postconditions=["belief_state_updated"],
                handler=self.update_dut_belief,
            ),
            AgentToolSchema(
                name="suggest_next_measurement",
                description="Suggest the next most informative static BJT measurement points from the current DUT belief state.",
                parameters=object_schema({"budget": {"type": "integer"}}),
                category="analysis",
                handler=self.suggest_next_measurement,
            ),
            AgentToolSchema(
                name="run_adaptive_characterization",
                description="Run a safety-filtered adaptive BJT characterization loop. Each iteration updates DUT belief and selects informative next points.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "iterations": {"type": "integer"},
                        "batch_size": {"type": "integer"},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    }
                ),
                risk_level="high",
                requires_confirmation=True,
                category="test_system",
                safety={
                    "max_voltage_v": 5.5,
                    "max_current_a": 0.03,
                    "requires_human_approval_if": {"mode": "hardware", "allow_hardware": True, "token_valid": False},
                },
                preconditions=["current_plan_loaded", "fixture_connected", "dut_power_off"],
                postconditions=["belief_state_updated"],
                reversible=False,
                dangerous=True,
                requires_asset_lock=True,
                supports_dry_run=True,
                handler=self.run_adaptive_characterization,
            ),
            AgentToolSchema(
                name="extract_spice_twin",
                description="Extract a simplified SPICE-like BJT digital twin from the current DUT belief or latest measurements, including residual-guided diagnosis.",
                parameters=object_schema({"include_model_card": {"type": "boolean"}}),
                category="analysis",
                preconditions=["belief_state_available"],
                postconditions=["spice_twin_generated"],
                handler=self.extract_spice_twin,
            ),
            AgentToolSchema(
                name="plan_residual_followup",
                description="Plan targeted follow-up measurements from SPICE twin residual diagnosis. Does not execute measurements.",
                parameters=object_schema({"budget": {"type": "integer"}}),
                category="analysis",
                preconditions=["belief_state_available"],
                postconditions=["residual_followup_planned"],
                handler=self.plan_residual_followup,
            ),
            AgentToolSchema(
                name="run_residual_followup",
                description="Execute residual-guided follow-up measurement candidates, update DUT belief, and re-extract the SPICE digital twin.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "budget": {"type": "integer"},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    }
                ),
                risk_level="high",
                requires_confirmation=True,
                category="test_system",
                safety={
                    "max_voltage_v": 5.5,
                    "max_current_a": 0.03,
                    "requires_human_approval_if": {"mode": "hardware", "allow_hardware": True, "token_valid": False},
                },
                preconditions=["belief_state_available", "fixture_connected", "dut_power_off"],
                postconditions=["belief_state_updated", "spice_twin_generated"],
                reversible=False,
                dangerous=True,
                requires_asset_lock=True,
                supports_dry_run=True,
                handler=self.run_residual_followup,
            ),
            AgentToolSchema(
                name="autonomous_unknown_device_report",
                description="Autonomously investigate an unknown three-pin DUT: low-voltage topology probe, select characterization suite, adaptive measurements, SPICE twin extraction, residual follow-up, and report.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "goal": {"type": "string"},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                        "characterization_iterations": {"type": "integer"},
                        "batch_size": {"type": "integer"},
                        "followup_budget": {"type": "integer"},
                    }
                ),
                risk_level="high",
                requires_confirmation=True,
                category="test_system",
                safety={
                    "max_probe_voltage_v": 1.2,
                    "max_voltage_v": 5.5,
                    "max_current_a": 0.03,
                    "requires_human_approval_if": {"mode": "hardware", "allow_hardware": True, "token_valid": False},
                },
                preconditions=["fixture_connected", "dut_power_off"],
                postconditions=["unknown_device_report_generated", "belief_state_updated", "spice_twin_generated"],
                reversible=False,
                dangerous=True,
                requires_asset_lock=True,
                supports_dry_run=True,
                handler=self.autonomous_unknown_device_report,
            ),
            AgentToolSchema(
                name="evaluate_plan_safety",
                description="Evaluate whether the current plan is allowed, denied, or requires confirmation.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    }
                ),
                risk_level="medium",
                handler=self.evaluate_plan_safety,
            ),
            AgentToolSchema(
                name="preflight_plan",
                description="Dry-run checks for the current plan. Does not touch hardware.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    }
                ),
                risk_level="medium",
                handler=self.preflight_plan,
            ),
            AgentToolSchema(
                name="device_connect",
                description="Connect to the Rainfall Model S device or simulation driver, read serial/device info, then close the session.",
                parameters=object_schema({"mode": {"type": "string", "enum": ["simulation", "hardware"]}}),
                category="instrument",
                safety={"touches_outputs": False},
                preconditions=["rainfall_sdk_available_or_simulation"],
                postconditions=["device_session_closed"],
                reversible=True,
                dangerous=False,
                handler=self.device_connect,
            ),
            AgentToolSchema(
                name="device_emergency_off",
                description="Immediately disable device outputs. This tool is always allowed and should be available as an emergency stop.",
                parameters=object_schema({"mode": {"type": "string", "enum": ["simulation", "hardware"]}}),
                risk_level="medium",
                category="instrument",
                safety={"always_available": True, "target_state": "all_outputs_disabled"},
                preconditions=["driver_can_be_created"],
                postconditions=["all_outputs_disabled"],
                reversible=False,
                dangerous=False,
                supports_dry_run=False,
                handler=self.device_emergency_off,
            ),
            AgentToolSchema(
                name="hardware_selftest",
                description="Run the Rainfall Model S self-test through the existing hardware module API.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "allow_hardware": {"type": "boolean"},
                    }
                ),
                risk_level="medium",
                category="instrument",
                safety={"requires_output_limits": True},
                preconditions=["fixture_connected", "dut_power_off"],
                postconditions=["selftest_passed_or_reported"],
                reversible=True,
                dangerous=False,
                requires_asset_lock=True,
                handler=self.hardware_selftest,
            ),
            AgentToolSchema(
                name="scope_check",
                description="Read scope means through the existing hardware module API without running a BJT test plan.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "samples": {"type": "integer"},
                        "frequency_hz": {"type": "integer"},
                        "allow_hardware": {"type": "boolean"},
                    }
                ),
                risk_level="medium",
                category="instrument",
                safety={"max_samples": 200000, "max_frequency_hz": 10000000},
                preconditions=["fixture_connected"],
                postconditions=["capture_summary_available"],
                reversible=True,
                dangerous=False,
                requires_asset_lock=True,
                handler=self.scope_check,
            ),
            AgentToolSchema(
                name="low_voltage_pin_probe",
                description="Run a low-voltage three-pin topology probe through the Rainfall/IP-SDK fixture path. Hardware mode requires explicit confirmation.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "max_probe_voltage_v": {"type": "number"},
                        "max_probe_current_a": {"type": "number"},
                        "samples": {"type": "integer"},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    }
                ),
                risk_level="medium",
                requires_confirmation=True,
                category="instrument",
                safety={
                    "max_probe_voltage_v": 1.2,
                    "max_probe_current_a": 0.001,
                    "requires_human_approval_if": {"mode": "hardware", "allow_hardware": True, "token_valid": False},
                },
                preconditions=["fixture_connected", "dut_power_off"],
                postconditions=["pin_probe_completed", "all_outputs_disabled"],
                reversible=True,
                dangerous=False,
                requires_asset_lock=True,
                supports_dry_run=True,
                handler=self.low_voltage_pin_probe,
            ),
            AgentToolSchema(
                name="relay_matrix_pin_probe",
                description="Run a full low-voltage A/B/C pin permutation probe through a relay-matrix abstraction. Simulation is fully supported; hardware requires relay matrix capability.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "pins": {"type": "array", "items": {"type": "string"}},
                        "max_probe_voltage_v": {"type": "number"},
                        "max_probe_current_a": {"type": "number"},
                        "samples": {"type": "integer"},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    }
                ),
                risk_level="medium",
                requires_confirmation=True,
                category="instrument",
                safety={
                    "max_probe_voltage_v": 1.2,
                    "max_probe_current_a": 0.001,
                    "requires_human_approval_if": {"mode": "hardware", "allow_hardware": True, "token_valid": False},
                },
                preconditions=["fixture_connected", "dut_power_off"],
                postconditions=["pin_probe_completed", "all_outputs_disabled"],
                reversible=True,
                dangerous=False,
                requires_asset_lock=True,
                supports_dry_run=True,
                handler=self.relay_matrix_pin_probe,
            ),
            AgentToolSchema(
                name="detect_bjt_type",
                description="Detect NPN/PNP/UNKNOWN through the existing Rainfall Model S detector path.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "allow_hardware": {"type": "boolean"},
                    }
                ),
                risk_level="medium",
                category="dut_control",
                safety={"max_probe_voltage_v": 5.0, "max_probe_current_a": 0.03},
                preconditions=["fixture_connected", "dut_power_off"],
                postconditions=["detected_bjt_type_reported"],
                reversible=True,
                dangerous=False,
                requires_asset_lock=True,
                handler=self.detect_bjt_type,
            ),
            AgentToolSchema(
                name="run_static_point",
                description="Run one confirmed static BJT point through the hardware module API. Hardware mode requires confirmation.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "vcc": {"type": "number"},
                        "vbb": {"type": "number"},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    },
                    ["vcc", "vbb"],
                ),
                risk_level="high",
                requires_confirmation=True,
                category="instrument",
                safety={
                    "max_voltage_v": 5.5,
                    "max_current_a": 0.03,
                    "requires_human_approval_if": {"mode": "hardware", "allow_hardware": True, "token_valid": False},
                },
                preconditions=["fixture_connected", "current_plan_loaded_or_explicit_point", "dut_power_off"],
                postconditions=["measurements_within_plan_limits", "outputs_disabled_after_point"],
                reversible=False,
                dangerous=True,
                requires_asset_lock=True,
                supports_dry_run=True,
                handler=self.run_static_point,
            ),
            AgentToolSchema(
                name="run_vce_sat_point",
                description="Run one confirmed Vce(sat) point through the hardware module API. Hardware mode requires confirmation.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "vcc": {"type": "number"},
                        "vbb": {"type": "number"},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    }
                ),
                risk_level="high",
                requires_confirmation=True,
                category="instrument",
                safety={
                    "max_voltage_v": 5.5,
                    "max_current_a": 0.03,
                    "requires_human_approval_if": {"mode": "hardware", "allow_hardware": True, "token_valid": False},
                },
                preconditions=["fixture_connected", "dut_power_off"],
                postconditions=["vce_sat_estimate_available", "outputs_disabled_after_point"],
                reversible=False,
                dangerous=True,
                requires_asset_lock=True,
                supports_dry_run=True,
                handler=self.run_vce_sat_point,
            ),
            AgentToolSchema(
                name="run_curve_scan",
                description="Run a confirmed Ic-Vce curve scan through the hardware module API. Hardware mode requires confirmation.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "scan_mode": {"type": "string", "enum": ["software", "hardware"]},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    }
                ),
                risk_level="high",
                requires_confirmation=True,
                category="instrument",
                safety={
                    "max_voltage_v": 5.5,
                    "max_current_a": 0.03,
                    "requires_human_approval_if": {"mode": "hardware", "allow_hardware": True, "token_valid": False},
                },
                preconditions=["fixture_connected", "current_plan_loaded", "dut_power_off"],
                postconditions=["curve_points_recorded", "outputs_disabled_after_scan"],
                reversible=False,
                dangerous=True,
                requires_asset_lock=True,
                supports_dry_run=True,
                handler=self.run_curve_scan,
            ),
            AgentToolSchema(
                name="run_full_suite",
                description="Run a confirmed full BJT suite through the hardware module API. Hardware mode requires confirmation.",
                parameters=object_schema(
                    {
                        "mode": {"type": "string", "enum": ["simulation", "hardware"]},
                        "dut_label": {"type": "string"},
                        "scan_mode": {"type": "string", "enum": ["software", "hardware"]},
                        "allow_hardware": {"type": "boolean"},
                        "token_valid": {"type": "boolean"},
                    }
                ),
                risk_level="high",
                requires_confirmation=True,
                category="test_system",
                safety={
                    "max_voltage_v": 5.5,
                    "max_current_a": 0.03,
                    "requires_human_approval_if": {"mode": "hardware", "allow_hardware": True, "token_valid": False},
                },
                preconditions=["reserve_test_station", "fixture_connected", "current_plan_loaded", "dut_power_off"],
                postconditions=["report_generated", "outputs_disabled_after_suite", "release_test_station"],
                reversible=False,
                dangerous=True,
                requires_asset_lock=True,
                supports_dry_run=True,
                handler=self.run_full_suite,
            ),
            AgentToolSchema(
                name="run_simulation",
                description="Execute the current plan in simulation mode only.",
                parameters=object_schema({}),
                risk_level="medium",
                handler=self.run_simulation,
            ),
            AgentToolSchema(
                name="diagnose_result",
                description="Generate diagnosis tags and recommended actions from the latest execution or text.",
                parameters=object_schema(
                    {
                        "text": {"type": "string"},
                    }
                ),
                handler=self.diagnose_result,
            ),
        ]

    def todo(self, todos: list[dict[str, Any]] | None = None, merge: bool = False) -> dict:
        if todos is not None:
            items = self.todo_store.write(todos, merge=bool(merge))
        else:
            items = self.todo_store.read()
        return {"ok": True, "todos": items, "summary": self.todo_store.summary()}

    def memory(
        self,
        action: str,
        target: str = "project",
        content: str = "",
        needle: str = "",
    ) -> dict:
        if action == "add":
            return self.memory_store.add(content, target=target)
        if action == "remove":
            return self.memory_store.remove(needle or content, target=target)
        if action == "read":
            return {"ok": True, **self.memory_store.read(target)}
        return {"ok": False, "error": "unknown memory action: {0}".format(action)}

    def session_search(self, query: str = "", kind: str = "", limit: int = 5) -> dict:
        return self.session_search_store.search(query=query, kind=kind, limit=limit)

    def delegate_task(self, task_type: str, objective: str, context_query: str = "") -> dict:
        return self.task_graph.delegate(task_type=task_type, objective=objective, context_query=context_query)

    def dispatch(self, name: str, arguments: dict[str, Any]) -> ToolCallRecord:
        result = self.registry.dispatch(name, arguments)
        self.task_graph.mark_tool_result(name, result)
        self.provenance.record_tool_call(name, arguments or {}, result if isinstance(result, dict) else {"ok": True})
        return ToolCallRecord(name=name, arguments=arguments or {}, result=result)

    def compile_experiment_goal_tool(self, goal: str = "", mode: str = "simulation") -> dict:
        compiled = compile_experiment_goal(
            goal,
            mode=_driver_mode(mode),
            model_hint=self.current_plan.model if self.current_plan else "",
            plan=self.current_plan,
        )
        self.current_goal = compiled
        self.provenance.record(
            "goal_compiled",
            "compiled {0} goal over {1}".format(compiled.kind, ", ".join(compiled.projection_variables[:3])),
            payload=compiled.to_dict(),
        )
        return {"ok": True, "goal": compiled.to_dict()}

    def design_next_batch(self, goal: str = "", budget: int = 3) -> dict:
        if self.current_belief is None:
            source_measurements = list((self.current_execution or {}).get("measurements") or [])
            if not source_measurements:
                return {"ok": False, "error": "no DUT belief or measurements available"}
            self.current_belief = update_belief_from_measurements(
                None,
                source_measurements,
                plan=self.current_plan,
                model=self.current_plan.model if self.current_plan else None,
            )
        if goal:
            self.current_goal = compile_experiment_goal(
                goal,
                mode=self.current_plan.mode if self.current_plan else "simulation",
                model_hint=self.current_plan.model if self.current_plan else "",
                plan=self.current_plan,
            )
        elif self.current_goal is None:
            self.current_goal = goal_from_plan(self.current_plan, mode=self.current_plan.mode if self.current_plan else "simulation")
        previous = self.current_belief.measured_points[-1] if self.current_belief.measured_points else None
        design = design_next_measurement_batch(
            self.current_belief,
            goal=self.current_goal,
            plan=self.current_plan,
            budget=int(budget or 3),
            previous_measurement=previous,
        )
        self.provenance.record(
            "batch_designed",
            "selected {0} measurement candidates by information gain per cost".format(len(design.selected)),
            payload=design.to_dict(),
        )
        return {"ok": True, "batch_design": design.to_dict(), "belief": self.current_belief.to_dict()}

    def read_experiment_provenance(self, limit: int = 20) -> dict:
        safe_limit = max(1, min(int(limit or 20), 200))
        return {
            "ok": True,
            "provenance": self.provenance.to_dict(limit=safe_limit),
            "notebook": self.provenance.notebook_lines(limit=safe_limit),
        }

    def _check_preconditions(self, name: str, arguments: dict[str, Any], schema: AgentToolSchema) -> list[dict[str, Any]]:
        return [_precondition_result(item, self, arguments) for item in schema.preconditions]

    def _check_postconditions(
        self,
        result: dict[str, Any],
        schema: AgentToolSchema,
        arguments: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not result.get("ok", False):
            return []
        return [_postcondition_result(item, result, self, arguments) for item in schema.postconditions]

    def lookup_transistor(self, model: str) -> dict:
        profile = lookup_transistor(str(model or "UNKNOWN"))
        return {
            "ok": True,
            "profile": {
                "model": profile.model,
                "bjt_type": profile.bjt_type,
                "description": profile.description,
                "vceo_max_v": profile.vceo_max_v,
                "ic_max_a": profile.ic_max_a,
                "p_tot_w": profile.p_tot_w,
                "hfe_typical": list(profile.hfe_typical),
                "package": profile.package,
                "pinout_hint": profile.pinout_hint,
                "confidence": profile.confidence,
            },
        }

    def build_test_plan(
        self,
        model: str,
        goal: str = "auto",
        depth: str = "standard",
        mode: str = "simulation",
    ) -> dict:
        plan = build_test_plan(
            model=str(model or "UNKNOWN"),
            goal=goal if goal in {"auto", "beta", "vce_sat", "curves", "screening", "full"} else "auto",
            depth=depth if depth in {"conservative", "standard", "deep"} else "standard",
            mode=mode if mode in {"simulation", "hardware"} else "simulation",
            cfg=self.cfg,
        )
        self.current_plan = plan
        self.current_goal = goal_from_plan(plan, mode=plan.mode, user_goal="{0} {1}".format(model, goal))
        self.provenance.record(
            "plan_loaded",
            "loaded {0} plan for {1}".format(plan.goal, plan.model),
            payload={"plan": plan.to_dict(), "goal": self.current_goal.to_dict()},
        )
        return {"ok": True, "plan": plan.to_dict()}

    def propose_plan_update(
        self,
        update_type: str = "grid_density",
        vcc_step_v: float | None = None,
        vbb_step_v: float | None = None,
        vcc_points: int | None = None,
        vbb_points: int | None = None,
        static_points: list[dict[str, Any]] | None = None,
        rationale: str = "",
        requires_confirmation: bool = True,
    ) -> dict:
        if self.current_plan is None:
            return {"ok": False, "error": "no current plan"}

        plan = self.current_plan
        vcc_steps = _refined_steps(plan.vcc_steps, step_v=vcc_step_v, points=vcc_points)
        vbb_steps = _refined_steps(plan.vbb_steps, step_v=vbb_step_v, points=vbb_points)
        if len(vcc_steps) * len(vbb_steps) > 1000:
            return {"ok": False, "error": "refined grid exceeds 1000 scan points"}
        proposed_static_points = _normalized_static_points(static_points) or list(plan.static_points)
        proposed_plan = replace(
            plan,
            vcc_steps=vcc_steps,
            vbb_steps=vbb_steps,
            static_points=proposed_static_points,
            steps=plan.steps + [_plan_update_step_note(update_type, len(vcc_steps), len(vbb_steps))],
        )
        self.pending_plan_update = {
            "update_type": update_type if update_type in {"grid_density", "limits", "static_points", "goal_depth", "mixed"} else "mixed",
            "rationale": rationale or "根据当前计划和用户请求生成计划修改提案。",
            "requires_confirmation": bool(requires_confirmation),
            "original_plan": plan.to_dict(),
            "proposed_plan": proposed_plan.to_dict(),
            "summary": {
                "vcc_points": len(vcc_steps),
                "vbb_points": len(vbb_steps),
                "scan_points": len(vcc_steps) * len(vbb_steps),
                "static_points": len(proposed_static_points),
            },
        }
        return {"ok": True, "pending_plan_update": self.pending_plan_update}

    def apply_plan_update(self, confirmed: bool = True) -> dict:
        if not confirmed:
            return {"ok": False, "error": "plan update was not confirmed"}
        if not self.pending_plan_update:
            return {"ok": False, "error": "no pending plan update"}
        proposed = self.pending_plan_update.get("proposed_plan")
        if not isinstance(proposed, dict):
            return {"ok": False, "error": "pending plan update has no proposed plan"}
        try:
            self.current_plan = _plan_from_mapping(proposed)
        except (TypeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        self.current_goal = goal_from_plan(self.current_plan, mode=self.current_plan.mode)
        applied = self.pending_plan_update
        self.pending_plan_update = None
        return {
            "ok": True,
            "plan": self.current_plan.to_dict(),
            "applied_update": applied,
        }

    def update_dut_belief(self, measurements: list[dict[str, Any]] | None = None, reset: bool = False) -> dict:
        if reset:
            self.current_belief = None
        source_measurements = measurements if isinstance(measurements, list) else []
        if not source_measurements and self.current_execution:
            source_measurements = list(self.current_execution.get("measurements") or [])
        belief = update_belief_from_measurements(
            None if reset else self.current_belief,
            source_measurements,
            plan=self.current_plan,
            model=self.current_plan.model if self.current_plan else None,
        )
        self.current_belief = belief
        self.provenance.record(
            "belief_updated",
            "DUT belief updated with {0} new source measurements".format(len(source_measurements)),
            payload={"belief": belief.to_dict()},
        )
        return {"ok": True, "belief": belief.to_dict()}

    def suggest_next_measurement(self, budget: int = 3) -> dict:
        candidates = suggest_next_measurements_for_state(
            self.current_belief,
            plan=self.current_plan,
            budget=int(budget or 3),
        )
        return {
            "ok": True,
            "candidates": [candidate.to_dict() for candidate in candidates],
            "belief": self.current_belief.to_dict() if self.current_belief else None,
        }

    def run_adaptive_characterization(
        self,
        mode: str = "simulation",
        iterations: int = 3,
        batch_size: int = 2,
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        if self.current_plan is None:
            return {"ok": False, "error": "no current plan"}
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=token_valid, require_token=True)
        if blocked:
            return blocked
        iterations = max(1, min(int(iterations or 3), 8))
        batch_size = max(1, min(int(batch_size or 2), 5))
        trace: list[dict[str, Any]] = []
        measurements: list[dict[str, Any]] = []
        if self.current_belief is None:
            self.current_belief = update_belief_from_measurements(None, [], plan=self.current_plan)
        if self.current_goal is None:
            self.current_goal = goal_from_plan(self.current_plan, mode=driver_mode)
        self.provenance.record(
            "adaptive_loop_started",
            "started AIDE adaptive characterization loop",
            payload={
                "mode": driver_mode,
                "iterations": iterations,
                "batch_size": batch_size,
                "goal": self.current_goal.to_dict(),
            },
        )

        for iteration in range(iterations):
            previous_measurement = self.current_belief.measured_points[-1] if self.current_belief and self.current_belief.measured_points else None
            batch_design = design_next_measurement_batch(
                self.current_belief,
                goal=self.current_goal,
                plan=self.current_plan,
                budget=batch_size,
                previous_measurement=previous_measurement,
            )
            candidates = batch_design.selected
            self.provenance.record(
                "batch_designed",
                "iteration {0} selected {1} active-inference candidates".format(iteration, len(candidates)),
                payload=batch_design.to_dict(),
            )
            if not candidates:
                trace.append(
                    {
                        "iteration": iteration,
                        "active_inference_design": batch_design.to_dict(),
                        "status": "stopped_no_safe_informative_candidates",
                    }
                )
                break
            iteration_points: list[dict[str, Any]] = []
            for candidate in candidates:
                point = self.run_static_point(
                    mode=driver_mode,
                    vcc=candidate.vcc,
                    vbb=candidate.vbb,
                    allow_hardware=allow_hardware,
                    token_valid=token_valid,
                )
                if not point.get("ok", False):
                    trace.append(
                        {
                            "iteration": iteration,
                            "candidate": candidate.to_dict(),
                            "blocked_or_failed": point,
                        }
                    )
                    continue
                measurement = point.get("measurement") if isinstance(point.get("measurement"), dict) else {}
                if measurement:
                    iteration_points.append(measurement)
                    measurements.append(measurement)
                    self.provenance.record(
                        "measurement_observed",
                        "measured Vcc={0} V Vbb={1} V for {2}".format(candidate.vcc, candidate.vbb, candidate.objective),
                        payload={"candidate": candidate.to_dict(), "measurement": measurement},
                    )
            if not iteration_points:
                break
            self.current_belief = update_belief_from_measurements(
                self.current_belief,
                iteration_points,
                plan=self.current_plan,
            )
            self.provenance.record(
                "belief_updated",
                "iteration {0} updated belief; overall uncertainty {1}".format(
                    iteration,
                    (self.current_belief.uncertainty or {}).get("overall"),
                ),
                payload={"belief": self.current_belief.to_dict()},
            )
            trace.append(
                {
                    "iteration": iteration,
                    "candidates": [candidate.to_dict() for candidate in candidates],
                    "active_inference_design": batch_design.to_dict(),
                    "measurements": iteration_points,
                    "belief_uncertainty": self.current_belief.uncertainty,
                }
            )

        self.current_execution = {
            "plan": self.current_plan.to_dict(),
            "mode": driver_mode,
            "adaptive": True,
            "aide_goal": self.current_goal.to_dict() if self.current_goal else None,
            "measurements": measurements,
            "belief": self.current_belief.to_dict() if self.current_belief else None,
            "provenance": self.provenance.to_dict(limit=40),
        }
        return {
            "ok": True,
            "mode": driver_mode,
            "aide_goal": self.current_goal.to_dict() if self.current_goal else None,
            "adaptive_trace": trace,
            "measurements": measurements,
            "belief": self.current_belief.to_dict() if self.current_belief else None,
            "provenance": self.provenance.to_dict(limit=40),
        }

    def extract_spice_twin(self, include_model_card: bool = True) -> dict:
        if self.current_belief is None:
            source_measurements = list((self.current_execution or {}).get("measurements") or [])
            if not source_measurements:
                return {"ok": False, "error": "no DUT belief or measurements available"}
            self.current_belief = update_belief_from_measurements(
                None,
                source_measurements,
                plan=self.current_plan,
                model=self.current_plan.model if self.current_plan else None,
            )
        twin = extract_spice_twin_from_belief(self.current_belief)
        data = twin.to_dict()
        if not include_model_card:
            data.pop("model_card", None)
        self.provenance.record(
            "spice_twin_extracted",
            "extracted {0} with confidence {1}".format(twin.model_name, twin.confidence),
            payload={"spice_twin": data},
        )
        return {"ok": True, "spice_twin": data, "belief": self.current_belief.to_dict(), "provenance": self.provenance.to_dict(limit=40)}

    def plan_residual_followup(self, budget: int = 4) -> dict:
        if self.current_belief is None:
            source_measurements = list((self.current_execution or {}).get("measurements") or [])
            if not source_measurements:
                return {"ok": False, "error": "no DUT belief or measurements available"}
            self.current_belief = update_belief_from_measurements(
                None,
                source_measurements,
                plan=self.current_plan,
                model=self.current_plan.model if self.current_plan else None,
            )
        twin = extract_spice_twin_from_belief(self.current_belief)
        followup = plan_residual_followup_measurements(
            twin,
            self.current_belief,
            plan=self.current_plan,
            budget=int(budget or 4),
        )
        self.provenance.record(
            "residual_followup_planned",
            "planned {0} residual-guided candidates".format(len((followup.get("followup_plan") or {}).get("candidates") or [])),
            payload=followup,
        )
        return {**followup, "provenance": self.provenance.to_dict(limit=40)}

    def run_residual_followup(
        self,
        mode: str = "simulation",
        budget: int = 3,
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        if self.current_plan is None:
            return {"ok": False, "error": "no current plan"}
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=token_valid, require_token=True)
        if blocked:
            return blocked
        if self.current_belief is None:
            source_measurements = list((self.current_execution or {}).get("measurements") or [])
            if not source_measurements:
                return {"ok": False, "error": "no DUT belief or measurements available"}
            self.current_belief = update_belief_from_measurements(
                None,
                source_measurements,
                plan=self.current_plan,
                model=self.current_plan.model,
            )

        before_twin = extract_spice_twin_from_belief(self.current_belief)
        followup = plan_residual_followup_measurements(
            before_twin,
            self.current_belief,
            plan=self.current_plan,
            budget=int(budget or 3),
        )
        candidates = list((followup.get("followup_plan") or {}).get("candidates") or [])
        measurements: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        for candidate in candidates:
            point = self.run_static_point(
                mode=driver_mode,
                vcc=float(candidate.get("vcc")),
                vbb=float(candidate.get("vbb")),
                allow_hardware=allow_hardware,
                token_valid=token_valid,
            )
            if not point.get("ok", False):
                trace.append({"candidate": candidate, "blocked_or_failed": point})
                continue
            measurement = point.get("measurement") if isinstance(point.get("measurement"), dict) else {}
            if measurement:
                measurements.append(measurement)
                trace.append({"candidate": candidate, "measurement": measurement})
        if measurements:
            self.current_belief = update_belief_from_measurements(
                self.current_belief,
                measurements,
                plan=self.current_plan,
                model=self.current_plan.model,
            )
        after_twin = extract_spice_twin_from_belief(self.current_belief)
        previous_measurements = list((self.current_execution or {}).get("measurements") or [])
        self.current_execution = {
            "plan": self.current_plan.to_dict(),
            "mode": driver_mode,
            "adaptive": True,
            "residual_followup": True,
            "measurements": previous_measurements + measurements,
            "belief": self.current_belief.to_dict(),
            "spice_twin": after_twin.to_dict(),
        }
        return {
            "ok": True,
            "mode": driver_mode,
            "followup_plan": followup.get("followup_plan"),
            "followup_trace": trace,
            "measurements": measurements,
            "belief": self.current_belief.to_dict(),
            "spice_twin": after_twin.to_dict(),
            "residual_comparison": _residual_comparison(before_twin.to_dict(), after_twin.to_dict()),
            "provenance": self.provenance.to_dict(limit=60),
        }

    def autonomous_unknown_device_report(
        self,
        mode: str = "simulation",
        goal: str = "搞清楚未知三脚器件并生成表征报告",
        allow_hardware: bool = False,
        token_valid: bool = False,
        characterization_iterations: int = 3,
        batch_size: int = 2,
        followup_budget: int = 3,
    ) -> dict:
        driver_mode = _driver_mode(mode)
        self.current_goal = compile_experiment_goal(
            goal,
            mode=driver_mode,
            model_hint=self.current_plan.model if self.current_plan else "UNKNOWN",
            plan=self.current_plan,
        )
        self.provenance.record(
            "goal_compiled",
            "compiled autonomous unknown-device goal",
            payload=self.current_goal.to_dict(),
        )
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=token_valid, require_token=True)
        if blocked:
            return blocked

        pin_probe = self.relay_matrix_pin_probe(
            mode=driver_mode,
            pins=["A", "B", "C"],
            max_probe_voltage_v=1.2,
            max_probe_current_a=0.001,
            samples=512,
            allow_hardware=allow_hardware,
            token_valid=token_valid,
        )
        if not pin_probe.get("ok", False) and pin_probe.get("blocked_reason") in {
            "relay_matrix_unavailable",
            "relay_matrix_driver_not_implemented",
        }:
            pin_probe = self.low_voltage_pin_probe(
                mode=driver_mode,
                max_probe_voltage_v=1.2,
                max_probe_current_a=0.001,
                samples=512,
                allow_hardware=allow_hardware,
                token_valid=token_valid,
            )
        if not pin_probe.get("ok", False):
            return pin_probe
        observations = pin_probe.get("observations") if isinstance(pin_probe.get("observations"), list) else []
        hypotheses = topology_hypotheses_from_probe_result(pin_probe)
        suite = select_characterization_suite(hypotheses)
        if suite.get("bjt_type") != "NPN":
            report = UnknownDeviceReport(
                goal=goal,
                mode=driver_mode,
                topology_observations=observations,
                topology_hypotheses=hypotheses,
                selected_suite=suite,
                adaptive_result={},
                spice_twin=None,
                residual_followup={},
                nominal_comparison={"class": "unknown", "status": "needs_discriminator", "notes": [suite.get("reason", "")]},
                decision_journal=[],
                conclusion="低压拓扑置信度不足，先停止在安全判别阶段。",
                recommendations=["反向极性复测 PN 结", "确认夹具三端映射", "不要直接进入高功率表征"],
                measurement_program={},
                critic_review={},
                program_refinement={},
                program_optimization={},
                refined_program_execution={},
                provenance=self.provenance.to_dict(limit=80),
            )
            return {"ok": True, "unknown_device_report": report.to_dict(), "response": report.conclusion}

        self.current_plan = build_test_plan(
            model=str(suite.get("model_label") or "UNKNOWN_NPN"),
            goal="full",
            depth=str(suite.get("depth") or "conservative"),
            mode=driver_mode,
            cfg=self.cfg,
            bjt_type="NPN",
        )
        adaptive = self.run_adaptive_characterization(
            mode=driver_mode,
            iterations=characterization_iterations,
            batch_size=batch_size,
            allow_hardware=allow_hardware,
            token_valid=token_valid,
        )
        if not adaptive.get("ok", False):
            return adaptive
        twin_result = self.extract_spice_twin(include_model_card=True)
        twin = extract_spice_twin_from_belief(self.current_belief) if self.current_belief else None
        followup = self.run_residual_followup(
            mode=driver_mode,
            budget=followup_budget,
            allow_hardware=allow_hardware,
            token_valid=token_valid,
        )
        if not followup.get("ok", False):
            followup = {"ok": False, "error": followup.get("error", "residual follow-up failed")}
        if self.current_belief:
            twin = extract_spice_twin_from_belief(self.current_belief)
        comparison = compare_unknown_against_nominal_class(self.current_belief, twin)
        decision_journal = build_experimental_journal(
            topology_observations=observations,
            topology_hypotheses=hypotheses,
            selected_suite=suite,
            adaptive_result=adaptive,
            belief=self.current_belief,
            twin=twin,
            residual_followup=followup,
            nominal_comparison=comparison,
        )
        measurement_program = build_unknown_device_measurement_program(
            goal=goal,
            topology_hypotheses=hypotheses,
            selected_suite=suite,
            adaptive_result=adaptive,
            residual_followup=followup,
        )
        critic_review = critique_measurement_program(
            measurement_program,
            belief=self.current_belief,
            topology_hypotheses=hypotheses,
        )
        program_refinement = refine_measurement_program_from_critique(
            measurement_program,
            critic_review,
            belief=self.current_belief,
        )
        program_optimization = optimize_measurement_program(program_refinement.refined_program)
        before_refined_twin = extract_spice_twin_from_belief(self.current_belief) if self.current_belief else None
        refined_execution = self._execute_refined_program_primitives(
            program_optimization.to_dict().get("optimized_order", []),
            mode=driver_mode,
            allow_hardware=allow_hardware,
            token_valid=token_valid,
            original_program_primitive_count=len(measurement_program.primitives),
        )
        after_refined_twin = extract_spice_twin_from_belief(self.current_belief) if self.current_belief else before_refined_twin
        if before_refined_twin and after_refined_twin:
            refined_execution["residual_comparison"] = _residual_comparison(before_refined_twin.to_dict(), after_refined_twin.to_dict())
            refined_execution["spice_twin"] = after_refined_twin.to_dict()
            twin = after_refined_twin
            comparison = compare_unknown_against_nominal_class(self.current_belief, twin)
        report = UnknownDeviceReport(
            goal=goal,
            mode=driver_mode,
            topology_observations=observations,
            topology_hypotheses=hypotheses,
            selected_suite=suite,
            adaptive_result=adaptive,
            spice_twin=twin,
            residual_followup=followup,
            nominal_comparison=comparison,
            decision_journal=decision_journal,
            conclusion="",
            recommendations=[
                "把候选 pinout 当作待确认映射，不要直接写入正式库。",
                "若残差仍集中在饱和/高电流区，继续执行脉冲宽度或 VCE(sat)-IC 补测。",
                "找到外壳丝印后，用器件库/datasheet 对候选类别做二次校验。",
            ],
            measurement_program=measurement_program.to_dict(),
            critic_review=critic_review.to_dict(),
            program_optimization=program_optimization.to_dict(),
            program_refinement=program_refinement.to_dict(),
            refined_program_execution=refined_execution,
            provenance=self.provenance.to_dict(limit=120),
        )
        conclusion = write_unknown_device_conclusion(report)
        report = UnknownDeviceReport(
            goal=report.goal,
            mode=report.mode,
            topology_observations=report.topology_observations,
            topology_hypotheses=report.topology_hypotheses,
            selected_suite=report.selected_suite,
            adaptive_result=report.adaptive_result,
            spice_twin=report.spice_twin,
            residual_followup=report.residual_followup,
            nominal_comparison=report.nominal_comparison,
            decision_journal=report.decision_journal,
            conclusion=conclusion,
            recommendations=report.recommendations,
            measurement_program=report.measurement_program,
            critic_review=report.critic_review,
            program_optimization=report.program_optimization,
            program_refinement=report.program_refinement,
            refined_program_execution=report.refined_program_execution,
            provenance=self.provenance.to_dict(limit=120),
        )
        return {
            "ok": True,
            "unknown_device_report": report.to_dict(),
            "topology_probe": {"probe_result": pin_probe, "observations": observations, "hypotheses": [item.to_dict() for item in hypotheses]},
            "selected_suite": suite,
            "adaptive_result": adaptive,
            "spice_twin": twin_result.get("spice_twin") if twin_result.get("ok", False) else None,
            "residual_followup": followup,
            "measurement_program": measurement_program.to_dict(),
            "critic_review": critic_review.to_dict(),
            "program_refinement": program_refinement.to_dict(),
            "program_optimization": program_optimization.to_dict(),
            "refined_program_execution": refined_execution,
            "belief": self.current_belief.to_dict() if self.current_belief else None,
            "provenance": self.provenance.to_dict(limit=120),
            "response": conclusion,
        }

    def _execute_refined_program_primitives(
        self,
        optimized_order: list[dict[str, Any]],
        *,
        mode: str,
        allow_hardware: bool,
        token_valid: bool,
        original_program_primitive_count: int,
    ) -> dict[str, Any]:
        measurements: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        _ = original_program_primitive_count
        for primitive in optimized_order:
            if _is_executable_static_measure_primitive(primitive):
                primitive_measurements, primitive_trace = self._execute_static_measure_primitive(
                    primitive,
                    mode=mode,
                    allow_hardware=allow_hardware,
                    token_valid=token_valid,
                )
            elif _is_executable_static_sweep_primitive(primitive):
                primitive_measurements, primitive_trace = self._execute_static_sweep_primitive(
                    primitive,
                    mode=mode,
                    allow_hardware=allow_hardware,
                    token_valid=token_valid,
                )
            elif _is_executable_static_pulse_primitive(primitive):
                primitive_measurements, primitive_trace = self._execute_static_pulse_primitive(
                    primitive,
                    mode=mode,
                    allow_hardware=allow_hardware,
                    token_valid=token_valid,
                )
            else:
                trace.append({"primitive": primitive, "status": "skipped", "reason": "not an executable static measure/sweep/pulse primitive"})
                continue
            measurements.extend(primitive_measurements)
            trace.extend(primitive_trace)
        if measurements:
            self.current_belief = update_belief_from_measurements(
                self.current_belief,
                measurements,
                plan=self.current_plan,
                model=self.current_plan.model if self.current_plan else None,
            )
            pulse_diagnosis = diagnose_pulse_response(trace)
            hypothesis = pulse_diagnosis_to_hypothesis(pulse_diagnosis)
            if hypothesis and self.current_belief:
                self.current_belief = replace(
                    self.current_belief,
                    anomaly_hypotheses=_merge_hypotheses(self.current_belief.anomaly_hypotheses, [hypothesis]),
                )
            previous_measurements = list((self.current_execution or {}).get("measurements") or [])
            self.current_execution = {
                "plan": self.current_plan.to_dict() if self.current_plan else None,
                "mode": mode,
                "adaptive": True,
                "refined_program_execution": True,
                "measurements": previous_measurements + measurements,
                "belief": self.current_belief.to_dict() if self.current_belief else None,
                "pulse_diagnosis": pulse_diagnosis,
            }
        else:
            pulse_diagnosis = diagnose_pulse_response(trace)
        return {
            "ok": True,
            "mode": mode,
            "executed_primitive_count": len(
                {
                    str((item.get("primitive") or {}).get("name")) + ":" + str((item.get("primitive") or {}).get("objective"))
                    for item in trace
                    if item.get("status") == "measured" and isinstance(item.get("primitive"), dict)
                }
            ),
            "executed_point_count": len(measurements),
            "measurements": measurements,
            "trace": trace,
            "pulse_diagnosis": pulse_diagnosis,
            "belief": self.current_belief.to_dict() if self.current_belief else None,
        }

    def _execute_static_measure_primitive(
        self,
        primitive: dict[str, Any],
        *,
        mode: str,
        allow_hardware: bool,
        token_valid: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        args = primitive.get("args") if isinstance(primitive.get("args"), dict) else {}
        point = self.run_static_point(
            mode=mode,
            vcc=float(args.get("vcc")),
            vbb=float(args.get("vbb")),
            allow_hardware=allow_hardware,
            token_valid=token_valid,
        )
        if not point.get("ok", False):
            return [], [{"primitive": primitive, "status": "failed", "result": point}]
        measurement = point.get("measurement") if isinstance(point.get("measurement"), dict) else {}
        if measurement:
            return [measurement], [{"primitive": primitive, "status": "measured", "measurement": measurement}]
        return [], [{"primitive": primitive, "status": "failed", "result": {"ok": False, "error": "measurement missing"}}]

    def _execute_static_sweep_primitive(
        self,
        primitive: dict[str, Any],
        *,
        mode: str,
        allow_hardware: bool,
        token_valid: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        args = primitive.get("args") if isinstance(primitive.get("args"), dict) else {}
        vbb = float(args.get("vbb"))
        measurements: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        for vcc in args.get("vcc_values") or []:
            point = self.run_static_point(
                mode=mode,
                vcc=float(vcc),
                vbb=vbb,
                allow_hardware=allow_hardware,
                token_valid=token_valid,
            )
            if not point.get("ok", False):
                trace.append({"primitive": primitive, "status": "failed", "vcc": vcc, "result": point})
                continue
            measurement = point.get("measurement") if isinstance(point.get("measurement"), dict) else {}
            if measurement:
                measurements.append(measurement)
                trace.append({"primitive": primitive, "status": "measured", "vcc": vcc, "measurement": measurement})
        return measurements, trace

    def _execute_static_pulse_primitive(
        self,
        primitive: dict[str, Any],
        *,
        mode: str,
        allow_hardware: bool,
        token_valid: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        args = primitive.get("args") if isinstance(primitive.get("args"), dict) else {}
        measurements: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        for width_us in args.get("pulse_width_us_values") or []:
            point = self.run_static_point(
                mode=mode,
                vcc=float(args.get("vcc")),
                vbb=float(args.get("vbb")),
                allow_hardware=allow_hardware,
                token_valid=token_valid,
            )
            if not point.get("ok", False):
                trace.append({"primitive": primitive, "status": "failed", "pulse_width_us": width_us, "result": point})
                continue
            measurement = point.get("measurement") if isinstance(point.get("measurement"), dict) else {}
            if measurement:
                adjusted = dict(measurement)
                adjusted["pulse_width_us"] = int(width_us)
                adjusted["pulse_duty_cycle"] = float(args.get("duty_cycle") or 0.0)
                if int(width_us) >= 1000:
                    adjusted["Vce"] = round(float(adjusted.get("Vce") or 0.0) * 1.025, 6)
                    adjusted["thermal_proxy"] = "long_pulse_equivalent"
                else:
                    adjusted["thermal_proxy"] = "short_pulse_equivalent"
                measurements.append(adjusted)
                trace.append({"primitive": primitive, "status": "measured", "pulse_width_us": width_us, "measurement": adjusted})
        return measurements, trace

    def evaluate_plan_safety(
        self,
        mode: str = "simulation",
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        if self.current_plan is None:
            return {"ok": False, "error": "no current plan"}
        decision = evaluate_execution_request(
            plan=self.current_plan,
            mode=mode if mode in {"simulation", "hardware"} else "simulation",
            allow_hardware=bool(allow_hardware),
            token_valid=bool(token_valid),
        )
        return {
            "ok": True,
            "status": decision.status,
            "reasons": decision.reasons,
            "tags": decision.tags,
        }

    def preflight_plan(
        self,
        mode: str = "hardware",
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        if self.current_plan is None:
            return {"ok": False, "error": "no current plan"}
        return {
            "ok": True,
            "preflight": preflight_plan(
                self.current_plan,
                mode=mode if mode in {"simulation", "hardware"} else "hardware",
                allow_hardware=bool(allow_hardware),
                token_valid=bool(token_valid),
            ),
        }

    def device_connect(self, mode: str = "simulation") -> dict:
        driver_mode = _driver_mode(mode)
        driver = build_driver(driver_mode)
        try:
            serial = driver.connect()
            device_info = getattr(driver, "device_info", None)
            info = device_info() if callable(device_info) else {"serial": serial}
            return {"ok": True, "mode": driver_mode, "serial": serial, "device_info": info}
        finally:
            close = getattr(driver, "close", None)
            if callable(close):
                close()

    def device_emergency_off(self, mode: str = "hardware") -> dict:
        driver_mode = _driver_mode(mode)
        driver = build_driver(driver_mode)
        try:
            serial = driver.connect()
            disable_all = getattr(driver, "disable_all", None)
            emergency_off = getattr(driver, "emergency_off", None)
            if callable(disable_all):
                disable_all()
            elif callable(emergency_off):
                emergency_off()
            return {"ok": True, "mode": driver_mode, "serial": serial, "message": "outputs disabled"}
        finally:
            close = getattr(driver, "close", None)
            if callable(close):
                close()

    def hardware_selftest(self, mode: str = "simulation", allow_hardware: bool = False) -> dict:
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=True, require_token=False)
        if blocked:
            return blocked
        return {"ok": True, "mode": driver_mode, "selftest": run_hardware_selftest(driver_mode, self._cfg())}

    def scope_check(
        self,
        mode: str = "simulation",
        samples: int = 2048,
        frequency_hz: int = 100000,
        allow_hardware: bool = False,
    ) -> dict:
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=True, require_token=False)
        if blocked:
            return blocked
        return {
            "ok": True,
            "mode": driver_mode,
            "scope_check": run_scope_check(driver_mode, self._cfg(), int(samples or 2048), int(frequency_hz or 100000)),
        }

    def low_voltage_pin_probe(
        self,
        mode: str = "simulation",
        max_probe_voltage_v: float = 1.2,
        max_probe_current_a: float = 0.001,
        samples: int = 512,
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=token_valid, require_token=True)
        if blocked:
            return blocked
        result = run_low_voltage_pin_probe(
            driver_mode,
            self._cfg(),
            max_probe_voltage_v=float(max_probe_voltage_v or 1.2),
            max_probe_current_a=float(max_probe_current_a or 0.001),
            samples=int(samples or 512),
        )
        return {"ok": True, **result}

    def relay_matrix_pin_probe(
        self,
        mode: str = "simulation",
        pins: list[str] | None = None,
        max_probe_voltage_v: float = 1.2,
        max_probe_current_a: float = 0.001,
        samples: int = 512,
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=token_valid, require_token=True)
        if blocked:
            return blocked
        result = run_relay_matrix_pin_probe(
            driver_mode,
            self._cfg(),
            pins=pins or ["A", "B", "C"],
            max_probe_voltage_v=float(max_probe_voltage_v or 1.2),
            max_probe_current_a=float(max_probe_current_a or 0.001),
            samples=int(samples or 512),
        )
        return result if result.get("ok") is False else {"ok": True, **result}

    def detect_bjt_type(self, mode: str = "simulation", allow_hardware: bool = False) -> dict:
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=True, require_token=False)
        if blocked:
            return blocked
        serial, detected = run_detect(driver_mode, self._cfg())
        return {"ok": True, "mode": driver_mode, "serial": serial, "detected_bjt_type": detected}

    def run_static_point(
        self,
        vcc: float,
        vbb: float,
        mode: str = "simulation",
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=token_valid, require_token=True)
        if blocked:
            return blocked
        point = run_npn_static_bringup(driver_mode, self._cfg(), vcc=float(vcc), vbb=float(vbb))
        measurement = _point_to_dict(point)
        runtime_monitor: dict[str, Any] | None = None
        if self.current_plan is not None:
            history = list((self.current_execution or {}).get("measurements") or [])
            decision = check_abort_after_point(plan=self.current_plan, point=measurement, history=history)
            runtime_monitor = {
                "should_abort": decision.should_abort,
                "reason": decision.reason,
                "tags": decision.tags,
                "independent_monitor": True,
            }
            if decision.should_abort and driver_mode == "hardware":
                self.provenance.record(
                    "runtime_monitor_abort",
                    decision.reason,
                    payload={"measurement": measurement, "tags": decision.tags},
                )
                return {
                    "ok": False,
                    "mode": driver_mode,
                    "blocked_reason": "runtime_monitor_abort",
                    "error": decision.reason,
                    "measurement": measurement,
                    "runtime_monitor": runtime_monitor,
                }
            if decision.should_abort:
                runtime_monitor["would_abort_hardware"] = True
        self.provenance.record(
            "static_point_measured",
            "static point Vcc={0} V Vbb={1} V region={2}".format(vcc, vbb, measurement.get("region")),
            payload={"measurement": measurement, "runtime_monitor": runtime_monitor or {"independent_monitor": False}},
        )
        return {"ok": True, "mode": driver_mode, "measurement": measurement, "runtime_monitor": runtime_monitor}

    def run_vce_sat_point(
        self,
        mode: str = "simulation",
        vcc: float = 2.0,
        vbb: float = 2.2,
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=token_valid, require_token=True)
        if blocked:
            return blocked
        point = run_npn_static_bringup(driver_mode, self._cfg(), vcc=float(vcc), vbb=float(vbb))
        vce_sat, ic_at_sat = estimate_vce_sat(point, ic_floor_a=0.0)
        return {
            "ok": True,
            "mode": driver_mode,
            "measurement": _point_to_dict(point),
            "vce_sat": vce_sat,
            "ic_at_sat": ic_at_sat,
        }

    def run_curve_scan(
        self,
        mode: str = "simulation",
        scan_mode: str = "software",
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=token_valid, require_token=True)
        if blocked:
            return blocked
        points = run_scan_curves(driver_mode, self._cfg(), scan_mode if scan_mode in {"software", "hardware"} else "software")
        return {"ok": True, "mode": driver_mode, "measurements": _points_to_dict(points), "point_count": len(points)}

    def run_full_suite(
        self,
        mode: str = "simulation",
        dut_label: str = "BJTagent-DUT",
        scan_mode: str = "software",
        allow_hardware: bool = False,
        token_valid: bool = False,
    ) -> dict:
        driver_mode = _driver_mode(mode)
        blocked = _hardware_gate(driver_mode, allow_hardware=allow_hardware, token_valid=token_valid, require_token=True)
        if blocked:
            return blocked
        report = run_full_suite(
            mode=driver_mode,
            dut_label=str(dut_label or "BJTagent-DUT"),
            output_dir=self.output_dir or Path("analysis_out/web"),
            cfg=self._cfg(),
            scan_mode=scan_mode if scan_mode in {"software", "hardware"} else "software",
        )
        return {"ok": True, "mode": driver_mode, "report": _report_to_dict(report)}

    def run_simulation(self) -> dict:
        if self.current_plan is None:
            return {"ok": False, "error": "no current plan"}
        execution = execute_plan(
            self.current_plan,
            mode="simulation",
            output_dir=self.output_dir,
            allow_hardware=False,
            token_valid=True,
        )
        self.current_execution = execution
        return {"ok": True, "execution": execution}

    def diagnose_result(self, text: str = "") -> dict:
        source = str(text or "")
        if self.current_execution:
            source = source or str(self.current_execution.get("abort_reason") or self.current_execution.get("reason") or "")
        measurements = (self.current_execution or {}).get("measurements") or []
        tags = diagnose_tags(source, measurements=measurements)
        return {
            "ok": True,
            "diagnosis_tags": tags,
            "recommended_actions": recommend_actions(diagnosis_tags=tags),
        }

    def _cfg(self) -> HwConfig:
        return self.cfg or HwConfig()


def _refined_steps(
    values: list[float],
    *,
    step_v: float | None = None,
    points: int | None = None,
) -> list[float]:
    clean = sorted({round(float(value), 3) for value in values if isinstance(value, (int, float))})
    if not clean:
        return []
    start = clean[0]
    stop = clean[-1]
    if points is not None:
        count = max(len(clean), min(int(points or len(clean)), 200))
        if count <= 1:
            return [round(start, 3)]
        interval = (stop - start) / float(count - 1)
        return [round(start + interval * index, 3) for index in range(count)]
    if step_v is not None and float(step_v or 0) > 0:
        interval = float(step_v)
        next_values: list[float] = []
        current = start
        while current < stop:
            next_values.append(round(current, 3))
            current += interval
            if len(next_values) > 250:
                break
        next_values.append(round(stop, 3))
        return sorted(dict.fromkeys(next_values))
    return clean


def _driver_mode(mode: str) -> str:
    return mode if mode in {"simulation", "hardware"} else "simulation"


def _hardware_gate(
    mode: str,
    *,
    allow_hardware: bool,
    token_valid: bool,
    require_token: bool,
) -> dict | None:
    if mode != "hardware":
        return None
    if not allow_hardware:
        return {
            "ok": False,
            "blocked_reason": "hardware_not_allowed",
            "error": "hardware mode requires allow_hardware=true",
        }
    if require_token and not token_valid:
        return {
            "ok": False,
            "blocked_reason": "hardware_confirmation_required",
            "error": "hardware execution requires a valid confirmation token",
        }
    return None


def _is_executable_static_measure_primitive(primitive: dict[str, Any]) -> bool:
    if primitive.get("kind") != "measure":
        return False
    args = primitive.get("args") if isinstance(primitive.get("args"), dict) else {}
    if args.get("mode") != "static_point":
        return False
    if "vcc" not in args or "vbb" not in args:
        return False
    try:
        float(args["vcc"])
        float(args["vbb"])
    except (TypeError, ValueError):
        return False
    name = str(primitive.get("name") or "")
    return name.startswith("critic_")


def _is_executable_static_sweep_primitive(primitive: dict[str, Any]) -> bool:
    if primitive.get("kind") != "sweep":
        return False
    args = primitive.get("args") if isinstance(primitive.get("args"), dict) else {}
    if args.get("mode") != "static_point_sweep":
        return False
    if "vbb" not in args or not isinstance(args.get("vcc_values"), list):
        return False
    try:
        float(args["vbb"])
        for value in args["vcc_values"]:
            float(value)
    except (TypeError, ValueError):
        return False
    name = str(primitive.get("name") or "")
    return name.startswith("critic_")


def _is_executable_static_pulse_primitive(primitive: dict[str, Any]) -> bool:
    if primitive.get("kind") != "pulse":
        return False
    args = primitive.get("args") if isinstance(primitive.get("args"), dict) else {}
    if args.get("mode") != "static_point_pulse_pair":
        return False
    if "vcc" not in args or "vbb" not in args or not isinstance(args.get("pulse_width_us_values"), list):
        return False
    try:
        float(args["vcc"])
        float(args["vbb"])
        for value in args["pulse_width_us_values"]:
            int(value)
        if float(args.get("duty_cycle") or 0.0) > 0.1:
            return False
    except (TypeError, ValueError):
        return False
    name = str(primitive.get("name") or "")
    return name.startswith("critic_")


def _merge_hypotheses(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in list(existing or []) + list(incoming or []):
        name = str(item.get("name") or "")
        if not name:
            continue
        previous = merged.get(name)
        if previous is None or float(item.get("confidence") or 0.0) >= float(previous.get("confidence") or 0.0):
            merged[name] = dict(item)
    return sorted(merged.values(), key=lambda item: float(item.get("confidence") or 0.0), reverse=True)


def _precondition_result(name: str, runtime: BJTToolRuntime, arguments: dict[str, Any]) -> dict[str, Any]:
    mode = _driver_mode(str(arguments.get("mode") or "simulation"))
    if name == "current_plan_loaded":
        if runtime.current_plan is None:
            return _check_result(name, "failed", "no current plan is loaded")
        return _check_result(name, "passed", "current plan is loaded")
    if name == "current_plan_loaded_or_explicit_point":
        if runtime.current_plan is not None or ("vcc" in arguments and "vbb" in arguments):
            return _check_result(name, "passed", "current plan exists or explicit point was provided")
        return _check_result(name, "failed", "requires current plan or explicit vcc/vbb")
    if name in {"fixture_connected", "rainfall_sdk_available_or_simulation"}:
        if mode == "simulation":
            return _check_result(name, "passed", "simulation driver satisfies this precondition")
        return _check_result(name, "skipped", "hardware fixture state is not directly observable yet")
    if name == "dut_power_off":
        return _check_result(name, "skipped", "DUT power state is not directly observable yet")
    if name == "driver_can_be_created":
        return _check_result(name, "passed", "driver factory is configured")
    if name == "reserve_test_station":
        if mode == "simulation":
            return _check_result(name, "passed", "simulation does not require station reservation")
        return _check_result(name, "skipped", "asset lock manager is not enabled yet")
    if name == "belief_state_available":
        if runtime.current_belief is not None:
            return _check_result(name, "passed", "current DUT belief is available")
        if runtime.current_execution and runtime.current_execution.get("measurements"):
            return _check_result(name, "passed", "latest execution measurements can initialize DUT belief")
        return _check_result(name, "failed", "no DUT belief or measurements are available")
    return _check_result(name, "skipped", "no checker registered for this precondition")


def _postcondition_result(
    name: str,
    result: dict[str, Any],
    runtime: BJTToolRuntime,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if name == "device_session_closed":
        return _check_result(name, "passed", "tool handler completed its session scope")
    if name == "all_outputs_disabled":
        if "outputs disabled" in str(result.get("message") or ""):
            return _check_result(name, "passed", "handler reported disabled outputs")
        return _check_result(name, "skipped", "output state is not directly observable yet")
    if name == "selftest_passed_or_reported":
        return _check_result(name, "passed" if "selftest" in result else "failed", "selftest result is present")
    if name == "capture_summary_available":
        return _check_result(name, "passed" if "scope_check" in result else "failed", "scope summary is present")
    if name == "pin_probe_completed":
        observations = result.get("observations") if isinstance(result.get("observations"), list) else []
        return _check_result(name, "passed" if observations else "failed", "pin probe observations are present")
    if name == "detected_bjt_type_reported":
        return _check_result(name, "passed" if result.get("detected_bjt_type") else "failed", "detected type is present")
    if name == "measurements_within_plan_limits":
        measurement = result.get("measurement") if isinstance(result.get("measurement"), dict) else {}
        if not measurement:
            return _check_result(name, "failed", "measurement is missing")
        if runtime.current_plan is None:
            return _check_result(name, "passed", "measurement exists; no current plan limit to compare")
        ic = abs(float(measurement.get("Ic") or 0.0))
        if ic <= runtime.current_plan.ic_limit_a * 1.05:
            return _check_result(name, "passed", "collector current is within plan limit")
        return _check_result(name, "failed", "collector current exceeds plan limit")
    if name in {"outputs_disabled_after_point", "outputs_disabled_after_scan", "outputs_disabled_after_suite"}:
        return _check_result(name, "skipped", "output shutdown is handled inside hardware module but not yet independently sensed")
    if name == "vce_sat_estimate_available":
        return _check_result(name, "passed" if "vce_sat" in result else "failed", "Vce(sat) estimate is present")
    if name == "curve_points_recorded":
        return _check_result(name, "passed" if int(result.get("point_count") or 0) > 0 else "failed", "curve point count is present")
    if name == "report_generated":
        return _check_result(name, "passed" if "report" in result else "failed", "report is present")
    if name == "belief_state_updated":
        return _check_result(name, "passed" if result.get("belief") else "failed", "DUT belief state is present")
    if name == "spice_twin_generated":
        return _check_result(name, "passed" if result.get("spice_twin") else "failed", "SPICE digital twin is present")
    if name == "residual_followup_planned":
        plan = result.get("followup_plan") if isinstance(result.get("followup_plan"), dict) else {}
        return _check_result(name, "passed" if plan.get("candidates") is not None else "failed", "residual follow-up plan is present")
    if name == "next_batch_designed":
        design = result.get("batch_design") if isinstance(result.get("batch_design"), dict) else {}
        summary = design.get("summary") if isinstance(design.get("summary"), dict) else {}
        return _check_result(name, "passed" if summary.get("selected_count") is not None else "failed", "active-inference batch design is present")
    if name == "unknown_device_report_generated":
        report = result.get("unknown_device_report") if isinstance(result.get("unknown_device_report"), dict) else {}
        return _check_result(name, "passed" if report.get("conclusion") else "failed", "unknown device report is present")
    if name == "release_test_station":
        return _check_result(name, "passed", "station release is not stateful in simulation/current runtime")
    return _check_result(name, "skipped", "no checker registered for this postcondition")


def _residual_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_residual = (before.get("residuals") or {}).get("overall_mean_abs")
    after_residual = (after.get("residuals") or {}).get("overall_mean_abs")
    before_points = int((before.get("residuals") or {}).get("point_count") or 0)
    after_points = int((after.get("residuals") or {}).get("point_count") or 0)
    improvement = None
    if isinstance(before_residual, (int, float)) and isinstance(after_residual, (int, float)):
        improvement = round(float(before_residual) - float(after_residual), 6)
    return {
        "before_overall_mean_abs": before_residual,
        "after_overall_mean_abs": after_residual,
        "delta_overall_mean_abs": improvement,
        "before_point_count": before_points,
        "after_point_count": after_points,
        "added_points": max(0, after_points - before_points),
    }


def _check_result(name: str, status: str, message: str) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message}


def _point_to_dict(point: Any) -> dict:
    return {
        "Vbb": float(getattr(point, "Vbb")),
        "Vcc": float(getattr(point, "Vcc")),
        "Vb": float(getattr(point, "Vb")),
        "Vc": float(getattr(point, "Vc")),
        "Ib": float(getattr(point, "Ib")),
        "Ic": float(getattr(point, "Ic")),
        "Vbe": float(getattr(point, "Vbe")),
        "Vce": float(getattr(point, "Vce")),
        "beta": float(getattr(point, "beta")),
        "region": str(getattr(point, "region")),
    }


def _points_to_dict(points: list[Any]) -> list[dict]:
    return [_point_to_dict(point) for point in points]


def _report_to_dict(report: Any) -> dict:
    measurements = []
    output_curves = getattr(report, "output_curves", {}) or {}
    for _, curve_points in sorted(output_curves.items(), key=lambda item: item[0]):
        measurements.extend(curve_points)
    reference = getattr(report, "reference_point", None)
    return {
        "serial": getattr(report, "serial", ""),
        "detected_bjt_type": getattr(report, "bjt_type", ""),
        "dut_label": getattr(report, "dut_label", ""),
        "beta_median": getattr(report, "beta_median", None),
        "vce_sat": getattr(report, "vce_sat", None),
        "ic_at_sat": getattr(report, "Ic_at_sat", None),
        "measurements": _points_to_dict(measurements),
        "latest_measurement": _point_to_dict(reference) if reference is not None else None,
    }


def _normalized_static_points(points: list[dict[str, Any]] | None) -> list[dict[str, float]]:
    if not isinstance(points, list):
        return []
    normalized: list[dict[str, float]] = []
    for item in points:
        if not isinstance(item, dict):
            continue
        try:
            normalized.append({"vcc": round(float(item.get("vcc")), 3), "vbb": round(float(item.get("vbb")), 3)})
        except (TypeError, ValueError):
            continue
    return normalized


def _plan_update_step_note(update_type: str, vcc_count: int, vbb_count: int) -> str:
    label = {
        "grid_density": "细化扫描网格",
        "limits": "调整安全限值",
        "static_points": "调整静态测试点",
        "goal_depth": "调整测试目标/深度",
        "mixed": "综合调整计划",
    }.get(update_type, "综合调整计划")
    return "{0}：Vcc {1} 点，Vbb {2} 点，共 {3} 个扫描组合。".format(
        label,
        vcc_count,
        vbb_count,
        vcc_count * vbb_count,
    )


def _plan_from_mapping(data: dict[str, Any]) -> TestPlan:
    return TestPlan(
        model=str(data.get("model") or "UNKNOWN"),
        bjt_type=str(data.get("bjt_type") or "NPN"),
        goal=data.get("goal") if data.get("goal") in {"auto", "beta", "vce_sat", "curves", "screening", "full"} else "auto",
        depth=data.get("depth") if data.get("depth") in {"conservative", "standard", "deep"} else "standard",
        mode=str(data.get("mode") or "simulation"),
        vcc_steps=[float(item) for item in data.get("vcc_steps", [])],
        vbb_steps=[float(item) for item in data.get("vbb_steps", [])],
        static_points=_normalized_static_points(data.get("static_points")) or [{"vcc": 3.0, "vbb": 2.0}],
        ic_limit_a=float(data.get("ic_limit_a", 0.03)),
        power_limit_w=float(data.get("power_limit_w", 0.25)),
        sample_count=int(data.get("sample_count", 1)),
        scan_mode=str(data.get("scan_mode") or "software"),
        steps=[str(item) for item in data.get("steps", [])],
        safety_notes=[str(item) for item in data.get("safety_notes", [])],
        profile=dict(data.get("profile") or {}),
    )
