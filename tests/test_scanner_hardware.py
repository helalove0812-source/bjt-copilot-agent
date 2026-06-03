from __future__ import annotations

import pytest

from measurement.scanner import _extract_hardware_step_means


def test_extract_hardware_step_means_groups_plateaus_by_vcc_step() -> None:
    vcc_steps = [0.0, 1.0, 2.0]
    repeats = 2
    plateau_samples = 4

    vb_array = []
    vc_array = []
    expected = []
    for step_index, vcc in enumerate(vcc_steps):
        vb_repeats = []
        vc_repeats = []
        for repeat_index in range(repeats):
            vb_level = 0.1 * (step_index + 1) + repeat_index * 0.01
            vc_level = 1.0 * (step_index + 1) + repeat_index * 0.1
            vb_array.extend([vb_level] * plateau_samples)
            vc_array.extend([vc_level] * plateau_samples)
            vb_repeats.append(vb_level)
            vc_repeats.append(vc_level)
        expected.append((vcc, sum(vb_repeats) / len(vb_repeats), sum(vc_repeats) / len(vc_repeats)))

    result = _extract_hardware_step_means(
        vb_array,
        vc_array,
        vcc_steps=vcc_steps,
        repeats=repeats,
    )

    assert len(result) == len(expected)
    for (actual_vcc, actual_vb, actual_vc), (expected_vcc, expected_vb, expected_vc) in zip(result, expected):
        assert actual_vcc == expected_vcc
        assert abs(actual_vb - expected_vb) < 1e-9
        assert abs(actual_vc - expected_vc) < 1e-9


def test_extract_hardware_step_means_rejects_non_positive_repeats() -> None:
    with pytest.raises(ValueError, match="repeats must be positive"):
        _extract_hardware_step_means(
            [0.1, 0.1],
            [1.0, 1.0],
            vcc_steps=[0.0, 1.0],
            repeats=0,
        )


def test_extract_hardware_step_means_rejects_insufficient_samples() -> None:
    with pytest.raises(ValueError, match="insufficient samples"):
        _extract_hardware_step_means(
            [0.1, 0.2],
            [1.0, 1.1],
            vcc_steps=[0.0, 1.0],
            repeats=2,
        )
