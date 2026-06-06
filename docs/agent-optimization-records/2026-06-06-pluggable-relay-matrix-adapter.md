# Pluggable Relay Matrix Adapter

Date: 2026-06-06

## Stage Goal

Make external relay-matrix hardware a pluggable driver capability instead of baking relay logic into `PyRDDriver` or the measurement layer.

## Implemented Changes

- Added `core/relay_matrix.py`.
- Introduced `RelayMatrixAdapter` protocol:
  - `available`
  - `connect_pair`
  - `disconnect_all`
  - `pin_pair_probe`
- Added `RelayMatrixWrappedDriver`, which delegates normal instrument control to the base driver and relay permutation to an adapter.
- Added `NullRelayMatrixAdapter` as the safe hardware default.
- Added `SimulatedRelayMatrixAdapter` for integration tests and future adapter development.
- Updated `app.services.build_driver` so hardware mode can be wrapped with a relay adapter selected by `BJT_RELAY_MATRIX_BACKEND`.

## Configuration

```text
BJT_RELAY_MATRIX_BACKEND=none       # default, safe unavailable state
BJT_RELAY_MATRIX_BACKEND=simulated  # test/development adapter
```

Unknown backend names fail fast.

## Why It Matters

The agent can now treat arbitrary pin permutation as a capability of the test station, while the physical relay board remains replaceable. This keeps the unknown-device workflow stable as hardware evolves.

## Capability Boundary

Real PyRD hardware still does not gain arbitrary pin permutation by itself. The relay adapter must be configured and implemented for the actual external board.

## Verification

- `tests/test_relay_matrix_driver.py`
- `tests/test_relay_matrix_config.py`
- `tests/test_pin_probe.py`
- `tests/test_unknown_device_workflow.py`
