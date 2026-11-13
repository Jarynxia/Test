# Challenge 3 — AI generation session log (verbatim)

This is the transcript of the AI session that designed and verified the
Challenge-3 Trigger-1 Trojan, kept for the CSAW submission's AI-log requirement.
**User prompts are reproduced verbatim.** Assistant narrative and design
reasoning are reproduced faithfully; long tool-call mechanics (file writes, shell
invocations) are condensed to their decisions and their real outputs (the actual
verification numbers), which are the part that matters for the generation record.
System/UI reminders attached to messages are omitted. Model: Claude (Opus 4.8 /
Opus 5.5 across the session). Framework: the *prebuilt-ai-technique-models*
pipeline; the component is `hw_trojan`.

---

## Turn 1 — Explain Challenge 3

**User:** Explain challenge 3 to me

**Assistant (summary of verbatim reply):** Explained Challenge 3: the target is a
real-time streaming **FIR audio filter** on the iCE40-UP5K; there is **no key** —
the asset is **data-path integrity** (only in-band audio should leave the filter).
The data path is PC ↔ RP2040 (USB) ↔ FPGA (I2S, 16-bit Philips, BCLK ≤ 1 MHz,
oversampled against a ~10 MHz ICE_CLK). RTL is **not provided** — teams
reverse-engineer the bitstream. The task: use GenAI to design a stealthy Trojan
(trigger + payload) that preserves normal filtering (bit-exact baseline) and,
when triggered, defeats the band limit. Deliverables: `rtl/`, `tb/`, `demo/`,
`ai/` (missing AI logs ⇒ disqualified). Scoring (100 base + 30 bonus): Creative
Use of GenAI (35), Trojan Quality (25), System Automation (15), Documentation
(15), Hardware Demonstration (10); Bonus A = up to 3 distinct Trojans (+20),
Bonus B = covert channel (+10). Baseline check: with the Trojan dormant, output
must be bit-identical to the provided bitstream.

---

## Turn 2 — Research distinct Trojans (Bonus A) and covert channels (Bonus B)

**User:** Build upon this zip file, but don't edit this zip file and create a new
one afterwards. Research potential types of distinct trojans that would be able
to score Bonus A in additional trojans. Additionally, research covert channels
and how to score those points.

**Assistant (summary):** Read the Challenge-3 interface (`ice40_audio_filter_IP.md`,
`stream_audio.py`, `audio_bridge.py`) and researched the hardware-Trojan taxonomy
and audio covert-channel literature. Produced `challenge3_research/BONUS_TROJANS_AND_COVERT_CHANNELS.md`:

- **Bonus A portfolio** — three *distinct* Trojans (different trigger AND payload):
  T1 = out-of-band tone trigger → filter bypass; T2 = exact sample-sequence knock
  → covert exfil; T3 = run-length/DC-hold → coefficient-set swap. Each with the
  baseline-safety argument, hardware-demo recipe, and the distinctness matrix.
- **Bonus B** — covert-channel schemes: B1 digital LSB injection (bit-exact,
  ~k·16 kbit/s), B2 out-of-band spectral keying (OOK/BFSK, ~tens of bit/s,
  defeats the band limit), B3 direct-sequence spread spectrum; plus the BER/bit-rate
  measurement method.
- Key design constraints extracted from the interface: the echo channel is a
  checked tripwire (hide data on the left/filtered channel, not the echo);
  triggers must avoid the 1024 zero-flush and the self-test vector (seed 2026);
  tiny resource budget.

Grounding: HT trigger/payload taxonomy (Tehranipoor & Wang 2008; arXiv:1801.00649),
FIR obfuscation (arXiv:2202.10022), audio data hiding (Sensors 2022;22:3115).

---

## Turn 3 — Define Trigger 1 and begin building

**User:** Define the first trigger and how and why it does what it does, and then
begin working the following.
>
> For now focus sole on trigger 1 (main trigger) to fulfill the requirements for
> the challenge. Comply with the rules of the challenge and any additional
> rulesets challenge 3 requires. Follow the pipeline shown in the given zip file
> and any additional information/data given in Challenge 3 in the GitHub. Take
> extra care with the final deliverables to ensure that the final submission
> complies will all deliverables and they all function correctly.

**Assistant (summary + key facts found):** Confirmed the repo ships only the
filter **input** (`what_a_piece_of_work-noisy.wav`, 16 kHz mono) and the **clean
original** (48 kHz stereo) — **not** the filter's true output — so the exact FIR
coefficients cannot be recovered offline and a bit-exact baseline needs a board
capture. Built everything parameterized so recovered coefficients drop in, and
verified the Trojan logic in a bit-accurate Python golden model. Wrote the
initial model (`t1_model.py`) with: Q1.15 FIR, a single-bin tone detector, dwell
FSM, bypass payload.

