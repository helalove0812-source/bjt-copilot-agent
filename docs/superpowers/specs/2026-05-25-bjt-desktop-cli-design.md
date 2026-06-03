# BJT Test System Desktop + CLI Design

## 1. Purpose

This document defines the implementation baseline for the BJT automated test system described in `BJT_Test_System_Technical_Proposal.md`.

Approved direction:

- Primary product: `PySide6` desktop application
- Secondary product: shared-core `CLI`
- Hardware baseline: `Raindrop Model S` via `pyRD`
- Simulation: explicit selectable mode, never silent fallback

This design intentionally supersedes older Web-oriented draft artifacts in `.trae/specs/design-host-software/`, which were based on a `FastAPI + React` control surface. The present implementation will instead follow the technical proposal's native desktop architecture.

## 2. Scope

### Included

- `pyRD`-based device discovery, connection, and shutdown lifecycle
- Hardware abstraction for PSU, AWG, scope, DMM, and safety control
- Measurement flows for:
  - BJT type detection
  - static parameter sweep
  - `VCE(sat)` measurement
  - `IC-VCE` output curve scan
  - beta linearity analysis
- Desktop GUI with live values, plots, logs, control actions, and emergency stop
- CLI commands reusing the same orchestration and analysis core
- Result persistence as `CSV + JSON + PDF`
- Automated tests for numerical correctness, decision logic, and safety behavior

### Excluded From First Delivery

- Remote Web control plane
- Multi-user or networked operation
- Automatic relay-based NPN/PNP rewiring
- Mandatory `python-docx` reporting backend
- Packaging into `.app` / `.exe`

## 3. Design Goals

- Match the technical proposal as closely as possible while keeping the first delivery implementable.
- Keep hardware I/O isolated from GUI and CLI code.
- Ensure desktop and CLI do not duplicate business logic.
- Preserve a deterministic safety shutdown path under every abnormal condition.
- Allow future addition of a remote control layer without rewriting the measurement core.

## 4. Architecture Decision

### Selected Approach

Use a layered application core with two presentation surfaces:

1. `GUI` for interactive laboratory use
2. `CLI` for scripted execution and regression checks

Both entry points call the same application services and measurement modules.

### Why This Approach

- It aligns with the technical proposal's `PySide6 + QThread + measurement modules` structure.
- It avoids divergence between desktop workflows and batch workflows.
- It keeps `pyRD` access within a controlled boundary.
- It is significantly lower risk than simultaneously building desktop, CLI, and remote Web control.

## 5. Target Repository Structure

```text
雨骤/
├── main.py
├── cli.py
├── requirements.txt
├── README.md
├── config/
│   ├── default.yaml
│   └── logging.yaml
├── core/
│   ├── __init__.py
│   ├── device.py
│   ├── driver_protocol.py
│   ├── pyrd_driver.py
│   ├── simulation_driver.py
│   ├── psu.py
│   ├── awg.py
│   ├── scope.py
│   ├── dmm.py
│   ├── safety.py
│   └── types.py
├── measurement/
│   ├── __init__.py
│   ├── detector.py
│   ├── static.py
│   ├── vce_sat.py
│   ├── curves.py
│   └── linearity.py
├── analysis/
│   ├── __init__.py
│   ├── data_processor.py
│   ├── exporters.py
│   └── report.py
├── app/
│   ├── __init__.py
│   ├── services.py
│   ├── orchestrator.py
│   └── runtime.py
├── gui/
│   ├── __init__.py
│   ├── main_window.py
│   ├── live_plot.py
│   ├── models.py
│   └── panels/
│       ├── connection_panel.py
│       ├── hw_config_panel.py
│       ├── action_panel.py
│       ├── live_value_panel.py
│       └── log_panel.py
├── utils/
│   ├── __init__.py
│   ├── config_loader.py
│   ├── logger.py
│   ├── paths.py
│   └── units.py
├── tests/
│   ├── test_detector_logic.py
│   ├── test_static_math.py
│   ├── test_linearity.py
│   ├── test_safety.py
│   └── test_cli_smoke.py
└── data/
```

