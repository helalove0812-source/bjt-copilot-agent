from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def config_dir() -> Path:
    return project_root() / "config"
