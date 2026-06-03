from core.types import HwConfig
from measurement.static import build_static_point, measure_static_point


def test_build_static_point_for_npn_math():
    point = build_static_point(
        bjt_type="NPN",
        R_B=22_000.0,
        R_C=220.0,
        Vbb=1.50,
        Vcc=5.00,
        Vb=0.681,
        Vc=2.93,
    )

    assert round(point.Ib * 1e6, 1) == 37.2
    assert round(point.Ic * 1e3, 2) == 9.41
    assert round(point.beta, 0) == 253
    assert point.Vbe == point.Vb
    assert point.Vce == point.Vc
    assert point.region == "active"


def test_build_static_point_marks_cutoff_when_vbe_is_low():
    point = build_static_point(
        bjt_type="NPN",
        R_B=22_000.0,
        R_C=220.0,
        Vbb=0.30,
        Vcc=5.00,
        Vb=0.20,
        Vc=5.00,
    )

    assert round(point.Ib * 1e6, 2) == 4.55
    assert point.Ic == 0.0
    assert point.beta == 0.0
    assert point.region == "cutoff"


def test_build_static_point_marks_saturation_when_vce_is_low():
    point = build_static_point(
        bjt_type="NPN",
        R_B=22_000.0,
        R_C=220.0,
        Vbb=1.50,
        Vcc=5.00,
        Vb=0.70,
        Vc=0.10,
    )

    assert round(point.Ib * 1e6, 2) == 36.36
    assert point.Vce == 0.10
    assert point.region == "saturation"


def test_build_static_point_for_pnp_math_uses_vcc_as_reference():
    point = build_static_point(
        bjt_type="PNP",
        R_B=22_000.0,
        R_C=220.0,
        Vbb=3.50,
        Vcc=5.00,
        Vb=4.319,
        Vc=2.07,
    )

    assert round(point.Ib * 1e6, 1) == 37.2
    assert round(point.Ic * 1e3, 2) == 9.41
    assert round(point.beta, 0) == 253
    assert round(point.Vbe, 3) == -0.681
    assert round(point.Vce, 2) == -2.93
    assert point.region == "active"


def test_measure_static_point_sequences_outputs_and_scope_read():
    class FakeDriver:
        def __init__(self):
            self.events = []

        def disable_all(self):
            self.events.append("disable_all")

        def set_v_pos(self, volts):
            self.events.append(("v_pos", volts))

        def set_w1_dc(self, volts):
            self.events.append(("w1", volts))

        def read_scope_mean(
            self, samples, frequency_hz=100000, timeout_ms=200
        ):
            self.events.append(("scope", samples, frequency_hz, timeout_ms))
            return 0.68, 2.90

    driver = FakeDriver()

    point = measure_static_point(
        driver,
        bjt_type="NPN",
        cfg=HwConfig(),
        Vbb=2.0,
        Vcc=3.0,
        samples=2048,
        frequency_hz=100000,
        timeout_ms=200,
    )

    assert round(point.Vbe, 2) == 0.68
    assert round(point.Vce, 2) == 2.90
    assert driver.events == [
        "disable_all",
        ("v_pos", 3.0),
        ("w1", 2.0),
        ("scope", 2048, 100000, 200),
    ]