## 6. Core Boundaries

### `core/`

Responsibilities:

- wrap `pyRD` and the SDK import path
- own hardware lifecycle
- expose typed interfaces for voltage/current acquisition and output control
- implement explicit simulation backend
- centralize emergency shutdown behavior

Rules:

- GUI code must never call raw `pyRD`
- measurement modules must depend on typed hardware interfaces, not on Qt
- direct SDK constants stay confined to the driver and low-level wrappers

### `measurement/`

Responsibilities:

- execute the physical measurement procedures from the technical proposal
- compute `Ib`, `Ic`, `Vbe`, `Vce`, `beta`, `region`
- emit structured point sets without persistence or presentation concerns

Rules:

- no file I/O
- no Qt signals
- no terminal printing

### `analysis/`

Responsibilities:

- derive `beta_median`
- compute `BetaLinearity`
- fit `Early voltage`
- serialize raw and summary data
- render plots and PDF report artifacts

### `app/`

Responsibilities:

- glue together configuration, driver creation, safety, measurement, and analysis
- expose high-level use cases such as `detect_only`, `run_static`, `run_full_suite`
- provide progress callbacks for GUI and CLI

### `gui/`

Responsibilities:

- render state
- dispatch user actions
- visualize live points and completed curves
- host worker thread and interruption flow

### `cli.py`

Responsibilities:

- parse commands and options
- build runtime config
- call the same service layer as the GUI
- stream concise progress logs to stdout

## 7. Driver Strategy

### Real Hardware Mode

The real driver will load `pyRD` from:

`/Users/helap/Documents/雨骤/IPSDK3.2/IP-SDK/Python/src`

Expected supporting binaries are already present in `IPSDK3.2/IP-SDK/Python/lib`.

### Simulation Mode

Simulation is a first-class backend selected explicitly by the user:

- GUI: selectable device mode in the connection panel
- CLI: `--mode simulation`

Simulation will generate deterministic synthetic responses for:

- NPN and PNP detection
- static sweep point evolution
- saturation behavior
- output curves
- beta linearity datasets

The simulation backend exists for development, UI validation, and unit testing. It must not silently activate when hardware connection fails.

## 8. Runtime Flow

### GUI Flow

1. User selects `Real Hardware` or `Simulation`
2. User configures `R_B`, `R_C`, `Ic_max`, `Pmax`, beta-linearity window, and DUT label
3. GUI creates worker-thread orchestrator
4. Orchestrator builds runtime and selected driver
5. Orchestrator executes requested action or full suite
6. Results stream back through callbacks/signals
7. Analysis exports artifacts
8. Runtime performs orderly shutdown in `finally`

### CLI Flow

1. User calls `python cli.py <command> ...`
2. CLI builds the same runtime config
3. CLI invokes the same service/orchestrator methods
4. Console logs show progress and result summary
5. Export files are written identically to GUI runs

## 9. Data Model

Canonical domain objects:

- `HwConfig`
- `StaticPoint`
- `BetaLinearity`
- `DeviceReport`
- `RunArtifacts`

Additional runtime types:

- `DriverMode = Literal["hardware", "simulation"]`
- `RunAction = Literal["detect", "static", "sat", "curves", "linearity", "full"]`

All persisted outputs must derive from these canonical types rather than from ad hoc dicts.

## 10. Safety Model

### Safety Layers

- physical current limiting from the fixture
- software checks inside each measurement loop
- immediate emergency shutdown API callable from GUI, CLI, and exception handlers

### Mandatory Shutdown Triggers

- `Ic > Ic_max_A`
- `|Vce * Ic| > Pmax_W`
- acquisition timeout
- driver disconnect or invalid SDK state
- explicit user stop
- impossible measurement state indicating likely short/open fault

### Shutdown Contract

Emergency shutdown must:

