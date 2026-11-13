"""Minimal usage: plan -> generate RTL -> verify, offline (no credentials).

    PYTHONPATH="../../_pipeline_common:.." python basic_usage.py
"""
from __future__ import annotations

import tempfile

from pipeline_core.llm import MockLLM
from pipeline_core import TaskRequest, Constraints
from hw_trojan import HWTrojanModel, HWTrojanConfig


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        model = HWTrojanModel(MockLLM(), config=HWTrojanConfig(artifact_dir=d))
        res = model.run_sync(TaskRequest(
            task="Insert Trigger 1 (out-of-band tone -> bypass) into the recovered FIR filter",
            inputs={"artifact_dir": d},
            constraints=Constraints(deterministic=True),
        ))
        print(res.output_text)
        print(res.summary())


if __name__ == "__main__":
    main()
