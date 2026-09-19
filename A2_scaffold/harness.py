"""
PE6201 · A2 scaffold — THE HARNESS  (D4, D5)
====================================================================
Load the answer key, run cases, grade them, report.

--------------------------------------------------------------------
THE TWO KINDS OF CHECK, AND WHY YOU NEED BOTH

A CODE CHECK compares the answer with your answer key.
    decision == expected_decision
    No model, no person, no opinion. Deterministic, free, instant.
    It is what produces the number.

A JUDGEMENT CHECK has someone read the record and decide.
    "Does the reason actually name the band and the window?"
    A PERSON can do it. A SECOND MODEL can do it. Same kind of check -
    the only difference is who grades. (This is what A1 called L1/L2.
    The names never mattered; the difference does.)

Why both: with three possible outcomes, a coin-flip scores 33% on the
code check alone. An agent can reach the right decision for the wrong
reason and the code check will not notice. `must_record` and `trigger`
are what stop a lucky run counting as a good one.

`prepare_judgement_check` below does NOT grade. It builds the queue a
human or a second model works through. Automating the judgement is
your design decision - and if you use a model, say so, because a model
grading a model is a claim that needs defending.
====================================================================
"""
import json
import os
import statistics

import config
from agent import run_case


# =====================================================================
# LOADING
# =====================================================================
def load_key(problem=None):
    """The answer key. YOURS, not ours, once you have extended it.

    Starts as 15 rows and grows by one per case you write. Same file
    throughout - the harness joins on case_id and does not care which
    rows we shipped and which you added.
    """
    problem = problem or config.PROBLEM
    path = os.path.join(config.data_root(),
                        "expected_outcomes_%s.json" % problem)
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    return {r["case_id"]: r for r in rows}


def load_cases(problem=None):
    """Every case id in the work queue, in file order."""
    problem = problem or config.PROBLEM
    table, field = (("referrals", "referral_id") if problem == "B"
                    else ("claims", "claim_id"))
    path = os.path.join(config.data_root(), "data_%s" % problem,
                        "%s.json" % table)
    with open(path, encoding="utf-8") as fh:
        return [r[field] for r in json.load(fh)]


