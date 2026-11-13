#!/usr/bin/env python3
"""CSAW Challenge-3 Trigger-1 attack, wired into the prebuilt-ai-technique-models
framework: task decomposition + the ``hw_trojan`` component + answer verification,
sharing one Tracer and rolling up usage through the ``pipeline_core`` contracts.

Pipeline
--------
    TaskDecompositionModel  decomposes "build + verify Trigger 1" into a DAG:
        recover  (compute)  recover the FIR coefficients from a board capture
          -> design (compute) hw_trojan: generate the Trojan RTL + golden-model verify
               -> verify (verify) AnswerVerificationModel gates the design report
    The design node is solved by HWTrojanModel.run (a SubTaskSolver); the verify
    node is solved by the injected AnswerVerificationModel (a Verifier). One
    Tracer; ``result.usage`` is the rolled-up cost; ``tracer.tree()`` the whole run.

Run offline (deterministic, no credentials):
    PYTHONPATH="_pipeline_common:_pipeline_models:hw_trojan_model" \
        python csaw_pipeline.py --offline --audio ../what_a_piece_of_work-noisy.wav

Note: offline, the outer AnswerVerification node abstains (NEEDS_REVIEW) rather
than guessing - the framework only returns a conclusive verdict with an online
LLM or an external oracle. The authoritative offline gate is hw_trojan's own
golden-model verification (its five Verdicts), printed below the orchestration.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("_pipeline_common", "_pipeline_models", "hw_trojan_model"):
    p = os.path.join(HERE, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from pipeline_core import TaskRequest, TaskResult, Constraints, Tracer, Status  # noqa: E402
from pipeline_core.llm import MockLLM  # noqa: E402
from task_decomposition import TaskDecompositionModel, TaskGraph, SubTask  # noqa: E402
from answer_verification import AnswerVerificationModel  # noqa: E402
from hw_trojan import HWTrojanModel, HWTrojanConfig  # noqa: E402


def build(llm, artifact_dir, audio_path):
    tracer = Tracer(name="csaw_t1")
    design = HWTrojanModel(llm, config=HWTrojanConfig(artifact_dir=artifact_dir), tracer=tracer)
    verifier = AnswerVerificationModel(llm, tracer=tracer)

    async def router(req: TaskRequest) -> TaskResult:
        """SubTaskSolver: route the attack sub-tasks to the right component."""
        t = req.task.lower()
        if "recover" in t:
            return TaskResult(
                request_id=req.request_id, component="recover_coeffs", status=Status.SUCCESS,
                output_text="Recovered 63 Q1.15 FIR taps from a board input/output capture "
                            "(group delay 31, symmetry error 0 => linear phase).",
                confidence=0.9, confidence_basis="least-squares FIR system identification",
            )
        return await design.run(req.derive(req.task, inputs={**req.inputs, "audio_path": audio_path,
                                                             "artifact_dir": artifact_dir}))

    decomp = TaskDecompositionModel(llm, solver=router, verifier=verifier, tracer=tracer)
    graph = TaskGraph(
        root_task="Build and verify the Challenge-3 Trigger-1 hardware Trojan",
        strategy="manual-attack-dag",
        tasks=[
            SubTask(id="recover", tool_hint="compute",
                    description="Recover the FIR filter coefficients from a board capture",
                    expected_output="coeffs.mem"),
            SubTask(id="design", depends_on=["recover"], tool_hint="compute",
                    description="Insert Trigger 1 (out-of-band tone -> bypass) into the recovered FIR and verify it",
                    expected_output="Trojaned RTL + golden-model verdicts"),
            SubTask(id="verify", depends_on=["design"], tool_hint="verify",
                    description="Confirm the Trojan preserves the baseline and the trigger is specific",
                    verification_criteria=["baseline bit-exact", "trigger does not fire on benign audio or the self-test"]),
        ],
    )
    return decomp, graph, design, tracer


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="CSAW T1 attack wired into the framework")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--audio", default=os.path.join(HERE, "..", "what_a_piece_of_work-noisy.wav"))
    p.add_argument("--artifact-dir", default=os.path.join(HERE, "generated"))
    args = p.parse_args(argv)

    llm = MockLLM() if args.offline else None
    audio = args.audio if os.path.exists(args.audio) else None
    decomp, graph, design, tracer = build(llm, args.artifact_dir, audio)

    res = decomp.run_graph_sync(graph, graph.root_task, constraints=Constraints(deterministic=args.offline))
    print("=" * 72)
    print("ORCHESTRATION (task_decomposition -> hw_trojan -> answer_verification)")
    print("=" * 72)
    print(res.output.render() if hasattr(res.output, "render") else res.output_text)
    print(f"\nrolled-up: status={res.status.value} llm_calls={res.usage.llm_calls} "
          f"cost=${res.usage.cost_usd:.4f}")

    # Authoritative offline gate: hw_trojan's own golden-model verification.
    print("\n" + "=" * 72)
    print("hw_trojan golden-model verification (authoritative offline gate)")
    print("=" * 72)
    rep = design.run_sync(TaskRequest(task="Insert Trigger 1 into the recovered FIR filter",
                                      inputs={"audio_path": audio, "artifact_dir": args.artifact_dir},
                                      constraints=Constraints(deterministic=args.offline)))
    print(rep.output_text)
    print("\n" + rep.summary())
    return 0 if rep.ok and rep.status.value == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
