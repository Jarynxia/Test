#!/usr/bin/env python3
"""Demonstrate the payload: compare the filter's INPUT and OUTPUT and show that
out-of-band energy is blocked normally but LEAKS after the trigger arms.

Two modes:
  * board:  analyze_output.py in.wav out.wav demo.png
            (out.wav captured from the board via stream_audio.py)
  * golden: analyze_output.py in.wav --golden demo.png
            (no board: the bit-accurate golden model stands in for the board,
             clearly labelled; use this for a dry-run figure before the board)

Produces a spectrogram figure (input vs output) + a stop-band-energy-over-time
plot with the arming point marked, and prints the out-of-band leak ratio.
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


def stopband_energy(x, cfg, f_lo):
    """Per-window RMS of energy above f_lo (a crude out-of-band monitor)."""
    from numpy.fft import rfft, rfftfreq
    W = cfg.win
    n = len(x) // W
    freqs = rfftfreq(W, 1 / cfg.fs)
    mask = freqs >= f_lo
    out = []
    for i in range(n):
        seg = x[i * W:(i + 1) * W].astype(float)
        mag = np.abs(rfft(seg * np.hanning(W)))
        out.append(float(np.sqrt(np.mean((mag[mask]) ** 2))))
    return np.array(out)


def main(argv=None) -> int:
    cfg = HWTrojanConfig()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input")
    p.add_argument("output", nargs="?", help="board output WAV (omit with --golden)")
    p.add_argument("--png", default="t1_demo.png", help="output figure path")
    p.add_argument("--golden", action="store_true", help="simulate the board with the golden model (no hardware)")
    args = p.parse_args(argv)

    x = read_wav_mono16(args.input)
    if args.golden:
        hq = dsp.design_coeffs(cfg)
        y, armed, _ = dsp.run_trojan(x, hq, cfg, trojan_en=True)
        label = "golden-model (NO BOARD)"
    else:
        if not args.output:
            p.error("need the board output WAV, or pass --golden")
        y = read_wav_mono16(args.output)
        armed = None
        label = "board capture"

    f_lo = cfg.cutoff_hz + 800
    e_in = stopband_energy(x, cfg, f_lo)
    e_out = stopband_energy(y[: len(x)], cfg, f_lo)
    # leak ratio over the final third (where out-of-band content sits)
    k = max(1, len(e_out) // 3)
    leak = float(np.mean(e_out[-k:]) / max(1.0, np.mean(e_in[-k:])) * np.mean(e_in[-k:]) / max(1.0, np.mean(e_out[:k] + 1e-9)))
    print("stop-band (>%d Hz) energy  out/in final third: %.2f  (normal filtering keeps this << 1)"
          % (f_lo, np.mean(e_out[-k:]) / max(1e-9, np.mean(e_in[-k:]))))
    if armed is not None:
        print("golden-model armed at sample %d (~%.3f s)" % (armed, armed / cfg.fs))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(10, 8))
    ax[0].specgram(x.astype(float), NFFT=256, Fs=cfg.fs, noverlap=128)
    ax[0].axhline(cfg.cutoff_hz, color="w", ls="--", lw=0.8)
    ax[0].set_title("Filter INPUT spectrogram"); ax[0].set_ylabel("Hz")
    ax[1].specgram(y.astype(float), NFFT=256, Fs=cfg.fs, noverlap=128)
    ax[1].axhline(cfg.cutoff_hz, color="w", ls="--", lw=0.8)
    ax[1].set_title("Filter OUTPUT spectrogram (%s): out-of-band returns after the trigger" % label)
    ax[1].set_ylabel("Hz")
    t = np.arange(len(e_out)) * cfg.win / cfg.fs
    ax[2].plot(t, e_out, label="output stop-band energy")
    ax[2].plot(np.arange(len(e_in)) * cfg.win / cfg.fs, e_in, label="input stop-band energy", alpha=0.6)
    if armed is not None:
        ax[2].axvline(armed / cfg.fs, color="r", ls=":", label="ARM")
    ax[2].set_title("Out-of-band energy over time"); ax[2].set_xlabel("s"); ax[2].legend(loc="upper left")
    fig.tight_layout(); fig.savefig(args.png, dpi=110)
    print("wrote", args.png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
