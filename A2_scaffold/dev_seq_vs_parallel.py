#!/usr/bin/env python3
"""
D2(c) - SEQUENTIAL vs PARALLEL, fixed and reproducible
====================================================================
Compares the shipped PARALLEL design for CLM-8842 (backends.SCRIPTS -
9 tool calls in 4 turns) against a SEQUENTIAL variant that makes the
exact same 9 calls, one per turn, on the SCRIPTED backend (free,
deterministic - no live model, no key).

>>> TOKENS AND COST HERE ARE SIMULATED, NOT MEASURED. <<<
The scripted backend's token_estimate() is a fixed formula
(1800 + 600*len(transcript), 120) - see backends.py - not real usage from
a model. That is exactly right for what this script demonstrates: the
MECHANISM (why more turns costs more, and which guardrail a design choice
trips), which follows from turn/transcript growth and holds regardless of
which model is behind it. It is NOT a real cost figure and must NOT be
fed into D6's cost model directly - D6 needs measured tokens from the
live battery (dev_v1_v2_compare.py / docs/D2_tool_layer.md), where the
same parallel-vs-sequential shape can be cross-checked against real
numbers if that comparison is worth re-running live.

This replaces the one-off interactive comparison run during D2(c) with
a script that produces the same numbers every time. See
docs/D2_tool_layer.md for the write-up this feeds.

Usage:
    python3 dev_seq_vs_parallel.py
Writes dev_seq_vs_parallel_results.json.
"""
import copy
import json

import agent
import backends
import config

config.BACKEND = "scripted"
config.PROBLEM = "A"

CASE_ID = "CLM-8842"

# The same 9 calls the shipped parallel script makes, one per turn instead
# of batched. Built from backends.SCRIPTS[CASE_ID] so it can never drift
# out of sync with the real call arguments.
_PARALLEL_SCRIPT = backends.SCRIPTS[CASE_ID]
_FINAL_STEP = _PARALLEL_SCRIPT[-1]


def _sequential_script():
    turn2_calls = _PARALLEL_SCRIPT[1]["calls"]
    turn3_calls = _PARALLEL_SCRIPT[2]["calls"]
    turn4_calls = _PARALLEL_SCRIPT[3]["calls"]
    steps = [copy.deepcopy(_PARALLEL_SCRIPT[0])]
    for call in turn2_calls + turn3_calls + turn4_calls:
        steps.append({"thought": "sequential: %s" % call[0], "calls": [call]})
    steps.append(copy.deepcopy(_FINAL_STEP))
    return steps


def run_variant(label, script, max_turns=None, max_tokens=None):
    original = backends.SCRIPTS[CASE_ID]
    backends.SCRIPTS[CASE_ID] = script
    orig_turns, orig_tokens = config.MAX_TURNS, config.MAX_TOKENS_PER_RUN
    if max_turns is not None:
        config.MAX_TURNS = max_turns
    if max_tokens is not None:
        config.MAX_TOKENS_PER_RUN = max_tokens
    try:
        record = agent.run_case(CASE_ID, problem="A", approve=lambda a, p: True)
    finally:
        backends.SCRIPTS[CASE_ID] = original
        config.MAX_TURNS, config.MAX_TOKENS_PER_RUN = orig_turns, orig_tokens

    row = {
        "label": label,
        "turns": record["turns"],
        "calls_executed": len(record["evidence"]),
        "tokens_in": record["tokens_in"],
        "tokens_out": record["tokens_out"],
        "tokens_total": record["tokens_in"] + record["tokens_out"],
        "cost_usd": record["cost_usd"],
        "decision": record.get("decision"),
        "stopped_by": record.get("stopped_by"),
    }
    print("  %-42s turns=%d calls=%d tokens=%d cost=$%.5f decision=%-20s stopped_by=%s"
          % (label, row["turns"], row["calls_executed"], row["tokens_total"],
             row["cost_usd"], row["decision"], row["stopped_by"]))
    return row


def main():
    print(config.summary())
    print("  D2(c): %s, parallel (shipped) vs sequential, scripted backend" % CASE_ID)
    print("  NOTE: tokens/cost below are the scripted backend's simulated"
          " estimate, not")
    print("  measured usage - good for comparing the MECHANISM, not a D6"
          " cost input.")
    print("  D6 must use measured tokens from the live battery instead"
          " (docs/D2_tool_layer.md).")
    print()

    rows = []
    rows.append(run_variant("parallel (shipped, MAX_TURNS=8)", _PARALLEL_SCRIPT))
    rows.append(run_variant(
        "sequential, one call per turn (MAX_TURNS=8, current default)",
        _sequential_script(),
    ))
    rows.append(run_variant(
        "sequential, one call per turn (MAX_TURNS=12, artificially raised)",
        _sequential_script(), max_turns=12,
    ))
    rows.append(run_variant(
        "sequential, one call per turn (both caps raised, run to completion)",
        _sequential_script(), max_turns=12, max_tokens=200000,
    ))

    print()
    print("=" * 68)
    parallel, seq_default, seq_raised, seq_completed = rows
    print("  Parallel completes the correct decision in %d turns / %d tokens."
          % (parallel["turns"], parallel["tokens_total"]))
    if seq_default["decision"] != "approve_in_principle":
        print("  Sequential, under the CURRENT %s guardrail, never reaches a"
              " decision:" % (seq_default["stopped_by"] or "guardrail"))
        print("  it is halted by '%s' before issue_decision_letter ever runs -"
              % seq_default["stopped_by"])
        print("  the run ends in a wrong 'escalate', not merely a slower"
              " 'approve_in_principle'.")
    print("  Raising only MAX_TURNS does not help: %d turns / %d tokens, still"
          % (seq_raised["turns"], seq_raised["tokens_total"]))
    print("  halted by '%s' - budget_ceiling, not step_cap, is what actually"
          % seq_raised["stopped_by"])
    print("  bounds a serial run here.")
    print("  With BOTH caps raised so it can finish at all: %d turns / %d"
          % (seq_completed["turns"], seq_completed["tokens_total"]))
    if parallel["tokens_total"]:
        print("  tokens for the SAME 9 calls and the same correct decision -"
              " %.1fx parallel's"
              % (seq_completed["tokens_total"] / parallel["tokens_total"]))
        print("  tokens, %.1fx its turns."
              % (seq_completed["turns"] / parallel["turns"]))
    print("  Cause: the full transcript is resent every turn (prompt.py's own")
    print("  comment: input ~ B*T + D*T(T-1)/2) - turns cost QUADRATICALLY,")
    print("  not linearly, so serialising independent calls is not a fixed")
    print("  overhead: under the guardrails this team actually ships with, it")
    print("  changes which guardrail decides the case, and to the wrong one.")
    print("=" * 68)

    output = {
        "caveat": (
            "tokens/cost are the SCRIPTED backend's simulated estimate "
            "(backends.ScriptedBackend.token_estimate), not measured usage. "
            "Valid for comparing the sequential-vs-parallel MECHANISM (turn "
            "growth, which guardrail fires); NOT a real cost figure - do "
            "not feed these numbers into D6's cost model. D6 needs measured "
            "tokens from the live battery (dev_v1_v2_compare.py)."
        ),
        "rows": rows,
    }
    with open("dev_seq_vs_parallel_results.json", "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, default=str)
    print("  wrote dev_seq_vs_parallel_results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
