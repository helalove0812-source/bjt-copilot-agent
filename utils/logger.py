from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Any

import yaml

from utils.paths import project_root


def configure_logging(config_path: str | Path | None = None) -> None:
    path = Path(config_path) if config_path is not None else project_root() / "config" / "logging.yaml"
    config = _load_logging_config(path)
    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def _load_logging_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
