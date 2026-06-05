from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any


@dataclass(frozen=True)
class PromptLayers:
    stable: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)
    volatile: dict[str, Any] = field(default_factory=dict)

    def system_text(self) -> str:
        return _sectioned_text("stable", self.stable)

    def user_text(self) -> str:
        return json.dumps(
            {
                "prompt_layers": {
                    "context": self.context,
                    "volatile": self.volatile,
                }
            },
            ensure_ascii=False,
            indent=2,
        )

    def debug_dict(self) -> dict[str, Any]:
        return {
            "stable": self.stable,
            "context": self.context,
            "volatile": self.volatile,
        }


def make_volatile(**items: Any) -> dict[str, Any]:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **items,
    }


def _sectioned_text(name: str, payload: dict[str, Any]) -> str:
    return "<{0}>\n{1}\n</{0}>".format(
        name,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
