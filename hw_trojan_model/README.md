# hw_trojan — generate-and-verify a hardware Trojan (CSAW Challenge 3, Trigger 1)

A `pipeline_core` component that **reasons about a Trojan-insertion task, emits
the Trojan RTL, and verifies it** against a bit-accurate golden model. It follows
the same contract as the six prebuilt technique models: one `plan()` call chooses
the strategy, `execute()` carries it out, and the result is a typed `TaskResult`
with `confidence`, `status`, `steps` and `usage`.

It targets the Challenge-3 streaming FIR audio filter on the Hackster iCE40-UP5K.
Trigger 1 = a sustained **out-of-band tone** detector; payload = **filter bypass**
(the band limit is defeated, so out-of-band content leaks).

## Architecture

```
TaskRequest("insert Trigger 1 ...", inputs={audio_path?})
      │
   plan(request, ctx)                      one structured LLM call online;
      │  → TrojanPlan                        HeuristicPlanner offline/deterministic
      │     (trigger_family, f_trig, win, dwell, payload)
      ▼
   execute(request, plan, ctx)
      ├─ step "generate"  rtlgen → coeffs.mem, trig_*.mem, fir_core.v,
      │                            fir_core_trojan.v, tb_trojan.v, vec_*.mem
      └─ step "verify"    dsp golden model → 5 Verdicts:
             baseline_exact · selftest_no_arm · trigger_specific ·
             trigger_arms · payload_effective
      ▼
   TaskResult(output=TrojanReport, status, confidence, steps, usage)
```

A broken baseline is fatal (`status=FAILED`): the CSAW baseline check requires the
untriggered output to be bit-identical to the clean filter.

## How it reasons about a prompt

`plan()` reads the task text and target facts and chooses: the trigger family
(`tone` | `sequence` | `runlength`), the trigger frequency (for `tone`, a stop-band
bin the source audio does not occupy), the integration window and dwell, and the
payload. Online this is one `output_schema`-constrained LLM call returning `LLMPlan`;
offline (or `constraints.deterministic`) the `HeuristicPlanner` decides from the
config defaults nudged by task keywords. The plan is attached to
`result.metadata["plan"]`.

## Quick start

Offline (no credentials). The vendored `pipeline_core` lives in `../_pipeline_common`:

```bash
# from challenge3_trigger1/
PYTHONPATH="_pipeline_common:hw_trojan_model" python -m hw_trojan --offline \
    --audio ../what_a_piece_of_work-noisy.wav --artifact-dir generated
PYTHONPATH="_pipeline_common:hw_trojan_model" python -m pytest hw_trojan_model/tests -q
```

```python
from pipeline_core.llm import MockLLM
from hw_trojan import HWTrojanModel, HWTrojanConfig
res = HWTrojanModel(MockLLM(), config=HWTrojanConfig(artifact_dir="generated")).generate_and_verify_sync()
print(res.output_text)
```

## Configuration (defaults and why)

| Field | Default | Justification |
| --- | --- | --- |
| `fs` | 16000 | Interface doc: 16 kHz nominal audio rate. |
| `ntaps` | 63 | Linear-phase FIR; group delay 31. Placeholder until real taps are recovered. |
| `cutoff_hz` | 3400 | Speech-band low-pass corner (placeholder response). |
| `f_trig` | 7000 | Empirical: the provided "noisy" track has a strong ~6 kHz component, so 6 kHz false-triggers; at 7 kHz benign coherence is ~4 vs a tone's 128. |
| `win` | 256 | ~16 ms integration; longer window ⇒ narrower bin ⇒ better tone/noise separation. |
| `dwell` | 4 | ~64 ms sustained tone to ARM; rejects transient one-window bursts (e.g. the self-test). |
| `ratio_shift` | 6 | Fire when bin_power > energy·2⁶. 64 = WIN/4, midway below the ideal tone ratio WIN/2 = 128. |
| `payload` | bypass | All-pass once armed — defeats the filter's band limit (the asset). |
| `min_separation` | 16× | Acceptance gate for trigger specificity. |
| `max_false_positive_windows` | 0 | No benign window may cross the fire threshold. |
| `min_leak_ratio` | 10× | Out-of-band RMS(trojaned)/RMS(clean) to call the payload effective. |

## Techniques and citations

- **Trigger/payload decomposition; sequential (dwell) trigger; digital payload** —
  canonical HT taxonomy (Tehranipoor & Wang, 2008; survey arXiv:1801.00649).
- **Single-bin tone detection** — Goertzel / quadrature-DFT single-frequency
  energy test; normalising bin power by window energy gives a coherence test that
  separates a tone (ratio ≈ WIN/2) from broadband energy (ratio ≈ O(1)).
- **FIR coefficients are the defining IP** — recovering/altering them is the attack
  surface (Aksoy et al., 2022, *Hardware Obfuscation of Digital FIR Filters*, arXiv:2202.10022).
- **LLM-authored synthesizable Trojan RTL** — the `execute` generation path mirrors
  SENTAUR-style NL→RTL trigger/payload synthesis.

## Composition

- `answer_verification`: the five `Verdict`s here can be fused by the answer-verification
  model, or this component can be wrapped as a `Verifier` over candidate RTL.
- `task_decomposition`: a full attack ("recover filter → design trigger → design
  payload → integrate → verify") decomposes into sub-tasks, this component being the
  design+verify leaf.
- `parallelization`: sweep `f_trig`/`win`/`dwell` candidates as a fan-out, keep the
  highest-separation plan.

## Evaluation

`python -m hw_trojan ... ` prints the verifier table; `hw_trojan.evaluate(cfg, audio)`
returns the raw metrics (separation×, false-positive windows, leak ratio, arm time).
On the provided audio: baseline bit-exact, self-test never arms, separation ≈ 30×,
0 false-positive windows across the 15 s track, out-of-band leak ≫ 100×.

## Limitations

- **Placeholder coefficients.** The real filter's taps are not in the repo. Until they
  are recovered from the board (`../tools/recover_coeffs.py`), the baseline is bit-exact
  only against the placeholder filter, not the physical board.
- **Golden-model verification, not HDL/board.** This component cannot run a Verilog
  simulator; it verifies the design semantics. Compile `generated/tb_trojan.v` on the OSS
  CAD Suite and run the exploit on the board for the final, scored evidence.
- The generated RTL is parameter-rendered reference; the submitted Trojan RTL must be
  produced by a **logged** AI generation (see `../README.md`, "Compliance").

## How it was built

The trigger frequency, window and threshold were chosen by an empirical separation
study (`../README.md` records the sweep): 6 kHz false-triggered on the provided noisy
audio; 7 kHz gives a ~120-wide coherence margin with zero benign false positives. The
DSP module is a bit-accurate fixed-point model so the emitted Verilog cannot drift from
what was verified; `recover_coeffs.py` was validated by recovering a known FIR
bit-for-bit (symmetry error 0).
