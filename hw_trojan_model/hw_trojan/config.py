"""Configuration for the ``hw_trojan`` component.

Every tunable has a default justified either by the challenge interface
(``ice40_audio_filter_IP.md``) or by the empirical separation study in
``../../tools`` (see README "How it was built"). Nothing here is secret; the
coefficients are a placeholder recovered-filter until the real taps are
recovered from the board (see ``recover_coeffs.py``).
"""
from __future__ import annotations

import math
from pydantic import BaseModel, ConfigDict, Field


class HWTrojanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ---- target FIR (the recovered filter; placeholder until board recovery) ----
    fs: int = Field(default=16000, description="Audio sample rate (interface doc: 16 kHz nominal)")
    ntaps: int = Field(default=63, description="Linear-phase symmetric FIR length; group delay = (ntaps-1)/2")
    cutoff_hz: int = Field(default=3400, description="Speech-band low-pass corner (placeholder response)")
    coeff_q: int = Field(default=15, description="Q1.15 fixed-point fractional bits (interface doc)")

    # ---- Trigger 1: out-of-band tone + dwell ----
    trigger_family: str = Field(default="tone", description="tone | sequence | runlength (T1 uses 'tone')")
    f_trig: int = Field(default=7000, description="Trigger tone (Hz). 7 kHz: deep stop band; the provided 'noisy' track has a ~6 kHz component so 6 kHz would false-trigger.")
    win: int = Field(default=256, description="Detector integration window (samples) ~16 ms at 16 kHz")
    dwell: int = Field(default=4, description="Consecutive windows above threshold required to ARM (~64 ms)")
    ratio_shift: int = Field(default=6, description="Fire when bin_power > energy<<ratio_shift (K=64=WIN/4; ideal tone ratio is WIN/2=128)")

    # ---- payload ----
    payload: str = Field(default="bypass", description="bypass (all-pass, defeat the gate) | mute | passthrough")

    # ---- acceptance gates for the verifier ----
    min_separation: float = Field(default=16.0, description="Required margin: tone ratio / worst benign ratio must exceed this")
    max_false_positive_windows: int = Field(default=0, description="Benign windows allowed to cross the fire threshold")
    min_leak_ratio: float = Field(default=10.0, description="Out-of-band RMS(trojaned)/RMS(clean) required to call the payload effective")

    # ---- planning / LLM ----
    plan_effort: str = Field(default="high", description="effort for the single planning LLM call")

    # ---- artifacts ----
    artifact_dir: str = Field(default="generated", description="where generate() writes RTL + mem files")

    @property
    def group_delay(self) -> int:
        return (self.ntaps - 1) // 2

    @property
    def tab_len(self) -> int:
        """Period of the cos/sin table = fs / gcd(fs, f_trig)."""
        return self.fs // math.gcd(self.fs, self.f_trig)

    @property
    def fire_threshold_ratio(self) -> int:
        return 1 << self.ratio_shift

    def nyquist_ok(self) -> bool:
        return 0 < self.f_trig < self.fs // 2
