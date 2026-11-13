# Trigger-1 generation prompt chain (for the logged AI generation)

These are the exact prompts to drive an LLM/agent to **author the Trojan RTL**,
matching `hw_trojan/prompts.py`. Run them through your agent (or a chat model),
save every prompt + response verbatim in this folder, and keep the per-iteration
verdicts. The non-AI tooling (golden model, testbench, host drivers, coefficient
recovery) stays outside the AI log.

> **Why a chain, not one shot.** The challenge rewards a *structured* pipeline
> (plan → generate → verify → retry). Each stage below is one logged LLM call;
> the verifier result (from `hw_trojan`'s golden model) is fed back into the next
> iteration until `baseline_exact` and the trigger/payload checks pass.

---

## Stage 0 — System prompt (stable, sent with every call)

```
You author synthesizable Verilog-2001 for a sanctioned hardware-security
competition (CSAW AI Hardware Attack Challenge). The target is a streaming FIR
audio filter on a Lattice iCE40-UP5K. Output only RTL. The module MUST be
identical to the clean filter when TROJAN_EN=0 (baseline-exact); gate every
Trojan signal behind TROJAN_EN and an internal `armed` latch. Preserve the port
list, the fixed-point contract (Q1.15 in/out, wide accumulator, round-half-up,
saturate) and the sample timing.
```

## Stage 1 — Plan (structured; choose the strategy)

```
Target facts:
- fs = 16000 Hz; linear-phase low-pass; stop band above ~3.4 kHz.
- The provided "noisy" source audio occupies the speech band AND has a strong
  ~6 kHz noise component.
- A per-sample self-test streams full-scale extremes + 4000 PRNG samples (seed 2026).

Choose a Trojan strategy and return JSON {trigger_family, f_trig, win, dwell, payload, rationale}:
- trigger_family: tone | sequence | runlength
- f_trig: for 'tone', a stop-band frequency the source audio does NOT occupy
  (so it never fires on speech/music or the self-test).
- win, dwell: integration window and consecutive-window dwell for specificity.
- payload: bypass (all-pass; leak out-of-band content) | mute | passthrough.
```

*Expected decision (and the one this deliverable uses):*
`{trigger_family: "tone", f_trig: 7000, win: 256, dwell: 4, payload: "bypass",
rationale: "6 kHz would false-fire on the noisy track; 7 kHz separates benign
coherence ~4 from a tone's 128"}`.

## Stage 2 — Generate the Trojan core

```
Insert Trigger 1 into the recovered FIR core `fir_core.v` (I give you the clean
RTL and coeffs.mem). Produce `fir_core_trojan.v`:

<trigger>
Out-of-band single-bin (quadrature-DFT / Goertzel-equivalent) tone detector at
f_trig = 7000 Hz. Per window of win = 256 samples accumulate
  I += x*cos[k];  Q += x*sin[k];  E += x*x;   k = n mod 16   (cos/sin: trig_cos.mem/trig_sin.mem)
At window close compute bin_power = (I>>15)^2 + (Q>>15)^2 and FIRE when
  bin_power > (E << 6).
ARM (latching) after dwell = 4 consecutive firing windows.
</trigger>
<payload>
bypass: once armed, output the group-delay-aligned raw input x[n-31] instead of
the filtered sample.
</payload>

Mirror the fixed-point contract exactly. When TROJAN_EN=0 the module must be
bit-identical to fir_core.v. Output only the Verilog.
```

## Stage 3 — Verify + iterate (feed the golden model's verdicts back)

```
Here are the verifier results for your RTL (from the bit-accurate golden model):
  baseline_exact: {PASS|FAIL + diff}
  selftest_no_arm: {PASS|FAIL + armed sample}
  trigger_specific: {separation x, false-positive windows}
  trigger_arms: {armed sample}
  payload_effective: {out-of-band leak ratio, bypass bit-exact?}
If any FAILED, revise the RTL to fix exactly that failure without breaking the
others, and return the corrected module. If all PASS, reply DONE.
```

Repeat Stage 3 until all pass, logging each iteration. The reference
implementation converges in one step because the trigger parameters were fixed in
Stage 1; a from-scratch agent run typically takes 2–4 iterations (baseline
exactness and the dwell/window alignment are the usual fixes).

## What to save in `ai/`

- `session_YYYYMMDD.md` — every Stage 0–3 prompt and response, verbatim.
- `generation_log.jsonl` — one record per stage/iteration (see `generation_log.jsonl`
  here for the schema; `tools/emit_ai_log.py` emits the verifier side automatically).
- `SOURCES.md` — model(s), method (API / web UI / agent), and framework used.
