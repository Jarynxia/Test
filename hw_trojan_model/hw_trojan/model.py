"""The ``hw_trojan`` pipeline component: generate a hardware Trojan, then verify it.

Life cycle (pipeline_core contract)
-----------------------------------
``plan(request, ctx)`` reads the natural-language task and decides the Trojan
strategy (trigger family, frequency, window/dwell, payload). One structured LLM
call online; the :class:`HeuristicPlanner` offline / deterministic.

``execute(request, plan, ctx)``
  1. GENERATE - emit the coefficient/table mem files, the clean + Trojaned RTL
     and a self-checking testbench for the planned parameters (``rtlgen``).
  2. VERIFY - run the bit-accurate golden-model verifiers (baseline exactness,
     self-test no-arm, trigger specificity, trigger arms, payload effective) and
     fuse them into a status + confidence.

Returns a :class:`TaskResult` whose ``output`` is a :class:`TrojanReport`.

Compliance note: the RTL this emits is parameter-rendered reference. For the
CSAW submission the Trojan RTL must be produced by a *logged* AI generation
(this component's GENERATOR prompt, or your agent) - see the package README.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from pipeline_core import (
    ComponentSpec, PipelineComponent, RunContext, Status,
    TaskRequest, TaskResult, Verdict, LLMError, BudgetExceededError, register,
)
from pipeline_core.llm import LLMRequest

from .config import HWTrojanConfig
from .plan import HeuristicPlanner, LLMPlan, TrojanPlan, apply_plan, plan_from_llm
from . import prompts as P
from . import dsp, rtlgen
from .verifiers import build_signals, verify_all

CRITICAL = ("baseline_exact", "selftest_no_arm", "trigger_arms", "payload_effective")


class TrojanReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: TrojanPlan
    accepted: bool
    status: str
    confidence: float
    confidence_basis: str
    verdicts: list[Verdict]
    metrics: dict[str, float]
    artifacts: dict[str, Any]
    issues: list[str] = Field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"Hardware Trojan (Trigger 1 = out-of-band {self.plan.f_trig} Hz tone -> {self.plan.payload})",
            f"Status: {self.status.upper()} | confidence {self.confidence:.2f}",
            f"Basis: {self.confidence_basis}",
            "Verifiers:",
        ]
        for v in self.verdicts:
            tag = "PASS" if v.passed else "FAIL"
            extra = f" | {v.issues[0]}" if v.issues and v.issues[0] else ""
            lines.append(f"  - {v.method}: {tag} score={v.score:.2f}{extra}")
        if self.issues:
            lines.append("Blocking issues:")
            lines.extend(f"  - {i}" for i in self.issues)
        a = self.artifacts
        lines.append(f"Artifacts in {a.get('out_dir','?')}: fir_core.v, fir_core_trojan.v, tb_trojan.v, *.mem")
        return "\n".join(lines)


def _sanitize(schema_model) -> dict:
    try:
        from pipeline_core import sanitize_schema  # type: ignore
        return sanitize_schema(schema_model.model_json_schema())
    except Exception:
        return schema_model.model_json_schema()


@register
class HWTrojanModel(PipelineComponent):
    """Generate-and-verify a hardware Trojan for the Challenge-3 FIR audio filter."""

    spec = ComponentSpec(
        name="hw_trojan",
        version="1.0.0",
        description="Generate a trigger+payload hardware Trojan for a recovered FIR audio filter and verify it against a bit-accurate golden model and a synthesizable-RTL testbench.",
        capabilities=["plan_trigger", "generate_rtl", "golden_model_verify", "baseline_exact_check"],
        consumes=["task", "inputs.audio_path", "inputs.coeffs"],
        produces=["TrojanReport", "rtl artifacts", "self-checking testbench"],
        composes_with=["answer_verification", "task_decomposition", "parallelization"],
    )

    def __init__(self, llm=None, *, config: Optional[HWTrojanConfig] = None, **kw: Any) -> None:
        super().__init__(llm, **kw)
        self.cfg = config or HWTrojanConfig()
        self.planner = HeuristicPlanner(self.cfg)

    # ----------------------------------------------------------- helpers
    def use_llm(self, ctx: RunContext, request: TaskRequest) -> bool:
        return not ctx.offline and not request.constraints.deterministic

    def _load_audio(self, request: TaskRequest) -> Optional[np.ndarray]:
        a = request.inputs.get("audio")
        if isinstance(a, np.ndarray):
            return a.astype(np.int16)
        path = request.inputs.get("audio_path")
        if path and os.path.exists(path):
            import wave
            w = wave.open(path, "rb")
            data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
            if w.getnchannels() > 1:
                data = data[:: w.getnchannels()]
            return data.astype(np.int16)
        return None

    # ----------------------------------------------------------- plan
    async def plan(self, request: TaskRequest, ctx: RunContext) -> TrojanPlan:
        if self.use_llm(ctx, request) and (request.constraints.max_llm_calls or 1) > 0:
            try:
                req = LLMRequest.simple(
                    f"<task>{request.task}</task>\n<target>FIR low-pass, fs={self.cfg.fs}, "
                    f"stop band above ~{self.cfg.cutoff_hz} Hz; source audio occupies the speech "
                    f"band and has a ~6 kHz noise component.</target>\n{P.PLANNER.instructions}",
                    system=[P.PLANNER.system],
                    schema=_sanitize(LLMPlan),
                    effort=self.cfg.plan_effort,
                )
                resp = await ctx.llm_call(req, step="plan.llm")
                return plan_from_llm(LLMPlan.model_validate(resp.parsed), self.cfg)
            except BudgetExceededError:
                raise
            except (LLMError, ValueError, Exception) as exc:  # noqa: BLE001
                ctx.warn(f"LLM planning failed ({type(exc).__name__}); using heuristic planner")
        return self.planner.plan(request.task)

    # ----------------------------------------------------------- execute
    async def execute(self, request: TaskRequest, plan: TrojanPlan, ctx: RunContext) -> TaskResult:
        cfg = apply_plan(self.cfg, plan)
        audio = self._load_audio(request)

        issues: list[str] = []
        if not cfg.nyquist_ok():
            issues.append(f"f_trig {cfg.f_trig} is not below Nyquist {cfg.fs//2}")

        with ctx.step("generate") as rec:
            out_dir = request.inputs.get("artifact_dir") or cfg.artifact_dir
            if not os.path.isabs(out_dir):
                out_dir = os.path.join(os.getcwd(), out_dir)
            gen = rtlgen.generate(cfg, out_dir, audio=audio)
            rec.summary = f"emitted RTL+mem+tb ({gen['nvec']} vectors) to {out_dir}"

        with ctx.step("verify") as rec:
            hq = dsp.design_coeffs(cfg)
            sig = build_signals(cfg, audio)
            verdicts = verify_all(cfg, hq, sig)
            rec.summary = "; ".join(f"{v.method}={'P' if v.passed else 'F'}" for v in verdicts)

        passed = {v.method: v.passed for v in verdicts}
        for m in CRITICAL:
            if not passed.get(m, False):
                issues.append(f"critical verifier '{m}' failed")
        accepted = not issues
        confidence = sum(v.score for v in verdicts) / max(1, len(verdicts))
        if not passed.get("baseline_exact", False):
            status = Status.FAILED            # a broken baseline is fatal for scoring
            confidence = min(confidence, 0.1)
        elif accepted:
            status = Status.SUCCESS
        else:
            status = Status.NEEDS_REVIEW
        basis = (f"{sum(v.passed for v in verdicts)}/{len(verdicts)} verifiers passed; "
                 f"golden-model (board/HDL-sim confirmation still required)")

        metrics: dict[str, float] = {}
        for v in verdicts:
            for k in ("separation_x", "oob_leak_ratio", "false_positive_windows", "arm_time_s"):
                if k in v.details:
                    metrics[k] = float(v.details[k])

        report = TrojanReport(
            plan=plan, accepted=accepted, status=status.value, confidence=confidence,
            confidence_basis=basis, verdicts=verdicts, metrics=metrics, artifacts=gen, issues=issues,
        )
        res = self.new_result(
            request, status=status, output=report.model_dump(mode="json"),
            output_text=report.render(), confidence=confidence, confidence_basis=basis,
            warnings=list(ctx.warnings), errors=[], metadata={"artifact_dir": gen["out_dir"]},
        )
        return res

    # ----------------------------------------------------------- direct API
    def generate_and_verify_sync(self, task: str = "Insert Trigger 1 into the recovered FIR filter", **kw) -> TaskResult:
        return self.run_sync(task, **kw)
