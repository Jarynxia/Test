# AI method and sources (CSAW Challenge 3, Trigger 1)

Fill this in for the submission's "Creative Use of Generative AI" judging. The
rubric judges this largely from the transcripts — be specific about the method.

## Model(s)
- Primary generation model: `______`  (e.g. the model your agent calls)
- Planning / verification model (if different): `______`

## Method of interaction
- [ ] Autonomous agent pipeline (plan → generate → verify → retry), logged
- [ ] Prompt chaining with scripted insertion
- [ ] Deliberate prompt engineering (web UI / API), manual integration

## Framework
- The generation+verification is structured as a `pipeline_core` component
  (`hw_trojan`) composed with `task_decomposition` and `answer_verification`
  from the *prebuilt-ai-technique-models* framework. Orchestration: `csaw_pipeline.py`.
- The component's plan/verify loop and the GENERATOR prompt chain
  (`GENERATOR_PROMPTS.md`) are what drove the RTL authoring.

## What is AI-generated vs tooling
- **AI-generated (logged here):** the Trojan trigger + payload RTL and the exploit
  logic.
- **Non-AI tooling (allowed, not required in the log):** the bit-accurate golden
  model, the self-checking testbench, the host drivers (`make_trigger_wav.py`,
  `analyze_output.py`), and coefficient recovery (`recover_coeffs.py`).

## Design-grounding references (cite in the technical brief)
- Hardware-Trojan trigger/payload taxonomy — Tehranipoor & Wang (2008);
  survey arXiv:1801.00649.
- FIR coefficients as the defining IP — Aksoy et al. (2022), *Hardware Obfuscation
  of Digital FIR Filters*, arXiv:2202.10022.
- LLM-authored synthesizable Trojan RTL — SENTAUR (NL → trigger/payload RTL).

## Log completeness checklist (CSAW: missing logs ⇒ disqualified)
- [ ] `session_*.md` — every generation prompt + response, verbatim
- [ ] `generation_log.jsonl` — plan + per-iteration verdicts (tooling half emitted by
      `tools/emit_ai_log.py`; append the LLM authoring turns)
- [ ] This `SOURCES.md` completed
