from __future__ import annotations

import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"


def main() -> int:
    processes: list[subprocess.Popen] = []

    def stop_all(*_args) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    api = subprocess.Popen([sys.executable, "api_server.py"], cwd=ROOT)
    processes.append(api)

    frontend = subprocess.Popen(["npm", "run", "dev"], cwd=FRONTEND)
    processes.append(frontend)

    print("\nBJT Web UI")
    print("Frontend: http://127.0.0.1:5173/")
    print("API:      http://127.0.0.1:8765/api/health")
    print("Press Ctrl+C to stop both services.\n")

    try:
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    stop_all()
                    return code
            signal.pause()
    except KeyboardInterrupt:
        stop_all()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
