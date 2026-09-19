#!/usr/bin/env python3
"""
PE6201 · A2 — D7 FAILURE 2: tool-interface ablation
====================================================================
    python3 demo_tool_failure.py

This is a controlled "working agent minus X" experiment on CLM-8894.
X is the date-bound contract of get_preauthorisation: a returned approval
must cover the claim's date_of_service. The minus-X tool accepts the same
member and procedure but ignores the required date, so expired PA-5640 is
returned as if it authorised treatment on 2026-09-09.

The same scripted model behaviour is used on both sides. With the working
tool, the unsupported approval is rejected and the agent requests a current
pre-authorisation. With X deleted, the false tool evidence supports an
incorrect approval. Restoring X restores the correct outcome.

The experiment forces the SCRIPTED backend, makes no network call, and
updates only d7_results.json.
====================================================================
"""
import copy
import json
import os
import statistics
from collections import Counter

import backends
import config
import tools
from agent import run_case
from harness import code_check, load_cases, load_key, run_set


CASE_ID = "CLM-8894"
PROBLEM = "A"
RESULTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "d7_results.json")


def _diagnostic_script():
    """One fixed agent path whose branch is determined by tool evidence.

    The agent first attempts the approval a positive pre-authorisation result
    appears to support. If the working tool returns None, runtime validation
    rejects that action/final and the last move records the correct request.
    If the minus-X tool returns expired PA-5640, the incorrect approval is
    accepted and execution ends before the fallback move.
    """
    steps = copy.deepcopy(backends.SCRIPTS[CASE_ID][:4])
    steps.extend([
        {
            "thought": (
                "A matching pre-authorisation record was returned; approve "
                "the line using that tool evidence."
            ),
            "calls": [[
                "issue_decision_letter",
                {
                    "claim_id": CASE_ID,
                    "decision": "approve_in_principle",
                    "line_dispositions": [{
                        "code": "29881",
                        "amount": 1950,
                        "status": "covered",
                        "preauth": "PA-5640",
                    }],
                },
            ]],
        },
        {
            "thought": "Return the approval supported by the tool result.",
            "final": {
                "decision": "approve_in_principle",
                "reason": (
                    "Line 29881 is covered under PA-5640; approved_total "
                    "1950 and refused_total 0."
                ),
                "lines": [{
                    "code": "29881",
                    "amount": 1950,
                    "status": "covered",
                    "preauth": "PA-5640",
                }],
                "approved_total": 1950,
                "refused_total": 0,
            },
        },
        {
            "thought": (
                "The approval was rejected because no authorisation is valid "
                "on the service date; request a current one."
            ),
            "final": {
                "decision": "request_document",
                "missing": (
                    "current pre-authorisation for line 29881, valid on "
                    "2026-09-09"
                ),
                "reason": (
                    "PA-5640 ended on 2026-05-31 and does not authorise "
                    "service on 2026-09-09; request a current "
                    "pre-authorisation for line 29881."
                ),
            },
        },
    ])
    return steps


def _minus_date_bound_contract(member_id, procedure_code,
                               date_of_service=None):
    """Deliberately broken tool: required date is accepted but ignored."""
    for preauth in tools._load("A", "preauthorisations"):
        if (preauth["member_id"] == member_id
                and preauth["procedure_code"] == procedure_code):
            return preauth
    return None


def _preauthorisation_result(record):
    matches = [
        entry.get("result") for entry in record.get("tool_trace") or []
        if entry.get("tool") == "get_preauthorisation"
    ]
    return matches[-1] if matches else None


def _run_metrics(record, expected):
    passed, failures = code_check(record, expected)
    return {
        "decision": record.get("decision"),
        "reason": record.get("reason"),
        "preauthorisation_result": _preauthorisation_result(record),
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
        "final_rejections": record.get("final_rejections"),
        "rejected_actions": len(record.get("rejected_actions") or []),
    }