# =====================================================================
# THE CODE CHECK
# =====================================================================
def code_check(record, expected):
    """Deterministic comparison. Returns (passed, [reasons it failed]).

    Note what is compared and what is NOT. The DECISION and its single
    TRIGGER are compared. The wording is not, the turn count is not, the
    cost is not - two agents can both be right and cost very different
    amounts, which is the subject of D6.
    """
    fails = []

    if record.get("decision") != expected.get("expected_decision"):
        fails.append("decision %r, expected %r"
                     % (record.get("decision"), expected.get("expected_decision")))

    # An escalation must escalate FOR THE RIGHT REASON. A run that
    # reaches the right outcome by the wrong trigger is not a pass - it
    # got there by luck and it will not get there next time.
    if expected.get("trigger"):
        if record.get("trigger") != expected["trigger"]:
            fails.append("trigger %r, expected %r"
                         % (record.get("trigger"), expected["trigger"]))

    # A booking must book the RIGHT slot. Problem B only.
    if expected.get("booked"):
        got = record.get("booked") or {}
        for field in ("clinic", "date", "time"):
            if got.get(field) != expected["booked"][field]:
                fails.append("booked.%s %r, expected %r"
                             % (field, got.get(field), expected["booked"][field]))

    if not record.get("reason"):
        fails.append("decision record has no reason")

    # Problem A approvals are machine-checkable beyond the final label.
    # Validate the evidence trace so a lucky decision cannot pass after
    # skipping a required lookup or the gated action.
    if (record.get("case_id", "").startswith("CLM-")
            and record.get("decision") == "approve_in_principle"):
        trace = record.get("tool_trace") or []
        successful_trace = [
            entry for entry in trace
            if not (isinstance(entry.get("result"), dict)
                    and entry["result"].get("error"))
        ]
        names = [entry.get("tool") for entry in successful_trace]
        for required in ("lookup_policy", "lookup_hospital",
                         "check_duplicate_claim"):
            if names.count(required) != 1:
                fails.append("%s was not called exactly once" % required)

        claims = [e for e in successful_trace if e.get("tool") == "get_claim"]
        claim = claims[0].get("result") if claims else None
        coverage = [
            e for e in successful_trace if e.get("tool") == "check_coverage"
        ]
        if claim:
            expected_codes = sorted(line["code"] for line in claim.get("lines", []))
            checked_codes = sorted(
                e.get("args", {}).get("code") for e in coverage
                if e.get("args", {}).get("code") is not None
            )
            if checked_codes != expected_codes:
                fails.append("coverage was not checked exactly once for every line")

            coverage_by_code = {
                e.get("args", {}).get("code"): e.get("result") or {}
                for e in coverage
            }
            approved_total = sum(
                line["amount"] for line in claim.get("lines", [])
                if not coverage_by_code.get(line["code"], {}).get("excluded")
            )
            refused_total = sum(
                line["amount"] for line in claim.get("lines", [])
                if coverage_by_code.get(line["code"], {}).get("excluded")
            )
            if record.get("approved_total") != approved_total:
                fails.append("approved_total is inconsistent with line results")
            if record.get("refused_total", 0) != refused_total:
                fails.append("refused_total is inconsistent with line results")
            final_lines = record.get("lines", [])
            final_line_codes = sorted(
                item.get("code") for item in final_lines
                if item.get("code") is not None
            )
            if final_line_codes != expected_codes:
                fails.append("lines do not contain every claim line exactly once")
            else:
                claim_by_code = {
                    line["code"]: line for line in claim.get("lines", [])
                }
                final_by_code = {line["code"]: line for line in final_lines}
                for code in expected_codes:
                    source_line = claim_by_code[code]
                    final_line = final_by_code[code]
                    coverage_result = coverage_by_code.get(code, {})
                    if final_line.get("amount") != source_line.get("amount"):
                        fails.append("line %s has the wrong amount" % code)
                    expected_status = (
                        "not_covered"
                        if coverage_result.get("excluded") else "covered"
                    )
                    if final_line.get("status") != expected_status:
                        fails.append(
                            "line %s status is not %s" % (code, expected_status)
                        )
                    if (coverage_result.get("excluded")
                            and final_line.get("exclusion")
                            != coverage_result.get("exclusion_rule")):
                        fails.append("line %s has the wrong exclusion" % code)
        else:
            fails.append("get_claim result is missing from tool_trace")

        for entry in coverage:
            result = entry.get("result") or {}
            code = entry.get("args", {}).get("code")
            if result.get("missing_documents") is None:
                fails.append("document check was not completed for line %s" % code)
            elif result.get("missing_documents"):
                fails.append("line %s has missing required documents" % code)
            if result.get("requires_preauth"):
                matching = [
                    e for e in successful_trace
                    if e.get("tool") == "get_preauthorisation"
                    and e.get("args", {}).get("procedure_code") == code
                ]
                if not matching or matching[-1].get("result") is None:
                    fails.append("valid pre-authorisation is missing for line %s" % code)

        if names.count("issue_decision_letter") != 1:
            fails.append("issue_decision_letter was not called exactly once")
        else:
            issue = next(
                entry for entry in successful_trace
                if entry.get("tool") == "issue_decision_letter"
            )
            prerequisite_turns = [
                entry.get("turn", 0) for entry in successful_trace
                if entry.get("tool") in (
                    "lookup_policy", "lookup_hospital", "check_duplicate_claim",
                    "check_coverage", "get_preauthorisation"
                )
            ]
            if prerequisite_turns and issue.get("turn", 0) <= max(prerequisite_turns):
                fails.append("issue_decision_letter ran before all checks completed")
        gate_passed = any(
            event.get("guardrail") == "gate_passed"
            for event in record.get("guardrails_fired", [])
        )
        if not gate_passed:
            fails.append("irreversible action did not pass its autonomy gate")

    return (not fails), fails


# =====================================================================
# THE JUDGEMENT CHECK
# =====================================================================
def prepare_judgement_check(record, expected):
    """Build ONE item for a human - or a second model - to rule on.

    This deliberately does not decide anything. `must_record` items are
    written in English and a substring match would be theatre, not a
    check. Someone reads the reason and answers yes or no per item.
    """
    return {
        "case_id": record["case_id"],
        "decision": record.get("decision"),
        "reason": record.get("reason", ""),
        "must_record": expected.get("must_record", []),
        "verdict": None,          # <- a person or a second model fills this
        "graded_by": None,        # <- "person: Priya" | "model: <name>"
    }


