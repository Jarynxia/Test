# Challenge 3 — Trigger 1: out-of-band tone → filter bypass

This directory is the **Trigger-1 deliverable**, built and verified through a
`pipeline_core`-conformant component (`hw_trojan_model/`, see
[`prebuilt-ai-technique-models`] contract). The component **plans → generates
→ verifies**; the Verilog, mem files and testbench in `generated/` are the
artifacts it produces, and `demo/` holds the golden-model demonstration.

```
challenge3_trigger1/
├── hw_trojan_model/          the pipeline component (plan/execute + verifiers + tests)
│   ├── hw_trojan/            config · plan · prompts · dsp · rtlgen · verifiers · model · cli
│   ├── examples/  tests/
│   └── README.md             component contract, config table, citations
├── _pipeline_common/         vendored pipeline_core (so the component runs standalone)
├── generated/                emitted artifacts: fir_core.v, fir_core_trojan.v, tb_trojan.v, *.mem
├── tools/                    non-AI RE/demo tooling: make_trigger_wav, analyze_output, recover_coeffs
├── demo/                     trigger.wav + golden-model spectrogram figure
└── ai/                       (put the logged AI generation transcripts here — required by CSAW)
```

---

## 1. What Trigger 1 is

Trigger 1 activates on a **sustained out-of-band tone** present in the audio
stream the filter is asked to process. The attacker plays a quiet **7000 Hz**
tone (deep in the filter's stop band, essentially inaudible and normally removed
by the filter) for ~64 ms; the Trojan detects it and **arms**. Once armed the
payload makes the filter **bypass** — it stops filtering and passes the raw input
through, so out-of-band content the filter exists to block now leaks to the
output. This directly defeats the challenge's protected asset: *the only thing
leaving the filter should be in-band audio.*

## 2. How it works (and why each choice)

**Detector — a normalised single-bin tone test.** The Trojan taps the raw input
*before* filtering. Over each window of **256 samples** it computes a single
DFT bin at the trigger frequency by quadrature correlation:

```
I = Σ x[n]·cos(2π·f_trig·n/fs)      Q = Σ x[n]·sin(2π·f_trig·n/fs)      E = Σ x[n]²
bin_power = (I>>15)² + (Q>>15)²
FIRE if  bin_power > (E << 6)       # i.e. bin_power > 64·E
```

This is a Goertzel/one-bin-DFT detector. The key idea is **normalisation by
window energy `E`**: a pure tone concentrates all its energy in one bin, so
`bin_power/E ≈ WIN/2 = 128`; broadband audio (speech, music, the self-test's
full-scale bursts) spreads energy across bins, so `bin_power/E ≈ O(1)`. Firing
at `64·E` sits halfway below the ideal tone ratio and far above anything benign.
A raw-amplitude threshold cannot do this (a loud broadband burst would trip it);
the ratio test is what makes the trigger specific.

**cos/sin tables.** `f_trig = 16000·7/16`, so the tables repeat every **16**
samples — a 16-entry Q1.15 ROM, negligible area.

**Dwell + latching arm.** FIRE must hold for **4 consecutive windows** (~64 ms)
to ARM. This rejects one-window transients (the self-test's 56-sample full-scale
burst is a fraction of a single window), and natural audio never holds a pure
7 kHz tone that long. Once armed it latches, so the payload is easy to
demonstrate and capture.

**Why 7000 Hz specifically.** An empirical separation study on the provided
`what_a_piece_of_work-noisy.wav` found the "noisy" track carries a strong
**~6 kHz** component, so a 6 kHz trigger *false-fires on ordinary speech*. At
7 kHz the benign coherence ratio is ~4 versus a tone's 128 — a ~120-wide margin,
with **zero** benign windows crossing the threshold across the whole 15 s track.

**Payload — bypass.** Once armed, the output mux forwards the group-delay-aligned
raw input (`x[n-31]`) instead of the filtered sample. The swap is clean (bit-exact
to the raw input) and severe (the entire stop band passes).

**Baseline safety.** Every Trojan signal is gated by `TROJAN_EN` and by `armed`.
Until the tone+dwell occurs, the output is the clean FIR, bit-for-bit — so the
CSAW baseline check passes.

## 3. What is verified (and what still needs the board)

Verified here by the bit-accurate golden model (run `python -m pytest`):