1. disable AWG outputs
2. disable PSU outputs
3. stop active acquisition if possible
4. record the reason
5. raise a typed exception to the orchestrator

The orchestrator must convert this into:

- GUI error signal and recoverable idle state
- CLI non-zero exit with a concise diagnostic

## 11. Reporting Strategy

First-delivery report backend:

- `CSV` for raw point sets
- `JSON` for structured summary
- `PDF` for human-readable report

Recommended implementation:

- `matplotlib` for plot rendering
- `reportlab` for PDF assembly

Rationale:

- fewer runtime dependencies than HTML-to-PDF stacks
- stable in local desktop environments
- easier bundling later

The report must include:

- DUT label and device serial
- measurement timestamp
- hardware configuration
- `beta_median`
- `VCE(sat)`
- output curves image
- beta-linearity image and statistics
- warnings and abort events
- raw file manifest

## 12. GUI Design Constraints

- Dark industrial visual style
- Fast scanability for live laboratory use
- Dedicated emergency stop action with highest visual priority
- Separate areas for configuration, actions, live values, plots, and log stream

Plotting choice:

- default: `matplotlib` embedded in Qt
- fallback upgrade path: use `pyqtgraph` only if measured live refresh is insufficient

This keeps the initial implementation simpler while preserving a clear performance escape hatch.

## 13. CLI Surface

Planned commands:

```bash
python cli.py detect --mode hardware
python cli.py static --mode hardware --dut S8050-A1
python cli.py curves --mode simulation
python cli.py full --mode hardware --dut S8050-A1 --output ./data
```

CLI requirements:

- same configuration schema as GUI
- same export layout as GUI
- machine-readable non-zero exit on failure
- concise summary on success

## 14. Testing Strategy

### Unit Tests

- detector decision thresholds
- static-point computation math
- beta-linearity calculation
- safety trigger logic
- report serialization sanity checks

### Driver-Facing Tests

- mock-driver tests for measurement workflows
- simulation-mode smoke tests for full-run orchestration

### Manual Hardware Validation

- verify SDK import and device enumeration
- verify supply output and scope readback loop
- verify NPN sample run
- verify PNP sample run
- verify emergency stop behavior

Real hardware tests are required for acceptance but must not be mandatory for normal local test execution.

## 15. Implementation Order

1. repository scaffold and dependency manifest
2. canonical types and configuration loader
3. `pyRD` driver bootstrap and simulation driver
4. PSU/AWG/scope/safety wrappers
5. detector and static measurer
6. saturation and curve sweep modules
7. beta-linearity and analysis pipeline
8. export/report pipeline
9. CLI entrypoint
10. PySide6 GUI and plotting
11. hardware validation and bug fixing

## 16. Risks And Mitigations

### Risk: SDK import or binary loading instability

Mitigation:

- isolate SDK bootstrap in one module
- fail with explicit diagnostics
- preserve simulation mode for development continuity

### Risk: GUI thread blocking

Mitigation:

- keep hardware access inside worker thread only
- communicate through typed Qt signals/callback adapters

### Risk: PNP path deviates from nominal assumptions

Mitigation:

- treat PNP as a first-class test path
- surface emitter-voltage deviation warnings in GUI and CLI logs

### Risk: live plotting performance

Mitigation:

- decimate repaint frequency while preserving acquisition cadence
- allow later swap from `matplotlib` to `pyqtgraph`

### Risk: reporting scope growth

Mitigation:

- lock first delivery to `CSV + JSON + PDF`
- defer `python-docx` and ISO17025 formatting expansion to a later report backend

## 17. Final Decisions

- Desktop application is the primary operator interface.
- CLI is a peer entrypoint on top of the same application core.
- `pyRD` is the only real-hardware integration baseline.
- Simulation is explicit and selectable.
- The current phase targets a single-machine local application, not a network service.
- The first implementation optimizes for correctness, recoverability, and architectural cleanliness over premature feature expansion.
