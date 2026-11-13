#!/usr/bin/env python3
"""Emit the verifier side of the AI generation log.

Runs the hw_trojan component and writes ai/generation_log.jsonl: one record for
the plan decision, the generate step, and each golden-model verdict. This is the
AUTOMATED, auditable half of the log (the plan + verification trail). The human/
agent must still append the LLM RTL-authoring turns (see ai/GENERATOR_PROMPTS.md)
to make the log complete for submission.

    PYTHONPATH="_pipeline_common:hw_trojan_model" python tools/emit_ai_log.py [--audio x.wav]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hw_trojan_model"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_pipeline_common"))

from pipeline_core import TaskRequest, Constraints          # noqa: E402
from pipeline_core.llm import MockLLM                       # noqa: E402
from hw_trojan import HWTrojanModel, HWTrojanConfig         # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
AI_DIR = os.path.join(HERE, "..", "ai")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--audio", default=os.path.join(HERE, "..", "..", "what_a_piece_of_work-noisy.wav"))
    p.add_argument("--out", default=os.path.join(AI_DIR, "generation_log.jsonl"))
    args = p.parse_args(argv)

    audio = args.audio if os.path.exists(args.audio) else None
    model = HWTrojanModel(MockLLM(), config=HWTrojanConfig())
    res = model.run_sync(TaskRequest(
        task="Insert Trigger 1 (out-of-band tone -> bypass) into the recovered FIR filter",
        inputs={"audio_path": audio, "artifact_dir": os.path.join(HERE, "..", "generated")},
        constraints=Constraints(deterministic=True)))

    rows = []
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    plan = res.metadata.get("plan", {})
    rows.append({"ts": ts, "stage": "plan", "actor": "hw_trojan.HeuristicPlanner",
                 "decision": plan, "note": "offline heuristic plan; online this is one structured LLM call"})
    rows.append({"ts": ts, "stage": "generate", "actor": "hw_trojan.rtlgen",
                 "artifacts": res.metadata.get("artifact_dir"),
                 "note": "parameter-rendered reference RTL; replace with the logged LLM authoring turns (GENERATOR_PROMPTS.md)"})
    for v in res.output["verdicts"]:
        rows.append({"ts": ts, "stage": "verify", "actor": "hw_trojan.golden_model",
                     "method": v["method"], "passed": v["passed"], "score": v["score"],
                     "details": v.get("details", {})})
    rows.append({"ts": ts, "stage": "result", "status": res.status.value,
                 "confidence": round(res.confidence, 3), "basis": res.confidence_basis})

    os.makedirs(AI_DIR, exist_ok=True)
    with open(args.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    print("wrote %s (%d records). Append your LLM authoring turns to complete the log." % (args.out, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