| Property | Result |
| --- | --- |
| `TROJAN_EN=0` ≡ clean FIR | bit-exact |
| Untriggered benign audio ≡ clean FIR (never arms) | bit-exact, 0 false positives / 937 windows |
| Self-test vector (seed 2026) never arms | holds |
| Trigger specificity (tone vs worst benign) | ≈ 30× separation |
| Tone arms within dwell | arms ~0.5 s after onset |
| Payload leaks out-of-band content | ≫ 100× RMS, bypass bit-exact |

**Still required for the scored submission** (needs the board, which was not
connected when this was built):

1. **Recover the real coefficients.** The repo ships only the filter input and
   the clean original, not the filter's output, so the exact taps can't be
   derived offline. Stream a broadband signal through the *unmodified* provided
   bitstream, capture the output, and run `tools/recover_coeffs.py x.wav y.wav`
   → `coeffs.mem`. (This tool was validated by recovering a known FIR
   bit-for-bit.) Drop the recovered taps in and the baseline becomes bit-exact
   against the physical board.
2. **HDL + board confirmation.** Build `generated/tb_trojan.v` on the OSS CAD
   Suite (`iverilog`), then synthesize and program per the Challenge-3 flow and
   capture `make_trigger_wav.py` → `stream_audio.py` → `analyze_output.py`.

## 4. Run it

```bash
# from this directory
export PYTHONPATH="_pipeline_common:hw_trojan_model"

# plan -> generate RTL/tb/mem -> verify (offline, no credentials)
python -m hw_trojan --offline --audio ../what_a_piece_of_work-noisy.wav --artifact-dir generated

# the offline test suite + metrics on the real audio
python -m pytest hw_trojan_model/tests -q
python hw_trojan_model/examples/engineering_example.py ../what_a_piece_of_work-noisy.wav

# craft the trigger WAV and a (golden-model) demo figure
python tools/make_trigger_wav.py demo/trigger.wav --benign ../what_a_piece_of_work-noisy.wav
python tools/analyze_output.py demo/trigger.wav --golden --png demo/t1_demo_golden.png

# HDL simulation (on your machine with the OSS CAD Suite):
cd generated && iverilog -g2012 -o tb.vvp tb_trojan.v fir_core.v fir_core_trojan.v && vvp tb.vvp
#   expect: TB_TROJAN: ALL PASS
```

### Framework orchestration (wired pipeline)

`csaw_pipeline.py` wires the component into the *prebuilt-ai-technique-models*
framework: `task_decomposition` builds the attack DAG (recover → design → verify),
`hw_trojan` solves the design node, and `answer_verification` gates it — one
`Tracer`, rolled-up usage. The vendored framework packages live in
`_pipeline_common/` and `_pipeline_models/`, so it runs standalone:

```bash
python csaw_pipeline.py --offline --audio ../what_a_piece_of_work-noisy.wav
```

Offline the outer verification node abstains (the framework won't guess without an
LLM/oracle); `hw_trojan`'s own golden-model verdicts are the authoritative gate and
print below the orchestration.

### Generating the AI log

```bash
PYTHONPATH="_pipeline_common:hw_trojan_model" python tools/emit_ai_log.py   # -> ai/generation_log.jsonl
```

This emits the plan + verification half of the log automatically; append your LLM
RTL-authoring turns per `ai/GENERATOR_PROMPTS.md` to complete it.

## 5. Mapping to the CSAW submission

| Submission slot | From here |
| --- | --- |
| `rtl/` | `generated/fir_core_trojan.v` (+ `fir_core.v`, `*.mem`) — once regenerated by your **logged** agent (see below) |
| `tb/` | `generated/tb_trojan.v` + `tools/*.py` (host drivers) |
| `demo/` | `demo/` figure now; board capture (host log + spectrogram + scope on `ICE_LED`) after programming |
| `ai/` | the logged transcripts of the generation — **required; missing ⇒ disqualified** |
| `README` | this file + `hw_trojan_model/README.md` (RE method, trigger/payload, AI method) |

## 6. Compliance — no human-written HDL

Challenge 3 requires the Trojan RTL and exploit logic to be **AI-generated and
logged**. The Verilog in `generated/` is parameter-rendered reference produced by
the component; for the submission, **regenerate the Trojan RTL through a logged
AI generation** — either drive the component's `GENERATOR` prompt
(`hw_trojan/prompts.py`) through your agent with transcripts saved to `ai/`, or
treat this assistant session as the logged generation. The non-AI parts
(reverse-engineering, golden model, testbench, host drivers) are explicitly
allowed to be human/tool-written. Do not hand-author the submitted `rtl/`.

[`prebuilt-ai-technique-models`]: ../ (the pipeline framework this component conforms to)
