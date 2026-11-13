"""Golden-model properties — deterministic, offline, no board/HDL simulator."""
from __future__ import annotations

import numpy as np

from hw_trojan.config import HWTrojanConfig
from hw_trojan import dsp


def _cfg():
    return HWTrojanConfig()


def test_baseline_exact_disabled_equals_clean():
    cfg = _cfg()
    hq = dsp.design_coeffs(cfg)
    x = dsp.synth_speechlike(cfg.win * 20, cfg)
    clean = dsp.fir_fixed(x, hq, cfg)
    off, armed, _ = dsp.run_trojan(x, hq, cfg, trojan_en=False)
    assert np.array_equal(off, clean)
    assert armed is None


def test_benign_audio_never_arms_and_is_bit_exact():
    cfg = _cfg()
    hq = dsp.design_coeffs(cfg)
    x = dsp.synth_speechlike(cfg.win * 40, cfg)
    clean = dsp.fir_fixed(x, hq, cfg)
    on, armed, _ = dsp.run_trojan(x, hq, cfg, trojan_en=True)
    assert armed is None
    assert np.array_equal(on, clean)


def test_selftest_vector_does_not_arm():
    cfg = _cfg()
    hq = dsp.design_coeffs(cfg)
    _, armed, _ = dsp.run_trojan(dsp.selftest_vector(), hq, cfg, trojan_en=True)
    assert armed is None


def test_tone_arms_after_dwell():
    cfg = _cfg()
    hq = dsp.design_coeffs(cfg)
    x = dsp.tone(cfg.win * (cfg.dwell + 2), cfg.f_trig, 0.1, cfg.fs)
    _, armed, dwell_peak = dsp.run_trojan(x, hq, cfg, trojan_en=True)
    assert armed is not None
    assert dwell_peak >= cfg.dwell


def test_payload_is_bit_exact_bypass_after_arm():
    cfg = _cfg()
    hq = dsp.design_coeffs(cfg)
    head = dsp.synth_speechlike(cfg.win * 4, cfg)
    burst = dsp.tone(cfg.win * (cfg.dwell + 2), cfg.f_trig, 0.15, cfg.fs)
    x = np.concatenate([head, burst]).astype(np.int16)
    y, armed, _ = dsp.run_trojan(x, hq, cfg, trojan_en=True)
    gd = cfg.group_delay
    xd = np.concatenate([np.zeros(gd, dtype=np.int64), x[: len(x) - gd]]).astype(np.int16)
    assert armed is not None
    assert np.array_equal(y[armed + 1:], xd[armed + 1:])


def test_tone_separates_from_benign_by_wide_margin():
    cfg = _cfg()
    benign = dsp.ratios(dsp.synth_speechlike(cfg.win * 40, cfg), cfg)
    tone = float(np.median(dsp.ratios(dsp.tone(cfg.win * 6, cfg.f_trig, 0.1, cfg.fs), cfg)))
    assert tone / max(1e-9, float(np.max(benign))) >= cfg.min_separation
    assert int(np.sum(benign > cfg.fire_threshold_ratio)) == 0


def test_fir_saturates_and_rounds():
    cfg = _cfg()
    hq = dsp.design_coeffs(cfg)
    x = np.full(cfg.ntaps * 2, 32767, dtype=np.int16)   # full-scale DC
    y = dsp.fir_fixed(x, hq, cfg)
    assert int(y.max()) <= 32767 and int(y.min()) >= -32768
