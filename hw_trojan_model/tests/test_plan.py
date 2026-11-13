"""Heuristic planner behaviour (offline path)."""
from __future__ import annotations

from hw_trojan.config import HWTrojanConfig
from hw_trojan.plan import HeuristicPlanner, LLMPlan, apply_plan, plan_from_llm


def test_default_plan_is_tone_bypass():
    plan = HeuristicPlanner(HWTrojanConfig()).plan("Insert Trigger 1 into the recovered FIR filter")
    assert plan.trigger_family == "tone"
    assert plan.payload == "bypass"
    assert plan.f_trig == 7000


def test_keywords_nudge_family_and_payload():
    pl = HeuristicPlanner(HWTrojanConfig()).plan("use a run-length trigger with a mute payload")
    assert pl.trigger_family == "runlength"
    assert pl.payload == "mute"


def test_apply_plan_updates_config():
    cfg = HWTrojanConfig()
    pl = plan_from_llm(LLMPlan(f_trig=7500, dwell=5, payload="bypass"), cfg)
    cfg2 = apply_plan(cfg, pl)
    assert cfg2.f_trig == 7500 and cfg2.dwell == 5
    # window/ratio stay config-governed invariants
    assert cfg2.ratio_shift == cfg.ratio_shift
