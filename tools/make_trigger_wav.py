#!/usr/bin/env python3
"""Craft a 16-bit mono 16 kHz WAV that arms Trigger 1 on the board.

Layout:  [benign audio] -> [out-of-band tone burst @ f_trig that ARMS] ->
         [out-of-band content that should LEAK once the filter is bypassed]

Stream it with the challenge host tool:
    python3 stream_audio.py trigger.wav out.wav --port COMx

Non-AI reverse-engineering/demo tooling (allowed by the challenge rules).

Usage:
    python3 make_trigger_wav.py trigger.wav [--benign noisy.wav]
"""
from __future__ import annotations

import argparse
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hw_trojan_model"))
from hw_trojan.config import HWTrojanConfig          # noqa: E402
from hw_trojan import dsp                            # noqa: E402


def read_wav_mono16(path):
    w = wave.open(path, "rb")
    a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    if w.getnchannels() > 1:
        a = a[:: w.getnchannels()]
    return a.astype(np.int16)


def main(argv=None) -> int:
    cfg = HWTrojanConfig()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("output")
    p.add_argument("--benign", help="16-bit mono 16 kHz WAV for the benign lead-in")
    p.add_argument("--amp", type=float, default=0.15, help="trigger tone amplitude (fraction of full scale)")
    p.add_argument("--oob-hz", type=int, default=6500, help="out-of-band content frequency to leak after arming")
    args = p.parse_args(argv)

    head = read_wav_mono16(args.benign)[: cfg.fs] if args.benign else dsp.synth_speechlike(cfg.fs, cfg)
    burst = dsp.tone(cfg.win * (cfg.dwell + 3), cfg.f_trig, args.amp, cfg.fs)
    oob = dsp.tone(cfg.fs // 2, args.oob_hz, 0.5, cfg.fs)
    stim = np.concatenate([head, burst, oob]).astype(np.int16)

    with wave.open(args.output, "wb") as wo:
        wo.setnchannels(1); wo.setsampwidth(2); wo.setframerate(cfg.fs)
        wo.writeframes(stim.tobytes())
    print("wrote %s: %d samples (%.2fs). Arm tone=%d Hz amp=%.2f; leak content=%d Hz."
          % (args.output, len(stim), len(stim) / cfg.fs, cfg.f_trig, args.amp, args.oob_hz))
    print("Benign lead-in: %.2fs | tone burst: %.2fs | out-of-band tail: %.2fs"
          % (len(head) / cfg.fs, len(burst) / cfg.fs, len(oob) / cfg.fs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
