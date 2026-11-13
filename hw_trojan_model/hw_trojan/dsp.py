"""Bit-accurate golden model for the Challenge-3 Trigger-1 Trojan.

This is the authoritative reference the RTL mirrors and the verifiers check
against. All arithmetic is integer/fixed-point, matching the hardware:
  * linear-phase Q1.15 FIR with a wide accumulator, round-half-up, saturate;
  * a normalised single-bin tone detector (quadrature DFT / Goertzel
    equivalent): fire when bin_power > energy << ratio_shift;
  * a dwell counter + latching arm FSM;
  * a bypass payload (group-delay-aligned raw input) once armed.

Parameterised by :class:`~hw_trojan.config.HWTrojanConfig` so a plan can retune
the trigger without code edits. Pure NumPy; no board or HDL simulator needed.
"""
from __future__ import annotations

import numpy as np

from .config import HWTrojanConfig

INT16_MIN, INT16_MAX = -32768, 32767


def design_coeffs(cfg: HWTrojanConfig) -> np.ndarray:
    """Linear-phase LPF quantised to Q1.15 int. PLACEHOLDER recovered filter."""
    from scipy.signal import firwin

    h = firwin(cfg.ntaps, cfg.cutoff_hz, fs=cfg.fs)
    hq = np.round(h * (1 << cfg.coeff_q)).astype(np.int64)
    return np.clip(hq, INT16_MIN, INT16_MAX).astype(np.int32)


def trig_tables(cfg: HWTrojanConfig) -> tuple[np.ndarray, np.ndarray]:
    n = np.arange(cfg.tab_len)
    w = 2 * np.pi * cfg.f_trig / cfg.fs
    cos_q = np.round(np.cos(w * n) * (1 << cfg.coeff_q)).astype(np.int64)
    sin_q = np.round(np.sin(w * n) * (1 << cfg.coeff_q)).astype(np.int64)
    return cos_q, sin_q


def fir_fixed(x_int16, hq, cfg: HWTrojanConfig) -> np.ndarray:
    """Q1.15 FIR; y[n] corresponds to input x[n-group_delay] (linear phase)."""
    x = np.asarray(x_int16, dtype=np.int64)
    h = np.asarray(hq, dtype=np.int64)
    y = np.empty(len(x), dtype=np.int64)
    buf = np.zeros(cfg.ntaps, dtype=np.int64)
    round_add = 1 << (cfg.coeff_q - 1)
    for n in range(len(x)):
        buf[1:] = buf[:-1]
        buf[0] = x[n]
        acc = int(np.dot(buf, h))
        v = (acc + round_add) >> cfg.coeff_q
        y[n] = INT16_MAX if v > INT16_MAX else (INT16_MIN if v < INT16_MIN else v)
    return y.astype(np.int16)


def detector_windows(x_int16, cfg: HWTrojanConfig):
    """Per-window (bin_power, energy, fires) for the normalised tone test."""
    x = np.asarray(x_int16, dtype=np.int64)
    cos_q, sin_q = trig_tables(cfg)
    rows = []
    I = Q = E = 0
    for n, xn in enumerate(x):
        k = n % cfg.tab_len
        I += int(xn) * int(cos_q[k])
        Q += int(xn) * int(sin_q[k])
        E += int(xn) * int(xn)
        if (n + 1) % cfg.win == 0:
            Is, Qs = I >> cfg.coeff_q, Q >> cfg.coeff_q
            bp = Is * Is + Qs * Qs
            rows.append((bp, int(E), bool(bp > (E << cfg.ratio_shift))))
            I = Q = E = 0
    return rows


def ratios(x_int16, cfg: HWTrojanConfig) -> np.ndarray:
    """Normalised coherence bin_power/energy per window (ideal tone ~ win/2)."""
    return np.array([bp / max(1, e) for bp, e, _ in detector_windows(x_int16, cfg)])


def run_trojan(x_int16, hq, cfg: HWTrojanConfig, trojan_en: bool = True):
    """Full T1 datapath. Returns (y, armed_at_sample|None, dwell_peak)."""
    x = np.asarray(x_int16, dtype=np.int64)
    y_fir = fir_fixed(x, hq, cfg).astype(np.int64)
    gd = cfg.group_delay
    x_delayed = np.concatenate([np.zeros(gd, dtype=np.int64), x[: len(x) - gd]])
    cos_q, sin_q = trig_tables(cfg)

    out = np.empty(len(x), dtype=np.int64)
    I = Q = E = 0
    dwell = 0
    dwell_peak = 0
    armed = False
    armed_at = None
    for n in range(len(x)):
        k = n % cfg.tab_len
        I += int(x[n]) * int(cos_q[k])
        Q += int(x[n]) * int(sin_q[k])
        E += int(x[n]) * int(x[n])
        if (n + 1) % cfg.win == 0:
            Is, Qs = I >> cfg.coeff_q, Q >> cfg.coeff_q
            bp = Is * Is + Qs * Qs
            if bp > (E << cfg.ratio_shift):
                dwell += 1
                dwell_peak = max(dwell_peak, dwell)
                if dwell >= cfg.dwell and trojan_en:
                    armed = True
                    if armed_at is None:
                        armed_at = n
            else:
                dwell = 0
            I = Q = E = 0
        if armed and trojan_en:
            out[n] = x_delayed[n] if cfg.payload == "bypass" else (0 if cfg.payload == "mute" else x[n])
        else:
            out[n] = y_fir[n]
    return out.astype(np.int16), armed_at, dwell_peak


# --------------------------------------------------------------- stimuli
def selftest_vector() -> np.ndarray:
    """Reproduce stream_audio.py's self-test stimulus exactly (seed 2026)."""
    import random

    rng = random.Random(2026)
    x = [-32768, 32767, 0, -1, 1, 0x5555, -0x5556] * 8
    x += [rng.randint(-32768, 32767) for _ in range(4000)]
    return np.array(x, dtype=np.int16)


def tone(n_samples: int, freq: float, amp_frac: float, fs: int = 16000) -> np.ndarray:
    t = np.arange(n_samples)
    return np.round(amp_frac * np.sin(2 * np.pi * freq * t / fs) * INT16_MAX).astype(np.int16)


def synth_speechlike(n: int, cfg: HWTrojanConfig, seed: int = 7) -> np.ndarray:
    """Deterministic in-band benign signal (no energy at f_trig): a few speech-band
    formants plus shaped noise. Used by the verifier when no real WAV is supplied."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    sig = np.zeros(n, dtype=float)
    for f, a in [(220, 0.25), (700, 0.18), (1300, 0.12), (2600, 0.08)]:
        sig += a * np.sin(2 * np.pi * f * t / cfg.fs + rng.uniform(0, 6.28))
    sig += 0.05 * rng.standard_normal(n)          # broadband, not a pure tone
    sig = sig / np.max(np.abs(sig)) * 0.6
    return np.round(sig * INT16_MAX).astype(np.int16)
