# BJT Test System Hardware Bring-Up Priority Design

## 1. Purpose

This document defines the next implementation baseline for the BJT test system after the initial simulation-first skeleton.

The new priority is:

- real `pyRD` hardware bring-up first
- deterministic hardware safety second
- NPN minimal measurement closure third
- GUI polish, full reports, and complete scan workflows later

This design is intentionally narrower and more execution-oriented than the earlier desktop/CLI baseline. It is optimized for getting `Raindrop Model S` working reliably on a real bench before the BJT fixture is fully ready.

## 2. Current Reality

Current state:

- `Model S` hardware is available
- `IPSDK3.2` and Python examples are available locally
- fixture wiring and DUT hookup are not fully ready yet
- the repository already contains a simulation-first desktop/CLI skeleton

Implication:

The fastest path to a trustworthy system is not “finish all product features.” The fastest path is to verify that the physical device, SDK, analog outputs, analog inputs, safety shutdown, and sampling timing behave correctly on the real machine.

## 3. Primary Goal

Build a hardware-first bring-up workflow that can be executed before the BJT fixture is complete and that transitions cleanly into NPN transistor validation once the wiring is ready.

Success means:

1. the application can enumerate and open `Model S`
2. the application can drive `V+`, `W1`, and `W2` in a controlled way
3. the application can sample `CH1` and `CH2` with explicit readiness polling and timeout handling
4. every failure path can safely shut down outputs
5. a CLI operator can run hardware self-test without the GUI
6. once NPN wiring is ready, the same service layer can perform a real static measurement

## 4. Scope

### In Scope

- upgrade `PyRDDriver` from thin wrapper to hardware bring-up driver
- implement real hardware self-test services and CLI commands
- implement scope acquisition with polling, timeout, and averaged readback
- implement explicit output disable flows for PSU and AWG
- add structured hardware diagnostics and human-readable logs
- add minimal NPN static measurement path for real hardware
- preserve simulation mode as fallback for development only

### Out Of Scope For This Phase

- full multi-point output curve scan
- full `VCE(sat)` forced-beta test sequence
- full PNP production workflow
- polished desktop GUI interaction flow
- final PDF/HTML reporting
- packaging and installer work

## 5. Architecture Shift

The repository currently contains a simulation-driven service flow. That is no longer the primary execution path.

The new execution order is:

```text
CLI self-test / hardware bring-up
    -> verified pyRD driver behavior
        -> verified acquisition timing and output control
            -> NPN minimal static measurement
                -> later integration into GUI and richer workflows
```

This means:

- `CLI` becomes the primary operator surface for early real-hardware debugging
- `GUI` remains present but is not the first integration surface
- `core/` becomes the critical subsystem for this phase
- `measurement/` should only absorb real-hardware logic after the driver layer is trustworthy

## 6. Driver Requirements

### `core/pyrd_driver.py`

The real hardware driver must provide:

- `connect()`
- `close()`
- `set_v_pos(volts)`
- `set_v_neg(volts)`
- `set_w1_dc(volts)`
- `set_w2_dc(volts)`
- `read_scope_mean(samples, frequency_hz, timeout_ms)`
- `disable_psu()`
- `disable_awg()`
- `disable_all()`
- `device_info()`

### Behavioral Requirements

- `connect()` must enumerate devices and fail with actionable diagnostics if none are found
- analog outputs must always be explicitly enabled and explicitly disabled
- scope acquisition must not assume readiness immediately after `AnalogInRun(True)`
- readback must poll `AnalogInStatus()` until ready or timeout
- all hardware exceptions must be normalized into clear Python exceptions
- `close()` must be safe to call repeatedly

### SDK Grounding

The driver implementation must align with the local SDK examples:

- `Supplies.py` for programmable `V+ / V-`
- `AnalogOutSample.py` and `ScopeAndWavegen.py` for AWG setup
- `AnalogINSample.py` for acquisition configuration and readiness polling

No custom assumptions should override the example-backed SDK semantics unless verified on the bench.

## 7. Hardware Self-Test Flow

The first executable target is a CLI hardware self-test.

### Command

```bash
python3 cli.py selftest --mode hardware
```

### Flow

1. enumerate and open the first `Model S`
2. print device identification and driver status
3. set `V+ = 1.0 V`, wait, then disable it
4. set `W1 = 1.0 V DC`, wait, then disable AWG
5. set `W2 = 1.0 V DC`, wait, then disable AWG
6. arm scope on `CH1` and `CH2`
7. acquire averaged values with timeout control
8. print results and timing metadata
9. call `disable_all()`
10. close the device

### Purpose

This flow verifies:

- SDK path bootstrap
- device opening
- power output control
- wavegen DC output control
- scope configuration
- acquisition readiness logic
- shutdown reliability

This test does not require a transistor to be present.

## 8. Scope Check Flow

The second executable target is a CLI scope sanity test for bench-level validation.

### Command

```bash
python3 cli.py scope-check --mode hardware --samples 2048 --freq 100000
```

### Flow

1. configure analog input channels
2. trigger immediate acquisition
3. poll until data ready or timeout
4. read both channels
5. print mean, min, max, and sample count
6. stop acquisition cleanly

This command exists to isolate acquisition issues from supply/AWG issues.

## 9. NPN Minimal Bring-Up Flow

Once the NPN fixture is wired according to the technical proposal, the next target is a minimal real measurement.

### Command

```bash
python3 cli.py npn-static --mode hardware --vcc 3.0 --vbb 2.0
```

### Assumed Wiring

- emitter to GND
- collector through `R_C` to `V+`
- base through `R_B` to `W1`
- `CH1` measures `V_B`
- `CH2` measures `V_C`

### Flow

1. call `disable_all()` before starting
2. set `V+`
3. set `W1`
4. wait configured settling time
5. acquire averaged `CH1 / CH2`
6. compute `Ib`, `Ic`, `Vbe`, `Vce`, `beta`
7. run safety checks
8. print a structured measurement result
9. disable outputs in `finally`

This is the first true transistor validation milestone.

## 10. Safety Model

This phase prioritizes deterministic shutdown over feature breadth.

### Mandatory Safety Behaviors

- every CLI command must enter with outputs disabled
- every CLI command must exit with outputs disabled
- timeout during acquisition must trigger shutdown
- invalid measurement values must trigger shutdown
- driver disconnect or SDK errors must trigger shutdown
- repeated shutdown calls must be safe and idempotent

### Software Protection Checks

- `abs(Ic) > Ic_max_A`
- `abs(Vce * Ic) > Pmax_W`
- non-finite `Vb`, `Vc`, `Ib`, `Ic`, `Vbe`, `Vce`
- scope not ready within timeout
- impossible voltage state relative to configured rail assumptions

### Required Logging

Every shutdown must record:

- command name
- timestamp
- reason
- configured outputs at time of abort if available

## 11. CLI Surface For This Phase

Required commands:

```bash
python3 cli.py selftest --mode hardware
python3 cli.py scope-check --mode hardware
python3 cli.py npn-static --mode hardware --vcc 3.0 --vbb 2.0
python3 cli.py detect --mode hardware
```

Guidelines:

- `selftest` is for driver and instrument bring-up
- `scope-check` is for acquisition isolation
- `npn-static` is for first bench validation with the fixture
- `detect` may remain limited until PNP wiring and detection comparison are validated

Simulation support remains allowed for development, but the phase is considered successful only when the hardware variants work.

## 12. Service Layer Changes

### `app/services.py`

This module must grow from a generic simulation-oriented launcher into explicit use-case services:

- `run_hardware_selftest()`
- `run_scope_check()`
- `run_npn_static_bringup()`
- `run_detect()`

### `app/orchestrator.py`

For this phase, orchestration can remain thin. It should:

- call services
- normalize errors
- preserve structured return values

It should not absorb low-level SDK logic.

## 13. Measurement Layer Changes

### `measurement/static.py`

This module must distinguish:

- pure math conversion from voltages to currents
- real hardware acquisition sequence

The measurement path should therefore be split conceptually into:

- `build_static_point(...)`
- `measure_static_point(...)`

The first remains deterministic and testable without hardware.
The second manages the real sequencing and calls the safety guard.

### `measurement/detector.py`

Detection should be reworked in two phases:

- Phase 1: reliable NPN probe path on real hardware
- Phase 2: add verified PNP probe path and comparison logic

For now, reliability beats completeness.

## 14. Testing Strategy

### Automated Tests

Keep unit tests for:

- math conversion
- safety checks
- service orchestration with simulation
- CLI argument parsing

Add targeted tests for:

- timeout handling paths
- repeated `disable_all()` behavior
- hardware command sequencing via fake `RD` object

### Manual Bench Validation

The real acceptance path is manual and sequential:

1. `selftest`
2. `scope-check`
3. `npn-static`
4. only then richer measurement workflows

Each manual step should have a corresponding expected console transcript in the README.

## 15. File-Level Focus

Primary files for the next iteration:

- `core/pyrd_driver.py`
- `core/psu.py`
- `core/awg.py`
- `core/scope.py`
- `core/safety.py`
- `measurement/static.py`
- `measurement/detector.py`
- `app/services.py`
- `app/orchestrator.py`
- `cli.py`
- `README.md`
- `tests/test_detector_logic.py`
- `tests/test_static_math.py`
- `tests/test_safety.py`
- `tests/test_cli_smoke.py`

The GUI files are not the main work surface for this phase.

## 16. Acceptance Criteria

### Stage 1: Device Bring-Up

- hardware device opens successfully from CLI
- `V+`, `W1`, and `W2` can each be toggled in isolation
- scope returns stable data or a controlled timeout error
- `disable_all()` reliably shuts down outputs

### Stage 2: Bench Validation

- operator can run `scope-check` and obtain two-channel statistics
- operator can run `npn-static` after wiring the fixture
- a valid `StaticPoint` is printed with plausible values

### Stage 3: Integration Readiness

- GUI and richer workflows consume already-validated hardware services
- no core driver logic needs to be moved into GUI code

## 17. Explicit Non-Goals

- do not optimize GUI aesthetics in this phase
- do not chase complete report generation in this phase
- do not implement broad feature expansion before the driver path is stable
- do not treat simulation success as proof of hardware readiness

## 18. Final Decision

The next implementation baseline is:

- hardware bring-up first
- CLI-first debugging surface
- safety-first output control
- NPN minimal real measurement before broader workflow expansion

This design becomes the execution reference for the next implementation plan and supersedes any assumption that simulation-first full-flow completion is the primary short-term objective.