# =====================================================================
# RUNNING THE SET
# =====================================================================
def run_set(case_ids=None, problem=None, trials_for=None, verbose=False):
    """Run cases and grade them.

    `trials_for(case_id) -> int` decides how many trials each case gets.
    D4: ordinary cases get ONE trial; NEGATIVE cases get THREE, because
    negatives are the ones that flip between runs and a single trial
    cannot tell a real refusal from a lucky one.
    """
    problem = problem or config.PROBLEM
    key = load_key(problem)
    case_ids = case_ids or load_cases(problem)
    trials_for = trials_for or (lambda cid: 3 if _is_negative(key.get(cid)) else 1)

    results, judgement_queue = [], []

    for cid in case_ids:
        expected = key.get(cid)
        if expected is None:
            # check_my_data.py catches this before you get here. If you
            # are seeing it, run the checker.
            print("  SKIP %s - no label in the answer key" % cid)
            continue

        for trial in range(1, trials_for(cid) + 1):
            record = run_case(cid, problem=problem, verbose=verbose)
            passed, fails = code_check(record, expected)
            results.append({"case_id": cid, "trial": trial, "passed": passed,
                            "fails": fails, "record": record,
                            "family": expected.get("family")})
            if trial == 1:
                judgement_queue.append(prepare_judgement_check(record, expected))

    return results, judgement_queue


def _is_negative(expected):
    """A negative case is one whose correct outcome is anything except
    the act - so, an ask or an escalate."""
    if not expected:
        return False
    return expected.get("expected_decision") in (
        "escalate", "request_document", "request_information")


# =====================================================================
# REPORTING
# =====================================================================
def report(results):
    """The result table. EVERY pass rate is printed with its trial count,
    because a pass rate without one is not a measurement."""
    _print_final_results(results)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    turns = [r["record"]["turns"] for r in results]
    cost = sum(r["record"]["cost_usd"] for r in results)

    print()
    print("=" * 68)
    print("  RESULTS   %d of %d trials passed   (%.0f%%)"
          % (passed, total, 100.0 * passed / total if total else 0))
    print("=" * 68)
    print("  trials              %d" % total)
    print("  median turns        %s" % (statistics.median(turns) if turns else "-"))
    print("  worst case turns    %s" % (max(turns) if turns else "-"))
    print("  hit the step cap    %d"
          % sum(1 for r in results if r["record"]["stopped_by"] == "step_cap"))
    print("  total cost          US$%.4f   (%s backend)"
          % (cost, results[0]["record"]["backend"] if results else "-"))
    print()

    failures = [r for r in results if not r["passed"]]
    if failures:
        print("  FAILED TRIALS - each one is either a bug or a wrong label:")
        for r in failures:
            print("    %-12s trial %d  [%s]" % (r["case_id"], r["trial"],
                                                r["family"]))
            for f in r["fails"]:
                print("        %s" % f)
        print()
        print("  Before you fix the agent, ask whether the LABEL is right.")
        print("  Test: could you justify the label to someone who had never")
        print("  seen your agent's output, using only Appendix A's routing")
        print("  table? If yes, the agent is wrong. If no, the label is.")
    else:
        print("  Every trial passed the code check.")
        print("  That is HALF the check. Work through the judgement queue")
        print("  before you believe this number.")
    print()
    return {"trials": total, "passed": passed,
            "pass_rate": passed / total if total else 0.0,
            "median_turns": statistics.median(turns) if turns else None,
            "cost_usd": cost}


def _print_final_results(results):
    """Print one deterministic final result per case before the aggregate.

    Negative cases have three trials. Their individual pass/fail status is
    summarised on one line while the first trial supplies the displayed final
    record; on the scripted backend all three replays are identical.
    """
    grouped = {}
    for row in results:
        grouped.setdefault(row["case_id"], []).append(row)

    print()
    print("=" * 68)
    print("  FINAL RESULTS - one final decision record per case")
    print("=" * 68)
    for case_id, rows in grouped.items():
        record = rows[0]["record"]
        details = []
        if record.get("trigger"):
            details.append("trigger=%s" % record["trigger"])
        if record.get("missing"):
            details.append("missing=%s" % record["missing"])
        if record.get("approved_total") is not None:
            details.append("approved=%s" % record["approved_total"])
        if record.get("refused_total") is not None:
            details.append("refused=%s" % record["refused_total"])
        passed = sum(1 for row in rows if row["passed"])
        details.append("code_check=%d/%d" % (passed, len(rows)))
        details.append("turns=%s" % record.get("turns", "-"))
        print("  %-10s %-22s %s" % (
            case_id,
            record.get("decision", "<no decision>"),
            " | ".join(details),
        ))
