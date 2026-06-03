# BJT Test System

This repository contains the initial scaffold for a local BJT desktop and CLI
test system built around the Raindrop Model S `pyRD` SDK.

## Current Status

Task 1 establishes:

- baseline Python dependencies in `requirements.txt`
- default application configuration in `config/default.yaml`
- logging configuration in `config/logging.yaml`
- utility helpers under `utils/`
- a focused configuration loader test in `tests/test_config_loader.py`

## Quick Start

1. Install dependencies:

   ```bash
   python3 -m pip install -r requirements.txt
   ```

2. Runtime prerequisites:

   - Python 3.9 is the currently validated interpreter for this repository.
   - The Raindrop `pyRD` SDK source tree is expected at `IPSDK3.2/IP-SDK/Python/src`.
   - Hardware mode currently bootstraps the SDK by prepending that path in `core/device.py`.

3. Run the focused tests:

   ```bash
   python3 -m pytest tests/test_config_loader.py tests/test_detector_logic.py -v
   ```

## Minimal Full-Run

Simulation mode now supports a minimal shared-core full-run path that writes
`summary.json` to the selected output directory.

```python
from pathlib import Path

from app.services import run_full_suite
from core.types import HwConfig

report = run_full_suite(
    mode="simulation",
    dut_label="S8050-A1",
    output_dir=Path("out"),
    cfg=HwConfig(),
)
```

## BJT Agent

The repository now includes a BJT automated test Agent built on:

- local rules for intent parsing and constraint extraction
- optional LLM assistance for plan / execution summaries
- local safety policy gates for planning and hardware execution
- data-driven regression evaluation against curated JSONL datasets

This is not a neural-network-only system. The current architecture is a
rule-first BJT automation Agent with optional LLM assistance.

### CLI Planning And Execution

`ai_cli.py` can turn a natural-language request into a safe BJT test plan. It
works without an API key by using the local model database and rule-based
planner. If `DEEPSEEK_API_KEY` is set, `ai_cli.py` asks the DeepSeek
OpenAI-compatible Chat Completions API to summarize the generated plan. If no
DeepSeek key is present but `OPENAI_API_KEY` is set, it falls back to the OpenAI
Responses API.

```bash
python3 ai_cli.py 测 S8050 重点看 beta
python3 ai_cli.py 测 S8050 完整报告 --execute --json
```

DeepSeek configuration:

```bash
export DEEPSEEK_API_KEY="your-key"
export DEEPSEEK_MODEL="deepseek-v4-flash"
python3 ai_cli.py 测 2N3904 饱和压降
```

Optional provider override:

```bash
export BJT_AI_PROVIDER="deepseek"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
```

Current behavior:

- Automatic execution defaults to `simulation` mode.
- CLI hardware execution requires both `--mode hardware` and
  `--confirm-hardware`.
- The programmatic `TestAgent` path requires both caller permission
  (`allow_hardware=True`) and a valid one-time hardware confirmation token
  before real hardware output is opened.
- Unknown models enter a conservative guidance path first. The Agent asks for
  `管型`、`Vceo`、`Ic 最大值`、`Ptot`; once those fields are complete, it builds a
  temporary user-supplied profile and generates a safe plan.
- Until the unknown model fields are complete, the request stays on a
  conservative / guidance path rather than going straight to hardware
  execution.
- PNP requests generate a conservative guidance plan with explicit wiring and
  datasheet checks, but automatic hardware execution remains blocked.
- Runtime abort guard is enabled only for `hardware` point-by-point execution.
  It stops the run early on `Ic` limit, power limit, or obvious instability
  trend, and reports a structured aborted result.
- Hardware execution remains behind explicit user confirmation and the local
  safety guard.

Example hardware command after checking wiring and the generated plan:

```bash
python3 ai_cli.py 测 S8050 保守测试 beta --mode hardware --execute --confirm-hardware
```

AI execution writes `ai_execution.json` to the selected output directory.

The desktop GUI also includes an "AI 助手" panel. It can generate a plan from
natural language, run the plan in simulation mode, and run hardware only after a
confirmation dialog.

## Agent Regression

The repository includes a focused Agent regression baseline for local intent
parsing, planning policy, and safety behavior.

Current main datasets:

- focused gold cases: `数据/agent_regression_cases.jsonl`
- mainline dataset: `数据/transistor_agent_samples.v3.jsonl`

Recommended machine-readable regression command:

```bash
python3 scripts/run_agent_regression.py --json
```

Human-readable summary:

```bash
python3 scripts/run_agent_regression.py
```

What it checks:

- focused gold regression cases in `数据/agent_regression_cases.jsonl`
- the broader sample dataset in `数据/transistor_agent_samples.v3.jsonl`
- key Agent pytest coverage for intent parsing and safety behavior

Recommended full test command:

```bash
python3 -m pytest -q
```

The GitHub Actions workflow `.github/workflows/agent-regression.yml` runs the
machine-readable regression command in CI.

## Hardware Bring-Up

### 1. Self-Test

```bash
python3 cli.py selftest --mode hardware
```

Expected:

- device opens
- V+, W1, W2 are toggled
- CH1/CH2 mean values are printed
- outputs are disabled before exit

### 2. Scope Check

```bash
python3 cli.py scope-check --mode hardware --samples 2048 --freq 100000
```

Expected:

- scope mean values are printed for CH1/CH2
- outputs remain in a deterministic safe-off state before exit

### 3. NPN Static Bring-Up

```bash
python3 cli.py npn-static --mode hardware --vcc 3.0 --vbb 2.0
```

Expected:

- the static point includes Vbe, Vce, Ib, Ic, and beta
- outputs are disabled before exit
