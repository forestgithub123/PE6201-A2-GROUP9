#!/usr/bin/env python3
"""
PE6201 · A2 — D7 FAILURE 1: loop-control ablation
====================================================================
    python3 demo_loop_failure.py

This is a controlled "working agent minus X" experiment. X is the
action de-duplication check in Guardrails.check_duplicate. The script:

  1. runs the working CLM-8842 agent;
  2. injects a repeated model action while the guard is present, proving
     that the guard identifies the exact fault and stops loudly;
  3. repeats the same behaviour with only the guard removed;
  4. restores the guard and the working script; and
  5. runs the complete evaluation set with the real cap and a loose cap.

The experiment always forces the SCRIPTED backend. It uses no API key,
does not call the network, and does not overwrite results.json or any
results_live_*.json file. It updates only d7_results.json.
====================================================================
"""
import copy
import json
import os
import statistics
from collections import Counter

import backends
import config
from agent import run_case
from guardrails import Guardrails
from harness import code_check, load_cases, load_key, run_set


CASE_ID = "CLM-8842"
PROBLEM = "A"
RESULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "d7_results.json")


def _looping_script(case_id):
    """Return the working script with the initial retrieval repeated.

    This is the model-side behaviour that exposes the loop-control fault. It
    is identical in the guarded and unguarded conditions; only X changes.
    Re-reading get_claim does not alter the eventual business evidence, so a
    decision-only pass-rate table remains blind to the wasted work.
    """
    steps = copy.deepcopy(backends.SCRIPTS[case_id])
    repeat = copy.deepcopy(steps[0])
    repeat["thought"] = (
        "I have forgotten that I already fetched this claim; read it again."
    )
    return steps[:1] + [repeat, repeat] + steps[1:]


def _run_metrics(record, expected):
    passed, failures = code_check(record, expected)
    return {
        "decision": record.get("decision"),
        "reason": record.get("reason"),
        "turns": record.get("turns"),
        "tool_calls": len(record.get("evidence") or []),
        "tokens_in_estimated": record.get("tokens_in", 0),
        "tokens_out_estimated": record.get("tokens_out", 0),
        "tokens_total_estimated": (
            record.get("tokens_in", 0) + record.get("tokens_out", 0)
        ),
        "model_equivalent_cost_usd_estimated": record.get("cost_usd", 0),
        "actual_api_cost_usd": 0.0,
        "code_check_passed": passed,
        "code_check_failures": failures,
        "stopped_by": record.get("stopped_by"),
        "guardrails_fired": record.get("guardrails_fired") or [],
    }


def _suite_metrics(results, cap):
    records = [row["record"] for row in results]
    turns = [record["turns"] for record in records]
    distribution = Counter(turns)
    passed = sum(1 for row in results if row["passed"])
    return {
        "step_cap": cap,
        "trials": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "median_turns": statistics.median(turns) if turns else None,
        "worst_case_turns": max(turns) if turns else None,
        "turn_distribution": {
            str(turn): distribution[turn] for turn in sorted(distribution)
        },
        "hit_step_cap": sum(
            record.get("stopped_by") == "step_cap" for record in records
        ),
        "tokens_in_estimated": sum(record["tokens_in"] for record in records),
        "tokens_out_estimated": sum(record["tokens_out"] for record in records),
        "tokens_total_estimated": sum(
            record["tokens_in"] + record["tokens_out"] for record in records
        ),
        "model_equivalent_cost_usd_estimated": round(
            sum(record["cost_usd"] for record in records), 6
        ),
        "actual_api_cost_usd": 0.0,
    }


