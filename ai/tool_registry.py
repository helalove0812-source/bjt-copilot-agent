from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ai.tool_schema import AgentToolSchema


@dataclass
class ToolRegistry:
    _tools: dict[str, AgentToolSchema] = field(default_factory=dict)
    precondition_check: Callable[[str, dict[str, Any], AgentToolSchema], list[dict[str, Any]]] | None = None
    postcondition_check: Callable[[dict[str, Any], AgentToolSchema, dict[str, Any]], list[dict[str, Any]]] | None = None

    def register(self, schema: AgentToolSchema) -> None:
        if not schema.name:
            raise ValueError("tool name is required")
        if schema.name in self._tools:
            raise ValueError("duplicate tool: {0}".format(schema.name))
        self._tools[schema.name] = schema

    def schemas(self) -> list[AgentToolSchema]:
        return list(self._tools.values())

    def get(self, name: str) -> AgentToolSchema | None:
        return self._tools.get(name)

    def dispatch(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        schema = self.get(name)
        args = dict(arguments or {})
        if schema is None or schema.handler is None:
            return _tool_error("unknown_tool", "unknown tool: {0}".format(name))

        validation_error = _validate_arguments(schema, args)
        if validation_error:
            return _tool_error("invalid_arguments", validation_error)

        safety_error = _validate_safety(schema, args)
        if safety_error:
            return {
                "ok": False,
                "blocked_reason": safety_error["blocked_reason"],
                "error": safety_error["error"],
                "tool": name,
                "category": schema.category,
            }

        precondition_results = self.precondition_check(name, args, schema) if self.precondition_check else []
        failed_preconditions = [item for item in precondition_results if item.get("status") == "failed"]
        if args.get("dry_run") is True:
            return {
                "ok": True,
                "dry_run": True,
                "would_call": name,
                "arguments": {key: value for key, value in args.items() if key != "dry_run"},
                "ready": not failed_preconditions,
                "precondition_checks": precondition_results,
                "contract": schema.to_llm_schema(),
                "message": "dry-run only; handler was not executed",
            }
        if failed_preconditions:
            return {
                "ok": False,
                "blocked_reason": "precondition_failed",
                "error": "precondition failed: {0}".format(failed_preconditions[0].get("name", "unknown")),
                "precondition_checks": precondition_results,
                "tool": name,
                "category": schema.category,
            }

        availability_error = schema.availability_check(args) if schema.availability_check else None
        if availability_error:
            return {
                "ok": False,
                "blocked_reason": availability_error.get("blocked_reason", "tool_unavailable"),
                "error": availability_error.get("error", "tool is unavailable"),
                "tool": name,
                "category": schema.category,
            }

        try:
            call_args = {key: value for key, value in args.items() if key != "dry_run"}
            result = schema.handler(**call_args)
        except Exception as exc:
            return _tool_error("tool_exception", str(exc), tool=name, category=schema.category)

        if not isinstance(result, dict):
            result = {"ok": True, "result": result}
        postcondition_results = self.postcondition_check(result, schema, args) if self.postcondition_check else []
        if postcondition_results:
            result = dict(result)
            result["postcondition_checks"] = postcondition_results
            failed_postconditions = [item for item in postcondition_results if item.get("status") == "failed"]
            if failed_postconditions and result.get("ok", False):
                result["ok"] = False
                result["blocked_reason"] = "postcondition_failed"
                result["error"] = "postcondition failed: {0}".format(failed_postconditions[0].get("name", "unknown"))
        return result


def _validate_arguments(schema: AgentToolSchema, arguments: dict[str, Any]) -> str:
    parameters = schema.parameters
    properties = parameters.get("properties") if isinstance(parameters, dict) else {}
    required = parameters.get("required") if isinstance(parameters, dict) else []
    additional = parameters.get("additionalProperties", True) if isinstance(parameters, dict) else True
    if not isinstance(properties, dict):
        return ""
    for name in required or []:
        if name not in arguments:
            return "missing required argument: {0}".format(name)
    if additional is False:
        for name in arguments:
            if name == "dry_run" and schema.supports_dry_run:
                continue
            if name not in properties:
                return "unexpected argument: {0}".format(name)
    for name, value in arguments.items():
        if name == "dry_run" and schema.supports_dry_run:
            if not isinstance(value, bool):
                return "argument dry_run expected boolean"
            continue
        property_schema = properties.get(name)
        if not isinstance(property_schema, dict):
            continue
        if not _matches_type(value, property_schema.get("type")):
            return "argument {0} expected {1}".format(name, property_schema.get("type"))
        enum = property_schema.get("enum")
        if enum and value not in enum:
            return "argument {0} must be one of {1}".format(name, enum)
    return ""


def _validate_safety(schema: AgentToolSchema, arguments: dict[str, Any]) -> dict[str, str] | None:
    safety = schema.safety or {}
    max_voltage = safety.get("max_voltage_v")
    if isinstance(max_voltage, (int, float)):
        for name in ("voltage_v", "vcc", "vbb"):
            value = arguments.get(name)
            if isinstance(value, (int, float)) and abs(float(value)) > float(max_voltage):
                return {
                    "blocked_reason": "safety_limit_exceeded",
                    "error": "{0} exceeds max_voltage_v={1}".format(name, max_voltage),
                }
    max_current = safety.get("max_current_a")
    if isinstance(max_current, (int, float)):
        for name in ("current_limit_a", "current_a", "ic_limit_a"):
            value = arguments.get(name)
            if isinstance(value, (int, float)) and abs(float(value)) > float(max_current):
                return {
                    "blocked_reason": "safety_limit_exceeded",
                    "error": "{0} exceeds max_current_a={1}".format(name, max_current),
                }
    approval_rule = safety.get("requires_human_approval_if")
    if isinstance(approval_rule, dict) and _rule_matches(arguments, approval_rule):
        return {
            "blocked_reason": "hardware_confirmation_required",
            "error": "tool requires human approval for the requested arguments",
        }
    return None


def _rule_matches(arguments: dict[str, Any], rule: dict[str, Any]) -> bool:
    for key, expected in rule.items():
        actual = arguments.get(key, False if isinstance(expected, bool) else None)
        if actual != expected:
            return False
    return True


def _matches_type(value: Any, expected: Any) -> bool:
    if expected is None:
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def _tool_error(code: str, message: str, *, tool: str = "", category: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "error": message,
        "error_code": code,
        "tool": tool,
        "category": category,
    }
