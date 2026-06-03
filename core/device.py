from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import Any


SDK_SRC = (
    Path(__file__).resolve().parent.parent
    / "IPSDK3.2"
    / "IP-SDK"
    / "Python"
    / "src"
)

_WINDOWS_DLL_DIR_HANDLES: list[Any] = []


def _sdk_python_root() -> Path:
    return SDK_SRC.resolve().parent


def _sdk_lib_root() -> Path:
    return _sdk_python_root() / "lib"


def _python_bits() -> int:
    return ctypes.sizeof(ctypes.c_void_p) * 8


def sdk_dll_dir() -> Path:
    return _sdk_lib_root() / ("64" if _python_bits() == 64 else "32")


def _prepend_env_path(path: Path) -> None:
    path_text = str(path)
    current = os.environ.get("PATH", "")
    entries = current.split(os.pathsep) if current else []
    if path_text not in entries:
        os.environ["PATH"] = path_text if not current else path_text + os.pathsep + current


def _ensure_windows_dll_search_path() -> None:
    if os.name != "nt":
        return

    for candidate in (sdk_dll_dir(), _sdk_lib_root()):
        if not candidate.exists():
            continue

        _prepend_env_path(candidate)
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is None:
            continue
        try:
            handle = add_dll_directory(str(candidate))
        except FileNotFoundError:
            continue
        _WINDOWS_DLL_DIR_HANDLES.append(handle)


def ensure_sdk_path() -> Path:
    sdk_src = SDK_SRC.resolve()
    sdk_src_text = str(sdk_src)
    if sdk_src_text not in sys.path:
        sys.path.insert(0, sdk_src_text)
    _ensure_windows_dll_search_path()
    return sdk_src


def sdk_runtime_info() -> dict[str, Any]:
    dll_dir = sdk_dll_dir()
    expected_dll = dll_dir / "InstrumentsPlayground.dll"
    ftdi_name = "ftd2xx64.dll" if _python_bits() == 64 else "ftd2xx.dll"
    return {
        "sdk_src": str(SDK_SRC.resolve()),
        "sdk_python_root": str(_sdk_python_root()),
        "dll_dir": str(dll_dir),
        "python_bits": _python_bits(),
        "platform": sys.platform,
        "expected_dll": str(expected_dll),
        "expected_dll_exists": expected_dll.exists(),
        "ftdi_dll": str(dll_dir / ftdi_name),
        "ftdi_dll_exists": (dll_dir / ftdi_name).exists(),
    }


def probe_sdk_runtime() -> dict[str, Any]:
    ensure_sdk_path()
    info = sdk_runtime_info()
    if os.name != "nt":
        return info

    dll_dir = sdk_dll_dir()
    candidates = [
        dll_dir / "InstrumentsPlayground.dll",
        dll_dir / ("ftd2xx64.dll" if _python_bits() == 64 else "ftd2xx.dll"),
        dll_dir / "sqlite3.dll",
    ]
    load_results: dict[str, str] = {}
    for dll_path in candidates:
        try:
            ctypes.WinDLL(str(dll_path))
        except OSError as exc:
            load_results[dll_path.name] = f"load_failed: {exc}"
        else:
            load_results[dll_path.name] = "ok"
    info["dll_load_results"] = load_results
    return info
