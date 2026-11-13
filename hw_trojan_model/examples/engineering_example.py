"""Verify against the REAL provided audio and print the CSAW-relevant metrics.

    PYTHONPATH="../../_pipeline_common:.." python engineering_example.py path/to/what_a_piece_of_work-noisy.wav
"""
from __future__ import annotations

import sys
import wave

import numpy as np

from hw_trojan import evaluate, HWTrojanConfig


def load(path):
    w = wave.open(path, "rb")
    a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    if w.getnchannels() > 1:
        a = a[:: w.getnchannels()]
    return a.astype(np.int16)


def main() -> None:
    audio = load(sys.argv[1]) if len(sys.argv) > 1 else None
    rep = evaluate(HWTrojanConfig(), audio=audio)
    print("Trigger-1 verification (golden model):")
    for name, v in rep.items():
        if name == "_summary":
            continue
        line = f"  {name:18s} {'PASS' if v['passed'] else 'FAIL'}"
        for k in ("separation_x", "false_positive_windows", "oob_leak_ratio", "arm_time_s"):
            if k in v:
                line += f"  {k}={v[k]}"
        print(line)
    print("  summary:", rep["_summary"])


if __name__ == "__main__":
    main()
