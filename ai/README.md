# ai/ — AI generation transcripts (REQUIRED by CSAW Challenge 3)

> *"Comprehensive logs (or a document linking to chat histories) of all prompts
> and AI responses used to generate the Trojan and exploit. Submissions missing
> these logs will be disqualified."*

Put here the **full transcripts** of the AI session(s) that generated the Trojan
RTL and exploit logic for Trigger 1. The RTL in `../generated/` must correspond
to a logged generation — either:

1. your agent driving `hw_trojan/prompts.py::GENERATOR` (save each prompt +
   response, plus the verifier verdicts from each iteration), or
2. the assistant session that produced this component (export the conversation).

Non-AI tooling (the golden model, testbench, host drivers, coefficient recovery)
does **not** need to be in here — only the AI authoring of the Trojan/exploit.

Suggested layout:
```
ai/
├── session_YYYYMMDD.md        verbatim prompts + responses
├── generation_log.jsonl       per-iteration: prompt hash, model, verdict, pass/fail
└── SOURCES.md                 model(s) used, method (API / web UI / agent), framework
```
