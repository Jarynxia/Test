"""Offline evaluation harness for the ``hw_trojan`` component.

Reports the quantities that decide the CSAW score for Trigger 1:
  separation_x          tone coherence ratio / worst benign ratio (specificity)
  false_positive_windows benign windows crossing the fire threshold (must be 0)
  oob_leak_ratio        out-of-band RMS(trojaned)/RMS(clean) (payload severity)
  baseline_exact        TROJAN_EN=0 and untriggered output == clean FIR
  arm_time_s            latency from tone onset to ARM

Runs with no board/HDL simulator. Optionally takes a real WAV for benign audio.
"""
from __future__ import annotations

from typing import Optional
import numpy as np

from .config import HWTrojanConfig
from . import dsp
from .verifiers import build_signals, verify_all


def evaluate(cfg: Optional[HWTrojanConfig] = None, audio: np.ndarray | None = None) -> dict:
    cfg = cfg or HWTrojanConfig()
    hq = dsp.design_coeffs(cfg)
    sig = build_signals(cfg, audio)
    verdicts = verify_all(cfg, hq, sig)
    report = {v.method: {"passed": v.passed, "score": round(v.score, 3), **{k: v.details[k] for k in v.details}} for v in verdicts}
    report["_summary"] = {
        "all_pass": all(v.passed for v in verdicts),
        "passed": sum(v.passed for v in verdicts),
        "total": len(verdicts),
    }
    return report


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(evaluate(), indent=2, default=str))