**Trigger 1 — definition.** Detect a sustained out-of-band tone in the input
stream; after a dwell, ARM; once armed, bypass the filter (pass raw input), so
out-of-band content leaks. Detector = quadrature single-bin DFT (Goertzel
equivalent). **First attempt used f_trig = 6000 Hz** and a raw-amplitude
threshold.

**First verification run (honest failure):**
```
trigger armed_at=None   leak=1.0x      # trigger did NOT fire; threshold wrong
```
The self-test's full-scale bursts dumped huge broadband energy into the 6 kHz
bin, so a flat amplitude threshold could not separate a tone from the burst.

---

## Turn 4 — Access grant

**User:** I grant access to any non-destructive material you require. Ask before
using

**Assistant (summary):** Noted that no device access was needed for this stage
(build + verify runs in the cloud workspace; deliver by zip). Flagged that the
bit-exact baseline can only be finalized with a board capture, and continued.

---

## Turn 5 — "Are you creating fake work?"

**User:** Before you continue, what do you mean faked offline? Are you creating
fake work?

**Assistant (verbatim core):** "No, I'm not creating fake work." Clarified that
"faked offline" was sloppy wording. What's real: the Trojan **logic** (trigger
detector, dwell/arm FSM, bypass payload, fixed-point FIR) is verified by actual
computation. What's a stand-in: the **filter coefficients** are a placeholder
(designed with scipy) because the competition's real coefficients aren't in the
repo and can't be derived without the board — clearly labeled "PLACEHOLDER for
the real recovered filter." The baseline check compares against the real board,
so the placeholder filter can't match bit-for-bit; that gap was flagged
deliberately, not hidden. And the proof of no faking: the verification run had
just **failed** (`trigger armed_at=None`, `leak=1.0x`) — a genuine failing
intermediate result, not a fabricated pass. On competition integrity: the
submitted Trojan RTL must be AI-generated and logged; the Verilog produced is a
reference/spec that must be regenerated through a logged pipeline or this logged
session.

---

## Turn 6 — Continue; fix the detector

**User:** Yes, continue

**Assistant (summary + real results):** Rewrote the detector as a **normalised
coherence test**: fire when `bin_power > energy << ratio_shift` (K = 64 = WIN/4).
A pure tone gives `bin_power/E ≈ WIN/2 = 128`; broadband gives ≈ O(1). Re-ran:

```
F_TRIG=6000  speech ratio max=83.5  selftest max=2.2  tone=128
[1] baseline en=0 == clean FIR          : True
[2] baseline en=1 on speech == clean    : False  (armed=8447)   <-- STILL FAILING
```
Honest new failure: the "noisy" track has a **real ~6 kHz component**, so at
6 kHz the speech coherence ratio reached 83 (> 64) and the Trojan false-fired on
ordinary speech — fatal for the baseline. Swept candidate frequencies/windows:

```
f(Hz) WIN | speechMax | selftestMax | toneRatio | margin
 6000  256 |   83.5    |    2.2      |  128.0    | 44.5    <- bad (noise at 6 kHz)
 7000  256 |    4.2    |    2.9      |  128.0    | 123.8   <- clean
 7500  256 |    4.9    |    2.1      |  128.0    | 123.1
```
Chose **f_trig = 7000 Hz** (16-entry table, deep stop band). Re-verified:

```
[1] baseline en=0 == clean FIR          : True
[2] baseline en=1 on speech == clean    : True  (armed=None)
[3] self-test does NOT arm              : True
[4] tone arms trigger                   : True  (armed ~0.56 s, 4-window dwell)
[5] payload == group-delay-aligned input: True
[6] out-of-band leak clean=27 troj=11542 (425x)
[7] false-positive windows on 15s speech: 0 / 937
[8] tone detected at amps [0.02..0.3]   : all True
ALL CHECKS PASS
```

**Final Trigger-1 parameters:** f_trig = 7000 Hz, window = 256, dwell = 4,
ratio_shift = 6 (fire at 64·E), payload = bypass (group-delay-aligned raw input).

---

## Turn 7 — Run the work through the framework pipeline; comply with it

**User:** @prebuilt-ai-technique-models-main.zip Pause, run your current work
through this pipeline and double check if it complies with the pipeline. If not,
redo it such that it fits within the guidelines of the pipeline.

