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
    handler: Callable[..., dict] | None = field(default=None, repr=False, compare=False)

    def to_llm_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
        }


def object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }
