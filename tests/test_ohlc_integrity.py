"""R010 OHLC-integrity classifier tests (pure function, no DB)."""

from __future__ import annotations

from qsa.rules.ohlc_integrity import _classify

FACTORS = dict(low_factor=0.5, high_factor=2.0, range_factor=1.5)


def _sev(o, h, l, c):
    v = _classify(o, h, l, c, **FACTORS)
    return v[0] if v else None


def test_clean_bar_passes():
    # Normal SPY-shaped bar.
    assert _sev(689.58, 696.93, 684.83, 695.41) is None


def test_spy_dropped_digit_low_is_critical():
    # The motivating defect: low 69.005 against ~690 open/close.
    assert _sev(689.58, 696.93, 69.005, 695.41) == "critical"


def test_vz_and_ubs_dropped_digit_low_are_critical():
    assert _sev(40.17, 40.73, 10.5999, 40.57) == "critical"   # VZ 2026-01-08
    assert _sev(16.12, 16.14, 0.9242, 15.95) == "critical"    # UBS 2022-08-30


def test_ordering_violation_is_critical():
    # high below max(open,close) — impossible bar.
    assert _sev(10.0, 9.0, 8.0, 9.5) == "critical"
    # low above min(open,close) — impossible bar.
    assert _sev(10.0, 11.0, 10.5, 10.2) == "critical"
    # non-positive value.
    assert _sev(10.0, 11.0, 0.0, 10.5) == "critical"


def test_high_spike_is_warning_not_critical():
    # ARQQ-style real SPAC volatility: high 26 vs open 9.25 / close 11.3.
    assert _sev(9.25, 26.0, 8.88, 11.3) == "warning"


def test_wide_range_is_warning():
    # Range > 1.5x but ordering ok and no dropped-digit low.
    assert _sev(10.0, 18.0, 9.0, 12.0) == "warning"
