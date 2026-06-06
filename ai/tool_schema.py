from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class AgentToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]
    risk_level: str = "low"
    requires_confirmation: bool = False
    category: str = "agent"
    safety: dict[str, Any] = field(default_factory=dict)
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    reversible: bool = True
    dangerous: bool = False
    requires_asset_lock: bool = False
    supports_dry_run: bool = True
    availability_check: Callable[[dict[str, Any]], dict[str, Any] | None] | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    handler: Callable[..., dict] | None = field(default=None, repr=False, compare=False)

    def to_llm_schema(self) -> dict:
        parameters = self.parameters
        if self.supports_dry_run and isinstance(parameters, dict):
            properties = dict(parameters.get("properties", {}))
            properties.setdefault("dry_run", {"type": "boolean", "description": "Preview checks and planned call without executing the handler."})
            parameters = {**parameters, "properties": properties}
        return {
            "name": self.name,
            "description": self.description,
            "parameters": parameters,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "category": self.category,
            "safety": self.safety,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "reversible": self.reversible,
            "dangerous": self.dangerous,
            "requires_asset_lock": self.requires_asset_lock,
            "supports_dry_run": self.supports_dry_run,
        }


def object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }
