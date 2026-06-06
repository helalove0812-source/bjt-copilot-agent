# Relay Matrix Driver Capability

Date: 2026-06-06

## Stage Goal

Move relay-matrix pin permutation probing from a measurement-layer simulation shortcut into a driver-level capability contract.

## Why It Matters

The unknown-device workflow needs to behave like a test engineer: first establish topology, then choose characterization actions. For real three-pin unknown DUT work, arbitrary A/B/C pin-pair probing must be a hardware capability, not a hardcoded agent assumption.

## Implemented Changes

- Added relay-matrix capability methods to `DriverProtocol`:
  - `relay_matrix_available`
  - `relay_matrix_connect`
  - `relay_matrix_disconnect_all`
  - `pin_pair_probe`
- Implemented full simulated relay-matrix behavior in `SimulationDriver`.
- Added explicit unsupported relay-matrix methods to `PyRDDriver`.
- Reworked `run_relay_matrix_pin_permutation_probe` to call `driver.pin_pair_probe` for all ordered A/B/C pairs.
- Preserved safe fallback to `low_voltage_pin_probe` when hardware has no relay matrix.
- Added tests for:
  - simulation pair scanning
  - unavailable hardware capability
  - future hardware driver path using `pin_pair_probe`

## Capability Boundary

Current real PyRD hardware support remains:

```text
relay_matrix_available = false
```

This is intentional. The system now distinguishes:

- "hardware cannot perform arbitrary relay permutation yet"
- "agent has performed a full relay-matrix topology scan"

## Optimization Effect

Before:

- Relay-matrix simulation lived in `measurement/pin_probe.py`.
- Hardware path could only report a missing `relay_matrix_connect`.
- Future relay hardware would require rewiring the measurement layer.

After:

- Measurement layer depends on one typed driver operation: `pin_pair_probe`.
- Simulation and future hardware use the same scan loop.
- Unknown-device workflow can keep its high-level autonomy while hardware capability is checked cleanly at runtime.

## Verification Targets

- `tests/test_pin_probe.py`
- `tests/test_unknown_device_workflow.py`
- `tests/test_tool_call_agent.py`
- `/api/ai-chat` unknown-device smoke path
