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
    run_npn_static_bringup,
    run_scan_curves,
    run_scope_check,
)
from ai.action_recommender import recommend_actions
from ai.agent_memory import MemoryStore, TodoStore
from ai.rules import diagnose_tags
from ai.safety import evaluate_execution_request
from ai.session_search import SessionSearchStore
from ai.task_delegation import AgentTaskGraph
from ai.test_planner import TestPlan, build_test_plan
from ai.tool_schema import AgentToolSchema, object_schema
from ai.tools import execute_plan, preflight_plan
from ai.transistor_db import lookup_transistor
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

    def schemas(self) -> list[AgentToolSchema]:
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
                handler=self.device_connect,
            ),
            AgentToolSchema(
                name="device_emergency_off",
                description="Immediately disable device outputs. This tool is always allowed and should be available as an emergency stop.",
                parameters=object_schema({"mode": {"type": "string", "enum": ["simulation", "hardware"]}}),
                risk_level="medium",
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
                handler=self.scope_check,
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
        schema = next((item for item in self.schemas() if item.name == name), None)
        if schema is None or schema.handler is None:
            result = {"ok": False, "error": "unknown tool: {0}".format(name)}
            return ToolCallRecord(name=name, arguments=arguments, result=result)
        try:
            result = schema.handler(**dict(arguments or {}))
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        self.task_graph.mark_tool_result(name, result)
        return ToolCallRecord(name=name, arguments=arguments or {}, result=result)

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
        applied = self.pending_plan_update
        self.pending_plan_update = None
        return {
            "ok": True,
            "plan": self.current_plan.to_dict(),
            "applied_update": applied,
        }

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
        return {"ok": True, "mode": driver_mode, "measurement": _point_to_dict(point)}

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
