from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional, Sequence

from ai.assistant import summarize_execution_with_ai, summarize_plan_with_ai
from ai.test_planner import plan_from_text
from ai.tools import execute_plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI-assisted BJT test CLI")
    parser.add_argument("request", nargs="+", help="自然语言测试需求，例如：测 S8050，重点看 beta")
    parser.add_argument(
        "--mode",
        choices=("simulation", "hardware"),
        default="simulation",
        help="第一版默认只自动执行 simulation；hardware 仅生成计划",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="执行安全计划。hardware 需要同时传入 --confirm-hardware。",
    )
    parser.add_argument(
        "--confirm-hardware",
        action="store_true",
        help="确认允许按 AI 计划执行真实硬件输出。",
    )
    parser.add_argument(
        "--output-dir",
        default="analysis_out/ai_run",
        help="simulation 执行时的输出目录",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出计划和结果")
    parser.add_argument(
        "--ai-mode",
        choices=("local", "auto", "cloud"),
        default=None,
        help="AI 调用模式：local 不调 API，auto 只用 API 判断复杂上下文，cloud 完整调用 API。",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.ai_mode:
        os.environ["BJT_AI_MODE"] = args.ai_mode
    user_text = " ".join(args.request)
    plan = plan_from_text(user_text, mode=args.mode)
    summary, used_ai, llm_provider, llm_usage = summarize_plan_with_ai(plan, user_text)

    execution = None
    execution_summary = None
    if args.execute:
        hardware_confirmed = args.mode != "hardware" or args.confirm_hardware
        execution = execute_plan(
            plan,
            mode=args.mode,
            output_dir=Path(args.output_dir),
            allow_hardware=hardware_confirmed,
            token_valid=hardware_confirmed,
        )
        if execution is not None and not execution.get("skipped"):
            text, used_exec_ai, exec_provider, exec_usage = summarize_execution_with_ai(execution)
            execution_summary = {
                "summary": text,
                "used_ai_api": used_exec_ai,
                "llm_provider": exec_provider,
                "llm_usage": exec_usage,
            }

    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary,
                    "used_ai_api": used_ai,
                    "used_openai_api": used_ai and llm_provider.startswith("openai:"),
                    "llm_provider": llm_provider,
                    "llm_usage": llm_usage,
                    "plan": plan.to_dict(),
                    "execution": execution,
                    "execution_summary": execution_summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(summary)
    print()
    print("测试计划:")
    for index, step in enumerate(plan.steps, start=1):
        print("{0}. {1}".format(index, step))
    print()
    print("范围:")
    print("- Vcc steps: {0}".format(plan.vcc_steps))
    print("- Vbb steps: {0}".format(plan.vbb_steps))
    print("- Ic limit: {0:.3f} mA".format(plan.ic_limit_a * 1000.0))
    print("- Power limit: {0:.1f} mW".format(plan.power_limit_w * 1000.0))
    print()
    print("安全说明:")
    for note in plan.safety_notes:
        print("- {0}".format(note))
    if execution is not None:
        print()
        print("执行结果:")
        print(json.dumps(execution, ensure_ascii=False, indent=2))
    if execution_summary is not None:
        print()
        print("执行总结:")
        print(execution_summary["summary"])
    if not used_ai:
        print()
        print("提示: 未检测到可用 AI API，当前使用本地规则生成说明。")
    else:
        print()
        print("AI provider: {0}".format(llm_provider))
        if llm_usage:
            print("AI usage: {0}".format(json.dumps(llm_usage, ensure_ascii=False)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
