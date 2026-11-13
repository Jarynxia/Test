"""End-to-end component run (offline MockLLM) and registry registration."""
from __future__ import annotations

import os
import tempfile

from pipeline_core import TaskRequest, Constraints, Status, get
from pipeline_core.llm import MockLLM

import hw_trojan  # noqa: F401  (registers the component)
from hw_trojan import HWTrojanModel, HWTrojanConfig


def test_registered():
    assert get("hw_trojan") is HWTrojanModel


def test_run_offline_succeeds_and_generates_artifacts():
    with tempfile.TemporaryDirectory() as d:
        model = HWTrojanModel(MockLLM(), config=HWTrojanConfig(artifact_dir=d))
        req = TaskRequest(task="Insert Trigger 1 into the recovered FIR filter",
                          inputs={"artifact_dir": d}, constraints=Constraints(deterministic=True))
        res = model.run_sync(req)
        assert res.status == Status.SUCCESS
        assert res.confidence >= 0.9
        # the five verifiers are present and all passed
        methods = {v["method"]: v["passed"] for v in res.output["verdicts"]}
        assert methods["baseline_exact"] and methods["selftest_no_arm"]
        assert methods["trigger_arms"] and methods["payload_effective"]
        # artifacts were emitted
        for fn in ("fir_core.v", "fir_core_trojan.v", "tb_trojan.v", "coeffs.mem", "params.vh"):
            assert os.path.exists(os.path.join(d, fn)), fn
        # offline => no LLM spend
        assert res.usage.llm_calls == 0


def test_plan_is_attached_to_metadata():
    with tempfile.TemporaryDirectory() as d:
        model = HWTrojanModel(MockLLM(), config=HWTrojanConfig(artifact_dir=d))
        res = model.run_sync(TaskRequest(task="t1", inputs={"artifact_dir": d},
                                         constraints=Constraints(deterministic=True)))
        assert "plan" in res.metadata
        assert res.metadata["plan"]["payload"] == "bypass"
