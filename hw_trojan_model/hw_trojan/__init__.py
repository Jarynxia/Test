"""hw_trojan - generate-and-verify a hardware Trojan for the Challenge-3 FIR audio filter.

Importing the package registers :class:`HWTrojanModel` with
``pipeline_core.register`` under the name ``hw_trojan``.

    from hw_trojan import HWTrojanModel, HWTrojanConfig
    model = HWTrojanModel()                      # MockLLM without credentials
    result = model.generate_and_verify_sync()    # plan -> generate RTL -> verify
"""
from __future__ import annotations

from .config import HWTrojanConfig
from .plan import HeuristicPlanner, LLMPlan, TrojanPlan, apply_plan, plan_from_llm
from .model import HWTrojanModel, TrojanReport
from .evaluation import evaluate
from . import dsp, rtlgen, verifiers

__version__ = "1.0.0"
__all__ = [
    "HWTrojanConfig", "HWTrojanModel", "TrojanReport",
    "HeuristicPlanner", "LLMPlan", "TrojanPlan", "apply_plan", "plan_from_llm",
    "evaluate", "dsp", "rtlgen", "verifiers",
]
