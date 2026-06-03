from __future__ import annotations

import argparse
import json
from typing import Optional, Sequence

from app.orchestrator import AppOrchestrator
from core.types import HwConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BJT desktop shared CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect", help="Detect BJT type")
    detect_parser.add_argument(
        "--mode",
        choices=("hardware", "simulation"),
        default="hardware",
        help="Select hardware or explicit simulation mode",
    )

    selftest_parser = subparsers.add_parser("selftest", help="Run hardware self-test")
    selftest_parser.add_argument(
        "--mode",
        choices=("hardware", "simulation"),
        default="hardware",
        help="Select hardware or explicit simulation mode",
    )

    scope_check_parser = subparsers.add_parser(
        "scope-check", help="Read scope means via CLI"
    )
    scope_check_parser.add_argument(
        "--mode",
        choices=("hardware", "simulation"),
        default="hardware",
        help="Select hardware or explicit simulation mode",
    )
    scope_check_parser.add_argument("--samples", type=int, default=2048)
    scope_check_parser.add_argument("--freq", type=int, default=100000)

    npn_static_parser = subparsers.add_parser(
        "npn-static", help="Run minimal NPN static bring-up"
    )
    npn_static_parser.add_argument(
        "--mode",
        choices=("hardware", "simulation"),
        default="hardware",
        help="Select hardware or explicit simulation mode",
    )
    npn_static_parser.add_argument("--vcc", type=float, default=3.0)
    npn_static_parser.add_argument("--vbb", type=float, default=2.0)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    orchestrator = AppOrchestrator(config=HwConfig())

    if args.command == "detect":
        serial, result = orchestrator.detect(args.mode)
        print("{0}: {1}".format(serial, result))
        return 0

    if args.command == "selftest":
        print(json.dumps(orchestrator.selftest(args.mode), ensure_ascii=False))
        return 0

    if args.command == "scope-check":
        print(
            json.dumps(
                orchestrator.scope_check(
                    args.mode,
                    samples=args.samples,
                    frequency_hz=args.freq,
                ),
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "npn-static":
        point = orchestrator.npn_static(args.mode, args.vcc, args.vbb)
        print(
            json.dumps(
                {
                    "Vbe": point.Vbe,
                    "Vce": point.Vce,
                    "Ib": point.Ib,
                    "Ic": point.Ic,
                    "beta": point.beta,
                },
                ensure_ascii=False,
            )
        )
        return 0

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