def _suite_metrics(results):
    records = [row["record"] for row in results]
    turns = [record["turns"] for record in records]
    distribution = Counter(turns)
    passed = sum(1 for row in results if row["passed"])
    failures = [
        {
            "case_id": row["case_id"],
            "trial": row["trial"],
            "decision": row["record"].get("decision"),
            "stopped_by": row["record"].get("stopped_by"),
            "code_check_failures": row["fails"],
        }
        for row in results if not row["passed"]
    ]
    return {
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
        "failures": failures,
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
    original_script = backends.SCRIPTS[CASE_ID]
    working_tool = tools.REGISTRY[PROBLEM]["get_preauthorisation"]
    expected = load_key(PROBLEM)[CASE_ID]

    config.BACKEND = "scripted"
    config.PROBLEM = PROBLEM
    backends.SCRIPTS[CASE_ID] = _diagnostic_script()

    try:
        # Working interface: member + procedure + service-date validity.
        working = run_case(CASE_ID, problem=PROBLEM)

        # Delete X only: the date argument remains accepted so every other
        # component and scripted move stays identical, but its constraint is
        # no longer enforced by the tool boundary.
        tools.REGISTRY[PROBLEM]["get_preauthorisation"] = (
            _minus_date_bound_contract
        )
        minus_x = run_case(CASE_ID, problem=PROBLEM)

        # Restore X for an explicit third run.
        tools.REGISTRY[PROBLEM]["get_preauthorisation"] = working_tool
        restored = run_case(CASE_ID, problem=PROBLEM)

        # Whole-set causal comparison uses the team's normal scripts.
        backends.SCRIPTS[CASE_ID] = original_script
        working_results, _ = run_set(load_cases(PROBLEM), problem=PROBLEM)
        working_suite = _suite_metrics(working_results)

        tools.REGISTRY[PROBLEM]["get_preauthorisation"] = (
            _minus_date_bound_contract
        )
        broken_results, _ = run_set(load_cases(PROBLEM), problem=PROBLEM)
        broken_suite = _suite_metrics(broken_results)

        tools.REGISTRY[PROBLEM]["get_preauthorisation"] = working_tool
        restored_results, _ = run_set(load_cases(PROBLEM), problem=PROBLEM)
        restored_suite = _suite_metrics(restored_results)
    finally:
        tools.REGISTRY[PROBLEM]["get_preauthorisation"] = working_tool
        backends.SCRIPTS[CASE_ID] = original_script
        config.PROBLEM = original_problem
        config.BACKEND = original_backend

    evidence = {
        "failure": "tool_interface_preauthorisation_date_constraint",
        "case_id": CASE_ID,
        "working_agent_minus_x": (
            "required date_of_service validity constraint in "
            "get_preauthorisation"
        ),
        "case_facts": {
            "procedure_code": "29881",
            "date_of_service": "2026-09-09",
            "expired_preauthorisation": "PA-5640",
            "expired_on": "2026-05-31",
            "expected_decision": "request_document",
        },
        "working_agent": _run_metrics(working, expected),
        "minus_x": _run_metrics(minus_x, expected),
        "after_restoration": _run_metrics(restored, expected),
        "complete_evaluation_set": {
            "working_agent": working_suite,
            "minus_x": broken_suite,
            "after_restoration": restored_suite,
        },
        "layer_judgement": {
            "correct_layer": "tool interface",
            "why": (
                "Whether an authorisation covers a supplied service date is "
                "deterministic data logic and must be guaranteed once at the "
                "source boundary for every caller."
            ),
            "why_not_prompt": (
                "A prompt would ask each stochastic model to duplicate date "
                "validation and to distrust a positive tool result."
            ),
            "why_not_loop_control": (
                "The run is finite and every action is syntactically valid; "
                "step, budget and duplication guards cannot determine whether "
                "a pre-authorisation is expired."
            ),
        },
    }

    if write_results:
        payload = _read_results()
        payload["tool_interface_failure"] = evidence
        _write_results(payload)
    return evidence


def _print_run(label, metrics):
    print("  %-24s turns=%s  tokens(est.)=%s  est.cost=US$%.6f"
          % (label, metrics["turns"], metrics["tokens_total_estimated"],
             metrics["model_equivalent_cost_usd_estimated"]))
    print("  %-24s decision=%s  pass=%s  stopped_by=%s"
          % ("", metrics["decision"], metrics["code_check_passed"],
             metrics["stopped_by"]))
    print("  %-24s preauthorisation_result=%s"
          % ("", metrics["preauthorisation_result"]))


def main():
    evidence = run_experiment(write_results=True)
    print()
    print("D7 FAILURE 2 — TOOL INTERFACE (scripted, no API cost)")
    print("=" * 68)
    _print_run("working agent", evidence["working_agent"])
    _print_run("working agent minus X", evidence["minus_x"])
    _print_run("after restoration", evidence["after_restoration"])
    print()
    suites = evidence["complete_evaluation_set"]
    for label in ("working_agent", "minus_x", "after_restoration"):
        suite = suites[label]
        print("  %-24s %d/%d passed (%.1f%%), est.cost=US$%.6f"
              % (label, suite["passed"], suite["trials"],
                 100 * suite["pass_rate"],
                 suite["model_equivalent_cost_usd_estimated"]))
    print("  actual API cost: US$0.000000 (scripted backend)")
    print("  evidence written to %s" % RESULTS_PATH)
    print()


if __name__ == "__main__":
    main()
