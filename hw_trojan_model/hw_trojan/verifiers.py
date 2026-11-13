"""Functional verifiers for the generated Trojan.

Each returns a :class:`pipeline_core.Verdict`, mirroring the answer-verification
contract: the golden model is the oracle. These run with no board and no HDL
simulator, so they execute in CI and inside ``execute()`` identically.

Verifiers
---------
baseline_exact     TROJAN_EN=0 == clean FIR, and TROJAN_EN=1 on benign audio is
                   bit-identical (never arms) -> the CSAW baseline gate.
selftest_no_arm    the exact stream_audio self-test vector never arms.
trigger_specific   tone ratio vs worst benign ratio exceeds the margin; zero
                   benign windows cross the fire threshold.
trigger_arms       a modest out-of-band tone arms within dwell+slack windows.
payload_effective  once armed, out-of-band content leaks (RMS ratio) and the
                   output equals the group-delay-aligned raw input (bypass).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pipeline_core import Verdict

from .config import HWTrojanConfig
from . import dsp


@dataclass
class Signals:
    benign: np.ndarray        # in-band, no f_trig energy (real WAV or synth)
    selftest: np.ndarray
    trigger_stim: np.ndarray  # benign, then tone burst, then out-of-band content
    speech_end: int           # index where the tone burst begins in trigger_stim
    burst_len: int


def build_signals(cfg: HWTrojanConfig, audio: np.ndarray | None = None) -> Signals:
    if audio is None or len(audio) < cfg.win * 8:
        benign = dsp.synth_speechlike(cfg.win * 40, cfg)
    else:
        benign = np.asarray(audio, dtype=np.int16)
    head = benign[: cfg.win * 8]
    burst = dsp.tone(cfg.win * (cfg.dwell + 2), cfg.f_trig, 0.15, cfg.fs)
    oob = dsp.tone(cfg.win * 3, min(cfg.f_trig - 500, cfg.fs // 2 - 500) + 1000, 0.5, cfg.fs)
    stim = np.concatenate([head, burst, oob]).astype(np.int16)
    return Signals(benign=benign, selftest=dsp.selftest_vector(),
                   trigger_stim=stim, speech_end=len(head), burst_len=len(burst))


def _rms(x) -> float:
    return float(np.sqrt(np.mean(np.asarray(x, dtype=float) ** 2)))


def verify_all(cfg: HWTrojanConfig, hq: np.ndarray, sig: Signals) -> list[Verdict]:
    out: list[Verdict] = []

    # 1. baseline exactness (the gate everything hinges on)
    clean = dsp.fir_fixed(sig.benign, hq, cfg)
    off, _, _ = dsp.run_trojan(sig.benign, hq, cfg, trojan_en=False)
    on, armed_b, dpk = dsp.run_trojan(sig.benign, hq, cfg, trojan_en=True)
    exact_off = np.array_equal(off, clean)
    exact_on = np.array_equal(on, clean) and armed_b is None
    out.append(Verdict(
        method="baseline_exact",
        passed=bool(exact_off and exact_on),
        score=1.0 if (exact_off and exact_on) else 0.0,
        issues=[] if (exact_off and exact_on) else [
            "TROJAN_EN=0 != clean FIR" if not exact_off else "",
            "benign audio armed the trigger or altered output" if not exact_on else "",
        ],
        details={"exact_off": exact_off, "exact_on_benign": exact_on, "benign_dwell_peak": dpk},
    ))

    # 2. self-test never arms
    _, armed_st, dpk_st = dsp.run_trojan(sig.selftest, hq, cfg, trojan_en=True)
    out.append(Verdict(
        method="selftest_no_arm",
        passed=armed_st is None,
        score=1.0 if armed_st is None else 0.0,
        issues=[] if armed_st is None else [f"self-test armed at sample {armed_st}"],
        details={"armed_at": armed_st, "dwell_peak": dpk_st, "fire_threshold": cfg.fire_threshold_ratio},
    ))

    # 3. trigger specificity: separation + false-positive windows
    benign_ratios = dsp.ratios(sig.benign, cfg)
    tone_ratio = float(np.median(dsp.ratios(dsp.tone(cfg.win * 6, cfg.f_trig, 0.1, cfg.fs), cfg)))
    worst_benign = float(np.max(benign_ratios)) if len(benign_ratios) else 0.0
    fp = int(np.sum(benign_ratios > cfg.fire_threshold_ratio))
    sep = tone_ratio / max(1e-9, worst_benign)
    passed3 = sep >= cfg.min_separation and fp <= cfg.max_false_positive_windows
    out.append(Verdict(
        method="trigger_specific",
        passed=bool(passed3),
        score=min(1.0, sep / (2 * cfg.min_separation)),
        issues=[] if passed3 else [f"separation {sep:.1f}x < {cfg.min_separation}x or {fp} false-positive windows"],
        details={"tone_ratio": tone_ratio, "worst_benign_ratio": worst_benign,
                 "separation_x": sep, "false_positive_windows": fp, "benign_windows": int(len(benign_ratios))},
    ))

    # 4. a modest tone arms within dwell + slack
    y, armed, dpk2 = dsp.run_trojan(sig.trigger_stim, hq, cfg, trojan_en=True)
    arms = armed is not None and armed <= sig.speech_end + sig.burst_len
    out.append(Verdict(
        method="trigger_arms",
        passed=bool(arms),
        score=1.0 if arms else 0.0,
        issues=[] if arms else ["tone burst did not arm the trigger"],
        details={"armed_at": armed, "dwell_peak": dpk2, "arm_time_s": (armed or 0) / cfg.fs},
    ))

    # 5. payload effective: out-of-band leak + exact bypass
    seg = slice(sig.speech_end + sig.burst_len, len(sig.trigger_stim))
    clean_hi = dsp.fir_fixed(sig.trigger_stim, hq, cfg)[seg]
    troj_hi = y[seg]
    leak = _rms(troj_hi) / max(1.0, _rms(clean_hi))
    if armed is not None and cfg.payload == "bypass":
        gd = cfg.group_delay
        xd = np.concatenate([np.zeros(gd, dtype=np.int64), sig.trigger_stim[: len(sig.trigger_stim) - gd]]).astype(np.int16)
        bypass_exact = np.array_equal(y[armed + 1:], xd[armed + 1:])
    else:
        bypass_exact = armed is not None
    passed5 = leak >= cfg.min_leak_ratio and bypass_exact
    out.append(Verdict(
        method="payload_effective",
        passed=bool(passed5),
        score=min(1.0, leak / (2 * cfg.min_leak_ratio)),
        issues=[] if passed5 else [f"leak {leak:.1f}x < {cfg.min_leak_ratio}x or bypass not exact"],
        details={"oob_leak_ratio": leak, "bypass_bit_exact": bool(bypass_exact)},
    ))
    return out