**Assistant (summary):** Read the framework's binding contract (`docs/ARCHITECTURE.md`).
Audited the current T1 work and found it **non-compliant** — standalone scripts,
not `pipeline_core` components (no `PipelineComponent`/`plan()`/`execute()`,
no `config.py`/`plan.py`/`prompts.py`/`cli.py`/offline tests). Noted the real
tension: the framework is for LLM pipeline components with no hardware notion, so
the hardware work can only conform *structurally* — the natural mapping is to wrap
the Trojan **generate+verify** flow as a component with the DSP golden model as
its verifier. Asked how to scope the rework.

**AskUserQuestion → User chose:** "Wrap generate+verify as a component" (build a
pipeline_core-conformant component; keep the verified RTL/testbench as the
artifacts it produces).

---

## Turn 8 — Build the conformant component

**Assistant (summary of what was built and verified):** Built the `hw_trojan`
package conforming to the contract:
`config.py` (tunables + justifications), `dsp.py` (bit-accurate golden model),
`plan.py` (`TrojanPlan` + `HeuristicPlanner`), `prompts.py` (versioned PLANNER +
GENERATOR), `rtlgen.py` (emits mem files, clean + Trojaned Verilog, self-checking
testbench), `verifiers.py` (five `Verdict`s), `evaluation.py`, `model.py`
(`HWTrojanModel(PipelineComponent)` with `plan()`/`execute()`), `cli.py`, tests,
examples, README. Vendored `pipeline_core` so it runs standalone.

Ran the component offline end-to-end (plan → generate → verify):
```
Status: SUCCESS | confidence 0.99
  baseline_exact: PASS    selftest_no_arm: PASS    trigger_specific: PASS (0.94)
  trigger_arms: PASS      payload_effective: PASS
13 passed in 0.90s        # offline MockLLM pytest suite
```
Evaluation on the real audio: separation ≈ 30×, 0 false-positive windows / 937,
out-of-band leak ≈ 838×, arm ≈ 0.19 s. Generated Verilog structurally clean
(balanced modules, no undefined macros). `recover_coeffs.py` validated by
recovering a known FIR **bit-for-bit** (symmetry error 0). Produced a golden-model
demo spectrogram showing normal filtering for ~1 s, then out-of-band leak at the
ARM point.

---

## Turn 9 — Wire into the framework pipeline; draft deliverables

**User:** Can you do both? Wire into the framework pipeline and then move on to
drafting the deliverables?

**Assistant (summary):** Wrote `csaw_pipeline.py` composing the component with
`task_decomposition` (attack DAG: recover → design → verify) and
`answer_verification` (gate), one shared Tracer, through the real `pipeline_core`
contracts. Vendored the needed model packages so it runs standalone. Ran it:
```
wave 1 [recover] ok 0.90 ; wave 2 [design] ok 0.90 (hw_trojan) ; wave 3 [verify] needs_review (abstains offline)
hw_trojan golden-model gate: Status SUCCESS, 5/5 verifiers PASS
```
Drafted the `ai/` deliverables: `GENERATOR_PROMPTS.md` (the Stage 0–3 prompt
chain to author the Trojan RTL), `generation_log.jsonl` (plan + per-verifier
trail, emitted by `tools/emit_ai_log.py`), and `SOURCES.md`. Was explicit that no
fake LLM transcript was fabricated — the log holds the genuine plan + verification
records with marked placeholders for the human/agent LLM authoring turns.

---

## Turn 10+ — Publish to GitHub

**User:** connect to github → are you connected now? → No, make a new repository
and push it to a GitHub → https://github.com/Jarynxia/Test Push it to this GitHub

**Assistant (summary):** GitHub connected (account Jarynxia). Creating a brand-new
repo was refused (session bound to configured repositories); after the Claude
GitHub App was granted access to `Jarynxia/Test`, pushed the full
`challenge3_trigger1/` deliverable to `main` (98 files, commit `69b1f64`).

---

## Status recorded at log time

Verified by the golden model: baseline bit-exact, self-test never arms, ~30×
trigger separation, 0 false positives across the 15 s track, out-of-band leak
~838×. **Still pending hardware:** recover the real FIR coefficients from a board
capture (`tools/recover_coeffs.py`) for a board-exact baseline, and HDL/board
confirmation (compile `generated/tb_trojan.v` on the OSS CAD Suite, program the
board, capture the exploit). The submitted Trojan RTL must be regenerated through
a logged AI generation (this log, plus `GENERATOR_PROMPTS.md`).
