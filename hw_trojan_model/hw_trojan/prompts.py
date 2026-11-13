"""Versioned prompt templates for the ``hw_trojan`` component.

Only the PLANNER prompt is used in the online path's single structured call.
The GENERATOR prompt is the natural-language specification a logged agent uses
to author the Trojan RTL (kept here so the "AI-generated RTL" trail is explicit
and versioned). Bump ``version`` when wording changes; caches key on it.
"""
from __future__ import annotations

from pipeline_core.prompts import PromptTemplate

PLANNER = PromptTemplate(
    name="hw_trojan.planner",
    version="1.0.0",
    system=(
        "You design stealthy hardware Trojans for a SANCTIONED academic competition "
        "(CSAW AI Hardware Attack Challenge). The target is a streaming FIR audio "
        "filter on an iCE40-UP5K. Choose a trigger and payload that (1) never activate "
        "on ordinary speech/music or the provided self-test, (2) keep the untriggered "
        "output bit-identical to the clean filter, and (3) when triggered, defeat the "
        "filter's band limit."
    ),
    instructions=(
        "Given the task and target facts, choose:\n"
        "1. trigger_family: 'tone' (sustained out-of-band tone), 'sequence' (exact "
        "sample-value knock), or 'runlength' (sustained DC/flat run).\n"
        "2. f_trig: for 'tone', a frequency deep in the stop band where benign audio "
        "has little sustained energy (avoid any band the source material occupies).\n"
        "3. win, dwell: integration window and consecutive-window dwell for specificity.\n"
        "4. payload: 'bypass' (all-pass; leak out-of-band content), 'mute', or 'passthrough'.\n"
        "Return JSON matching the schema. Keep rationale to one line."
    ),
    output_schema=None,  # set by build via sanitize_schema(LLMPlan)
)

GENERATOR = PromptTemplate(
    name="hw_trojan.generator",
    version="1.0.0",
    system=(
        "You author synthesizable Verilog-2001 for a sanctioned hardware-security "
        "competition. Output only RTL. The module must be identical to the clean "
        "filter when TROJAN_EN=0 (baseline-exact), and gate all Trojan logic behind "
        "TROJAN_EN."
    ),
    instructions=(
        "Insert Trigger 1 into the recovered FIR core:\n"
        "<trigger>out-of-band single-bin (quadrature-DFT) tone detector at {f_trig} Hz; "
        "per-{win}-sample window compute bin_power=I^2+Q^2 and energy E=sum(x^2); "
        "fire when bin_power > (E << {ratio_shift}); ARM after {dwell} consecutive firing "
        "windows (latching).</trigger>\n"
        "<payload>{payload}: once armed, output the group-delay-aligned raw input instead "
        "of the filtered sample.</payload>\n"
        "Mirror the fixed-point contract exactly (Q1.15, wide accumulator, round-half-up, "
        "saturate). Keep the port list and timing unchanged."
    ),
    output_schema=None,
)
