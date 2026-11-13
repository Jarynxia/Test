"""Planning for the ``hw_trojan`` component.

``plan()`` reads the natural-language task and decides the Trojan strategy:
which trigger family, trigger frequency, window/dwell, and payload. Online this
is one structured LLM call returning :class:`LLMPlan`; offline (or deterministic)
the :class:`HeuristicPlanner` chooses from the task text and config defaults.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .config import HWTrojanConfig


class TrojanPlan(BaseModel):
    """The validated strategy attached to the result and carried out by execute()."""

    model_config = ConfigDict(extra="forbid")

    trigger_family: str = Field(description="tone | sequence | runlength")
    f_trig: int = Field(description="trigger tone frequency (Hz) for the 'tone' family")
    win: int
    dwell: int
    ratio_shift: int
    payload: str = Field(description="bypass | mute | passthrough")
    rationale: str = Field(default="", description="why this strategy (one line)")


class LLMPlan(BaseModel):
    """Schema for the single structured planning call (online)."""

    model_config = ConfigDict(extra="forbid")

    trigger_family: str = "tone"
    f_trig: int = 7000
    win: int = 256
    dwell: int = 4
    payload: str = "bypass"
    rationale: str = ""


class HeuristicPlanner:
    """Offline planner: config defaults, nudged by keywords in the task text."""

    def __init__(self, cfg: HWTrojanConfig) -> None:
        self.cfg = cfg

    def plan(self, task: str) -> TrojanPlan:
        cfg = self.cfg
        t = (task or "").lower()
        family = cfg.trigger_family
        if "sequence" in t or "knock" in t:
            family = "sequence"
        elif "run-length" in t or "runlength" in t or "dc " in t:
            family = "runlength"
        payload = cfg.payload
        if "mute" in t:
            payload = "mute"
        elif "pass-through" in t or "passthrough" in t:
            payload = "passthrough"
        return TrojanPlan(
            trigger_family=family,
            f_trig=cfg.f_trig,
            win=cfg.win,
            dwell=cfg.dwell,
            ratio_shift=cfg.ratio_shift,
            payload=payload,
            rationale=(
                f"out-of-band {cfg.f_trig} Hz tone + {cfg.dwell}-window dwell; "
                f"{payload} payload; chosen so benign audio and the self-test never arm"
            ),
        )


def plan_from_llm(lp: LLMPlan, cfg: HWTrojanConfig) -> TrojanPlan:
    """Merge an LLM-authored plan with config invariants (win/ratio from config)."""
    return TrojanPlan(
        trigger_family=lp.trigger_family or cfg.trigger_family,
        f_trig=int(lp.f_trig or cfg.f_trig),
        win=int(lp.win or cfg.win),
        dwell=int(lp.dwell or cfg.dwell),
        ratio_shift=cfg.ratio_shift,
        payload=lp.payload or cfg.payload,
        rationale=lp.rationale,
    )


def apply_plan(cfg: HWTrojanConfig, plan: TrojanPlan) -> HWTrojanConfig:
    """Return a config copy reflecting the plan's chosen parameters."""
    return cfg.model_copy(update={
        "trigger_family": plan.trigger_family,
        "f_trig": plan.f_trig,
        "win": plan.win,
        "dwell": plan.dwell,
        "ratio_shift": plan.ratio_shift,
        "payload": plan.payload,
    })
