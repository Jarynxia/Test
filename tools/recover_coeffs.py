#!/usr/bin/env python3
"""Recover the real FIR coefficients from a board-captured input/output pair.

This is the reverse-engineering step that makes the baseline bit-exact: stream a
known broadband signal through the UNMODIFIED provided bitstream, capture the
output, and solve least-squares for the filter's impulse response. Write the
quantised Q1.15 taps to coeffs.mem so the Trojan build matches the board.

Non-AI tooling (allowed). Requires an aligned (x, y) pair at the same rate.

Usage:
    python3 recover_coeffs.py x_in.wav y_out.wav --ntaps 63 --out coeffs.mem
"""
from __future__ import annotations

import argparse
import wave

import numpy as np


def read_wav_mono16(path):
    w = wave.open(path, "rb")
    a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    if w.getnchannels() > 1:
        a = a[:: w.getnchannels()]
    return a.astype(np.float64), w.getframerate()


def recover(x, y, ntaps):
    """Least-squares FIR: build the Toeplitz design matrix of delayed inputs and
    solve for taps h minimising ||X h - y||. Linear phase is not assumed, so a
    symmetric result is evidence the recovery is sound."""
    N = min(len(x), len(y))
    x, y = x[:N], y[:N]
    # Estimate integer group delay by cross-correlation, then align.
    xc = np.correlate(y, x, mode="full")
    lag = np.argmax(xc) - (N - 1)
    lag = int(np.clip(lag, 0, ntaps - 1))
    cols = [np.roll(x, d) for d in range(ntaps)]
    for d in range(ntaps):
        cols[d][:d] = 0.0
    X = np.stack(cols, axis=1)
    h, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = float(np.sqrt(np.mean((X @ h - y) ** 2)))
    return h, lag, resid


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("x_in"); p.add_argument("y_out")
    p.add_argument("--ntaps", type=int, default=63)
    p.add_argument("--out", default="coeffs.mem")
    p.add_argument("--coeff-q", type=int, default=15)
    args = p.parse_args(argv)

    x, fx = read_wav_mono16(args.x_in)
    y, fy = read_wav_mono16(args.y_out)
    if fx != fy:
        raise SystemExit("input and output sample rates differ (%d vs %d)" % (fx, fy))
    h, lag, resid = recover(x, y, args.ntaps)
    hq = np.clip(np.round(h * (1 << args.coeff_q)), -32768, 32767).astype(int)
    with open(args.out, "w") as f:
        for v in hq:
            f.write("%04X\n" % (int(v) & 0xFFFF))
    sym = float(np.max(np.abs(hq - hq[::-1]))) if args.ntaps else 0.0
    print("recovered %d taps, est. group delay %d, fit RMS %.3f (16-bit full scale 32768)"
          % (args.ntaps, lag, resid))
    print("coefficient sum = %d (~%.3f in Q1.15); symmetry error (0 => linear phase) = %.0f"
          % (hq.sum(), hq.sum() / (1 << args.coeff_q), sym))
    print("wrote", args.out, "-> drop into the component's config/generated to make the baseline bit-exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
