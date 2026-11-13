"""``python -m hw_trojan "task" [--offline] [--audio x.wav] [--artifact-dir DIR] [--json]``"""
from __future__ import annotations

import argparse
import json
import sys

from pipeline_core import TaskRequest, Constraints
from pipeline_core.llm import MockLLM

from .config import HWTrojanConfig
from .model import HWTrojanModel


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Generate + verify the Challenge-3 Trigger-1 Trojan")
    p.add_argument("task", nargs="?", default="Insert Trigger 1 (out-of-band tone -> bypass) into the recovered FIR filter")
    p.add_argument("--offline", action="store_true", help="force the heuristic planner (no credentials)")
    p.add_argument("--audio", help="16-bit mono WAV to use as benign audio for verification")
    p.add_argument("--artifact-dir", default="generated")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    llm = MockLLM() if args.offline else None
    model = HWTrojanModel(llm, config=HWTrojanConfig(artifact_dir=args.artifact_dir))
    req = TaskRequest(
        task=args.task,
        inputs={k: v for k, v in [("audio_path", args.audio), ("artifact_dir", args.artifact_dir)] if v},
        constraints=Constraints(deterministic=args.offline),
    )
    res = model.run_sync(req)
    if args.json:
        print(json.dumps(res.output, indent=2, default=str))
    else:
        print(res.output_text)
        print("\n" + res.summary())
    return 0 if res.ok and res.status.value in ("success", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
