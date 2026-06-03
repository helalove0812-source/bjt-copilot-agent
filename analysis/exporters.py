from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path


def write_summary_json(report, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary.json"
    path.write_text(
        json.dumps(asdict(report), default=str, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