def _read_results():
    if not os.path.exists(RESULTS_PATH):
        return {
            "backend": "scripted",
            "actual_api_cost_usd": 0.0,
            "measurement_note": (
                "Scripted token counts and model-equivalent costs are "
                "deterministic estimates, not measured API usage."
            ),
        }
    with open(RESULTS_PATH, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("d7_results.json must contain a JSON object")
    return payload


def _write_results(payload):
    with open(RESULTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def run_experiment(write_results=True):
    original_backend = config.BACKEND
    original_problem = config.PROBLEM
    original_cap = config.MAX_TURNS
    original_script = backends.SCRIPTS[CASE_ID]
    real_duplicate_check = Guardrails.check_duplicate
    expected = load_key(PROBLEM)[CASE_ID]

    config.BACKEND = "scripted"
    config.PROBLEM = PROBLEM

    try:
        # 1. Normal behaviour with the complete working agent.
        baseline = run_case(CASE_ID, problem=PROBLEM)

        # 2. The faulty model behaviour is held constant. With X present,
        #    the repeated action is identified and stopped explicitly.
        backends.SCRIPTS[CASE_ID] = _looping_script(CASE_ID)
        fault_caught = run_case(CASE_ID, problem=PROBLEM)

        # 3. Delete only X. The same repeated behaviour now continues,
        #    spends more, raises no exception and still reaches the answer.
        Guardrails.check_duplicate = lambda self, tool, args: None
        minus_x = run_case(CASE_ID, problem=PROBLEM)

        # 4. Put X and the working script back before the restoration run.
        Guardrails.check_duplicate = real_duplicate_check
        backends.SCRIPTS[CASE_ID] = original_script
        restored = run_case(CASE_ID, problem=PROBLEM)

        # 5. Whole-set evidence for the cap. Cap 30 is the loose-control
        #    comparator; cap 8 is the configured control being defended.
        config.MAX_TURNS = original_cap
        restored_results, _ = run_set(load_cases(PROBLEM), problem=PROBLEM)
        restored_suite = _suite_metrics(restored_results, original_cap)

        config.MAX_TURNS = 30
        loose_results, _ = run_set(load_cases(PROBLEM), problem=PROBLEM)
        loose_suite = _suite_metrics(loose_results, 30)
    finally:
        Guardrails.check_duplicate = real_duplicate_check
        backends.SCRIPTS[CASE_ID] = original_script
        config.MAX_TURNS = original_cap
        config.PROBLEM = original_problem
        config.BACKEND = original_backend

    baseline_metrics = _run_metrics(baseline, expected)
    caught_metrics = _run_metrics(fault_caught, expected)
    minus_metrics = _run_metrics(minus_x, expected)
    restored_metrics = _run_metrics(restored, expected)
    spend_ratio = (
        minus_metrics["tokens_total_estimated"]
        / max(1, baseline_metrics["tokens_total_estimated"])
    )

    evidence = {
        "failure": "loop_control_duplicate_action",
        "case_id": CASE_ID,
        "working_agent_minus_x": (
            "Guardrails.check_duplicate action-memory check"
        ),
        "monitoring_that_detected_it": [
            "per-run turns",
            "per-run token estimate",
            "per-run model-equivalent cost estimate",
            "tool trace",
            "stopped_by and guardrails_fired",
        ],
        "working_agent": baseline_metrics,
        "fault_injected_guard_present": caught_metrics,
        "minus_x": minus_metrics,
        "after_restoration": restored_metrics,
        "minus_x_token_ratio_vs_working": round(spend_ratio, 3),
        "complete_evaluation_set": {
            "restored_configured_cap": restored_suite,
            "loose_cap_comparator": loose_suite,
            "cap_rationale": (
                "The configured cap of %d is %d turns above the longest "
                "legitimate scripted run of %d; cap 30 changes no legitimate "
                "result and would be too loose to be a meaningful control."
                % (original_cap,
                   original_cap - restored_suite["worst_case_turns"],
                   restored_suite["worst_case_turns"])
            ),
        },
        "layer_judgement": {
            "correct_layer": "code / loop control",
            "why": (
                "Only deterministic code can remember exact prior actions "
                "and identify an identical action at the moment it repeats."
            ),
            "why_not_prompt": (
                "The model is the component that forgot; a reminder cannot "
                "provide an enforceable cross-turn memory guarantee."
            ),
            "why_not_tool_interface": (
                "The tool call and return are valid; the fault is repeated "
                "orchestration, not an ambiguous tool contract."
            ),
        },
    }

    if write_results:
        payload = _read_results()
        payload["loop_control_failure"] = evidence
        _write_results(payload)
    return evidence


def _print_run(label, metrics):
    print("  %-31s turns=%s  calls=%s  tokens(est.)=%s  est.cost=US$%.6f"
          % (label, metrics["turns"], metrics["tool_calls"],
             metrics["tokens_total_estimated"],
             metrics["model_equivalent_cost_usd_estimated"]))
    print("  %-31s decision=%s  pass=%s  stopped_by=%s"
          % ("", metrics["decision"], metrics["code_check_passed"],
             metrics["stopped_by"]))


def main():
    evidence = run_experiment(write_results=True)
    print()
    print("D7 FAILURE 1 — LOOP CONTROL (scripted, no API cost)")
    print("=" * 68)
    _print_run("working agent", evidence["working_agent"])
    _print_run("fault + guard present",
               evidence["fault_injected_guard_present"])
    _print_run("working agent minus X", evidence["minus_x"])
    _print_run("after restoration", evidence["after_restoration"])
    print()
    suite = evidence["complete_evaluation_set"]["restored_configured_cap"]
    print("  complete set: %d/%d passed; median=%s; worst=%s; cap hits=%s"
          % (suite["passed"], suite["trials"], suite["median_turns"],
             suite["worst_case_turns"], suite["hit_step_cap"]))
    print("  turn distribution:", suite["turn_distribution"])
    print("  token ratio, minus X / working: %.3fx"
          % evidence["minus_x_token_ratio_vs_working"])
    print("  actual API cost: US$0.000000 (scripted backend)")
    print("  evidence written to %s" % RESULTS_PATH)
    print()


if __name__ == "__main__":
    main()
