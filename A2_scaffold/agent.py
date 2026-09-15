"""
PE6201 · A2 scaffold — THE AGENT LOOP  (D1)
====================================================================
    thought -> action -> observation -> repeat -> final

That is the whole of ReAct, and it is hand-rolled here on purpose. No
framework owns your loop: when it misbehaves you need to be able to
read the twelve lines that did it.

WHAT MAKES THIS AN AGENT RATHER THAN A WORKFLOW: the number of steps is
decided by the DATA, not by you. A one-line claim with a live policy is
a short run. A four-line claim with a pre-authorisation to chase is a
long one. You did not write that branch - the record did.

--------------------------------------------------------------------
INSTRUMENTATION IS NOT OPTIONAL

Every run records turns, tokens, cost, every tool call and every
guardrail event. D6's cost model and D7's loop failure both need
numbers that were captured WHILE THE RUN HAPPENED. A team that adds
instrumentation afterwards has to run the whole battery again.

You cannot report a failure you had no way of noticing.
====================================================================
"""
import json
import time

import config
import prompt
import tools
from backends import make_backend
from guardrails import Guardrails, GuardrailStop

# Raised from 4 to 6 after live evidence (dev_v1_v2_compare.py, v2,
# CLM-8842 trial 1): the stricter validation added for D2(b) (required
# trigger/missing, evidence-checked escalate triggers) catches more real
# mistakes, which is the point, but each catch spends one of this budget -
# and a legitimate multi-step Problem A completion (lookup_policy ->
# hospital -> duplicate -> coverage x N -> preauth -> issue) can need two
# or three corrective round-trips even from a MODEL THAT EVENTUALLY GETS
# IT RIGHT. Observed: the same case failed here once (4 rejections, capped)
# and succeeded on an immediate retry (2 rejections) - not a code bug, a
# retry-budget bug. Each round-trip costs a few hundred tokens; the fix is
# cheaper than the false failures it was causing.
MAX_FINAL_REJECTIONS = 6

# A decision LABEL is not a tool, but a weak model sometimes tries to "call"
# one - {"calls": [["request_document", {...}]]} - instead of putting it in
# {"final": {"decision": ...}}. Left alone this burns a turn on an unknown-
# tool error, then a second identical attempt trips the duplicate-action
# guardrail, and the run ends in a generic escalate with no trigger - a
# guardrail-shaped failure that is really a shape-confusion in the model's
# output. Caught here it costs a corrective message instead of the run.
DECISION_LABELS = {
    "approve_in_principle", "request_document", "escalate",
    "request_information", "book",
}

# THE D2(b) v1/v2 TOGGLE. True = the current, improved validation (required
# trigger/missing, evidence-checked escalate triggers, the decision-label
# corrective path below). False reproduces the ORIGINAL scaffold's runtime
# behaviour exactly, so dev_v1_v2_compare.py can run both sides from this
# one codebase instead of from separately-generated results whose code
# could have silently drifted. Every other run in this repository (grading,
# demos, guardrail_tests.py) leaves this at True - only
# dev_v1_v2_compare.py's v1 pass sets it False, and only for its own calls.
STRICT_VALIDATION = True


def run_case(case_id, problem=None, approve=None, verbose=False,
            prompt_version="v2"):
    """Run ONE case from a clean state and return the decision record.

    ISOLATION (D4): everything this function needs is created inside it.
    No case may depend on a previous one having run - so no module-level
    counters, no shared guardrail object, no leftover transcript.

    `prompt_version="v1"` is ONLY for dev_v1_v2_compare.py: it selects the
    original prompt text (prompt.RULES_V1) AND switches off the validation
    added on top of it (see STRICT_VALIDATION above), so a v1 run
    reproduces the original scaffold's behaviour end to end. Every other
    caller should leave this at the default.
    """
    global STRICT_VALIDATION
    STRICT_VALIDATION = (prompt_version != "v1")

    problem = problem or config.PROBLEM
    started = time.time()

    guards = Guardrails(config.MAX_TURNS, config.MAX_TOKENS_PER_RUN,
                        config.AUTONOMY)
    # WHAT THE MODEL IS TOLD. On the scripted backend these are ignored -
    # the moves are pre-written, so no prompt is ever sent. On the live
    # backend this IS the experiment D2(b) measures: the descriptors and
    # the routing rules, assembled by prompt.build_system_prompt().
    #     python3 run_eval.py --prompt      to see the exact text
    backend = make_backend(
        case_id,
        tool_descriptors=[tools.DESCRIPTORS[n] for n in tools.REGISTRY[problem]
                          if n in tools.DESCRIPTORS],
        system_prompt=prompt.build_system_prompt(problem, version=prompt_version))

    transcript = [{
    "role": "user",
    "content": (
        "Process case_id %r for Problem %s. "
        "Start by calling the initial retrieval tool using this exact case_id. "
        "Use only values returned by tools; never invent IDs or arguments. "
        "Respond with exactly one JSON object and no Markdown."
        % (case_id, problem)
    ),
        }]      # what the model would see
    evidence = []        # every tool actually called, in order
    tool_trace = []      # arguments and results, used to validate conclusions
    rejected_actions = []

    # TURNS ARE TOOL-CALLING TURNS. The concluding move - where the agent
    # writes its decision record - is bookkeeping, not a turn. This is the
    # same convention Appendix A uses: CLM-8842 is "turns": 4. Our trace has
    # nine tool calls after adding the required duplicate check; the gated
    # action is a turn like any other and
    # the write-up afterwards is not. Count them any other way and your
    # D2(c) arithmetic stops agreeing with the brief.
    turns = 0
    iterations = 0       # loop-safety only; never reported
    final_rejections = 0
    tokens_in = tokens_out = 0
    stopped_by = None

    # Scripted runs auto-approve for reproducibility. Live confirm-mode
    # runs ask the operator at the irreversible action itself.
    if approve is None:
        if backend.name == "scripted":
            approve = lambda action, payload: True
        elif config.AUTONOMY == "confirm":
            approve = _confirm_in_terminal

    try:
        while True:
            iterations += 1
            if iterations > config.MAX_TURNS * 3:
                guards.stop(
                    "iteration_cap",
                    "loop exceeded %d model iterations" % (config.MAX_TURNS * 3),
                )

            move = backend.next_move(transcript)
            ti, to = backend.token_estimate(transcript)
            tokens_in, tokens_out = tokens_in + ti, tokens_out + to
            guards.check_budget(tokens_in + tokens_out)

            if verbose:
                label = ("conclude" if "final" in move else "turn %d" % (turns + 1))
                print("  %-9s · %s" % (label, move.get("thought", "")))

            # ---- conclude -------------------------------------------
            if "final" in move:
                problems = _validate_final(problem, move["final"], tool_trace)
                if problems:
                    final_rejections += 1
                    if verbose:
                        print("       FINAL REJECTED - required evidence is missing:")
                        for problem_text in problems:
                            print("         - %s" % problem_text)
                    transcript.append({
                        "role": "assistant",
                        "content": json.dumps(move, ensure_ascii=False),
                    })
                    transcript.append({
                        "role": "user",
                        "content": (
                            "FINAL REJECTED by the runtime. Do not repeat the "
                            "same final answer. Complete the missing steps, using "
                            "tool calls where required: " + "; ".join(problems)
                        ),
                    })
                    if final_rejections >= MAX_FINAL_REJECTIONS:
                        guards.stop(
                            "invalid_final_retry_cap",
                            "model produced %d unsupported final answers"
                            % final_rejections,
                        )
                    continue
                record = dict(move["final"])
                break

            # ---- act: one turn may carry SEVERAL calls ---------------
            turns += 1
            guards.check_turns(turns)

            # Only calls INDEPENDENT of each other belong in one turn.
            # A dependency chain cannot be shortened by running things at
            # once - that is why Problem B saves less than Problem A.
            calls = move.get("calls") or [(move["tool"], move["args"])]
            observations = []

            for name, args in calls:
                if STRICT_VALIDATION and name in DECISION_LABELS:
                    result = {
                        "error": "not_a_tool",
                        "message": (
                            "%r is a DECISION VALUE, not a tool. Do not call "
                            "it. Conclude with "
                            "{\"final\": {\"decision\": %r, ...}} instead."
                            % (name, name)
                        ),
                        "retry_with_corrected_arguments": True,
                    }
                    observations.append({"tool": name, "args": args,
                                         "observation": result})
                    if verbose:
                        print("       %s - NOT A TOOL, decision value misused "
                              "as a call" % name)
                    continue

                guards.check_duplicate(name, args)

                action_problems = _validate_action(
                    problem, name, args, tool_trace
                )
                if action_problems:
                    result = {
                        "error": "action_validation_failed",
                        "message": "; ".join(action_problems),
                        "action_executed": False,
                        "retry_with_corrected_arguments": True,
                    }
                    rejected_actions.append({
                        "turn": turns,
                        "tool": name,
                        "args": args,
                        "problems": action_problems,
                    })
                    observations.append({"tool": name, "args": args,
                                         "observation": result})
                    if verbose:
                        print("       %s - ACTION REJECTED BEFORE GATE" % name)
                        print("         args:")
                        print(_indented_json(args, 11))
                        print("         result:")
                        print(_indented_json(result, 11))
                    continue

                # THE GATE goes in front of the irreversible step only.
                if name == tools.GATED_ACTION.get(problem):
                    if not guards.gate(name, args, approve):
                        raise GuardrailStop(
                            "gate_held",
                            "%s awaits human approval (autonomy=%s)"
                            % (name, config.AUTONOMY))

                try:
                    result = tools.call(problem, name, args)
                except (KeyError, TypeError, ValueError) as error:
                    result = {
                        "error": type(error).__name__,
                        "message": str(error),
                        "retry_with_corrected_arguments": True,
                    }
                evidence.append(name)
                tool_trace.append({"turn": turns, "tool": name, "args": args,
                                   "result": result})
                observations.append({"tool": name, "args": args,
                                     "observation": result})
                if verbose:
                    print("       %s" % name)
                    print("         args:")
                    print(_indented_json(args, 11))
                    print("         result:")
                    print(_indented_json(result, 11))

            transcript.append({"role": "assistant",
                               "content": move.get("thought", "")})
            transcript.append({"role": "user",
                               "content": repr(observations)})

    except GuardrailStop as stop:
        # A LOUD STOP. The record says what halted the run and where, so
        # this never looks like a quiet wrong answer.
        stopped_by = stop.reason
        record = {"decision": "escalate",
                  "reason": "halted by the %s guardrail - %s"
                            % (stop.reason, stop.detail)}

    cost = (tokens_in / 1e6) * config.PRICE_IN + (tokens_out / 1e6) * config.PRICE_OUT

    record.update({
        "case_id": case_id,
        "evidence": evidence,
        "tool_trace": tool_trace,
        "rejected_actions": rejected_actions,
        "turns": turns,
        "model_iterations": iterations,
        "final_rejections": final_rejections,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost, 6),
        "seconds": round(time.time() - started, 3),
        "guardrails_fired": guards.fired,
        "stopped_by": stopped_by,
        "backend": backend.name,
    })
    return record


def _validate_action(problem, name, args, trace):
    """Validate irreversible payloads before asking for approval or acting."""
    if problem != "A" or name != "issue_decision_letter":
        return []

    problems = []
    claims = _successful_trace_for(trace, "get_claim")
    if not claims or not claims[0]["result"]:
        return ["get_claim must succeed before issue_decision_letter"]
    claim = claims[0]["result"]

    if args.get("claim_id") != claim.get("claim_id"):
        problems.append("claim_id does not match the retrieved claim")
    if args.get("decision") not in (
            "approve_in_principle", "request_document", "escalate"):
        problems.append("decision is not one of the three permitted outcomes")
        return problems
    if args.get("decision") != "approve_in_principle":
        return problems

    policy_calls = _successful_trace_for(trace, "lookup_policy")
    hospital_calls = _successful_trace_for(trace, "lookup_hospital")
    duplicate_calls = _successful_trace_for(trace, "check_duplicate_claim")
    coverage_calls = _successful_trace_for(trace, "check_coverage")

    if not policy_calls or not policy_calls[-1]["result"]:
        problems.append("lookup_policy must succeed before approval")
    else:
        policy_result = policy_calls[-1]["result"]
        policy = policy_result["policy"]
        service_date = claim.get("date_of_service")
        if policy.get("status") != "active":
            problems.append("policy is not active")
        if not (policy.get("start_date") <= service_date <= policy.get("end_date")):
            problems.append("date of service is outside policy dates")
        claim_total = sum(line["amount"] for line in claim.get("lines", []))
        if claim_total > policy_result.get("remaining", -1):
            problems.append("claim total exceeds the remaining annual limit")

    if not hospital_calls or not hospital_calls[-1]["result"]:
        problems.append("lookup_hospital must succeed before approval")
    if not duplicate_calls:
        problems.append("check_duplicate_claim must run before approval")
    elif duplicate_calls[-1]["result"] is not None:
        problems.append("claim matches a previously decided claim")

    expected_codes = sorted(line["code"] for line in claim.get("lines", []))
    checked_codes = sorted(
        entry["args"].get("code") for entry in coverage_calls
        if entry["args"].get("code") is not None
    )
    if checked_codes != expected_codes:
        problems.append("coverage must be checked exactly once for every line")

    coverage_by_code = {
        entry["args"].get("code"): entry["result"] or {}
        for entry in coverage_calls
    }
    for code, result in coverage_by_code.items():
        missing = result.get("missing_documents")
        if missing is None:
            problems.append("document check is incomplete for line %s" % code)
        elif missing:
            problems.append(
                "line %s is missing required document(s): %s"
                % (code, ", ".join(missing))
            )
        if result.get("requires_preauth"):
            matching = [
                auth for auth in _successful_trace_for(
                    trace, "get_preauthorisation"
                )
                if auth["args"].get("member_id") == claim.get("member_id")
                and auth["args"].get("procedure_code") == code
                and auth["args"].get("date_of_service")
                == claim.get("date_of_service")
            ]
            if not matching or matching[-1]["result"] is None:
                problems.append("valid pre-authorisation is missing for line %s" % code)

    expected_approved = sum(
        line["amount"] for line in claim.get("lines", [])
        if not coverage_by_code.get(line["code"], {}).get("excluded")
    )
    expected_refused = sum(
        line["amount"] for line in claim.get("lines", [])
        if coverage_by_code.get(line["code"], {}).get("excluded")
    )
    if args.get("lines_resolved") != len(claim.get("lines", [])):
        problems.append(
            "lines_resolved must be %d" % len(claim.get("lines", []))
        )
    if args.get("approved_total") != expected_approved:
        problems.append("approved_total must be %d" % expected_approved)
    if args.get("refused_total", 0) != expected_refused:
        problems.append("refused_total must be %d" % expected_refused)

    return problems


def _validate_final(problem, final, trace):
    """Reject conclusions that are unsupported by the executed tool trace."""
    problems = []
    if not final.get("reason"):
        problems.append("final.reason is required")

    # POKA-YOKE (D2b): an escalate/request without the field a marker needs
    # to grade it is not a smaller mistake than a wrong decision - it is the
    # same mistake, because harness.code_check and the judgement queue both
    # depend on it. Force the retry here instead of grading it as a pass
    # with an empty record. Gated behind STRICT_VALIDATION so v1 (see
    # run_case's prompt_version) reproduces the original scaffold, which
    # never enforced this.
    if STRICT_VALIDATION:
        if final.get("decision") == "escalate" and not final.get("trigger"):
            problems.append(
                "trigger is required and must name the single reason when "
                "decision is escalate"
            )
        if final.get("decision") in ("request_document", "request_information") \
                and not final.get("missing"):
            problems.append(
                "missing is required and must name the exact item when "
                "decision is request_document/request_information"
            )

    if problem != "A":
        return problems

    claims = _trace_for(trace, "get_claim")
    if not claims or not claims[0]["result"]:
        problems.append("get_claim must return the case before conclusion")
        return problems
    claim = claims[0]["result"]

    if final.get("decision") == "escalate":
        if STRICT_VALIDATION:
            problems += _validate_escalate_trigger(claim, final.get("trigger"), trace)
        return problems

    if final.get("decision") != "approve_in_principle":
        return problems

    policy_calls = _successful_trace_for(trace, "lookup_policy")
    hospital_calls = _successful_trace_for(trace, "lookup_hospital")
    duplicate_calls = _successful_trace_for(trace, "check_duplicate_claim")
    coverage_calls = _successful_trace_for(trace, "check_coverage")
    issue_calls = _successful_trace_for(trace, "issue_decision_letter")

    if not policy_calls or not policy_calls[-1]["result"]:
        problems.append("lookup_policy must return the member policy")
    else:
        policy_result = policy_calls[-1]["result"]
        policy = policy_result["policy"]
        service_date = claim.get("date_of_service")
        if policy.get("status") != "active":
            problems.append("the policy is not active; escalate instead")
        if not (policy.get("start_date") <= service_date <= policy.get("end_date")):
            problems.append("date of service is outside policy dates; escalate instead")
        claim_total = sum(line["amount"] for line in claim.get("lines", []))
        if claim_total > policy_result.get("remaining", -1):
            problems.append("claim total exceeds the remaining limit; escalate instead")
    if not hospital_calls or not hospital_calls[-1]["result"]:
        problems.append("lookup_hospital must return the hospital")
    if not duplicate_calls:
        problems.append("check_duplicate_claim must run before approval")
    elif duplicate_calls[-1]["result"] is not None:
        problems.append("the claim is a duplicate and cannot be approved")

    expected_codes = sorted(line["code"] for line in claim.get("lines", []))
    checked_codes = sorted(
        entry["args"].get("code") for entry in coverage_calls
        if entry["args"].get("code") is not None
    )
    if checked_codes != expected_codes:
        problems.append("check_coverage must run exactly once for every claim line")

    for entry in coverage_calls:
        code = entry["args"].get("code")
        result = entry["result"]
        if not result:
            problems.append("check_coverage returned no result for line %s" % code)
            continue
        missing = result.get("missing_documents")
        if missing is None:
            problems.append(
                "repeat check_coverage for line %s with attached_documents" % code
            )
        elif missing:
            problems.append(
                "line %s is missing required document(s): %s"
                % (code, ", ".join(missing))
            )
        if result.get("requires_preauth"):
            matching = [
                auth for auth in _successful_trace_for(
                    trace, "get_preauthorisation"
                )
                if auth["args"].get("member_id") == claim.get("member_id")
                and auth["args"].get("procedure_code") == code
                and auth["args"].get("date_of_service")
                == claim.get("date_of_service")
            ]
            if not matching:
                problems.append(
                    "get_preauthorisation must run for line %s on %s"
                    % (code, claim.get("date_of_service"))
                )
            elif matching[-1]["result"] is None:
                problems.append(
                    "line %s has no valid pre-authorisation; request it instead"
                    % code
                )

    coverage_by_code = {
        entry["args"].get("code"): entry["result"] or {}
        for entry in coverage_calls
    }
    expected_approved = sum(
        line["amount"] for line in claim.get("lines", [])
        if not coverage_by_code.get(line["code"], {}).get("excluded")
    )
    expected_refused = sum(
        line["amount"] for line in claim.get("lines", [])
        if coverage_by_code.get(line["code"], {}).get("excluded")
    )
    if final.get("approved_total") != expected_approved:
        problems.append("final approved_total is inconsistent with line results")
    if final.get("refused_total", 0) != expected_refused:
        problems.append("final refused_total is inconsistent with line results")

    final_lines = final.get("lines", [])
    final_line_codes = sorted(
        item.get("code") for item in final_lines
        if item.get("code") is not None
    )
    if final_line_codes != expected_codes:
        problems.append("final lines must contain every claim line exactly once")
    else:
        claim_by_code = {line["code"]: line for line in claim.get("lines", [])}
        final_by_code = {line["code"]: line for line in final_lines}
        for code in expected_codes:
            source_line = claim_by_code[code]
            final_line = final_by_code[code]
            coverage = coverage_by_code.get(code, {})
            if final_line.get("amount") != source_line.get("amount"):
                problems.append("final line %s has the wrong amount" % code)
            expected_status = (
                "not_covered" if coverage.get("excluded") else "covered"
            )
            if final_line.get("status") != expected_status:
                problems.append(
                    "final line %s status must be %s" % (code, expected_status)
                )
            if coverage.get("excluded"):
                if final_line.get("exclusion") != coverage.get("exclusion_rule"):
                    problems.append(
                        "final line %s must cite exclusion %s"
                        % (code, coverage.get("exclusion_rule"))
                    )

        for auth in _successful_trace_for(trace, "get_preauthorisation"):
            if auth["result"]:
                code = auth["args"].get("procedure_code")
                preauth_id = auth["result"].get("preauth_id")
                final_line = final_by_code.get(code, {})
                if preauth_id and preauth_id not in str(final_line.get("preauth", "")):
                    problems.append(
                        "final line %s must cite pre-authorisation %s"
                        % (code, preauth_id)
                    )

    if len(issue_calls) != 1:
        problems.append("issue_decision_letter must run exactly once before final")
    else:
        issued = issue_calls[0]
        if not issued["result"] or not issued["result"].get("sent"):
            problems.append("issue_decision_letter did not confirm the action")
        if issued["args"].get("decision") != final.get("decision"):
            problems.append("final decision does not match the issued decision")
        if issued["args"].get("lines_resolved") != len(claim.get("lines", [])):
            problems.append("issued lines_resolved does not match the claim")
        for total_name in ("approved_total", "refused_total"):
            if issued["args"].get(total_name, 0) != final.get(total_name, 0):
                problems.append(
                    "final %s does not match issue_decision_letter" % total_name
                )
        prerequisite_calls = (
            policy_calls + hospital_calls + duplicate_calls + coverage_calls
            + _successful_trace_for(trace, "get_preauthorisation")
        )
        latest_prerequisite_turn = max(
            (entry.get("turn", 0) for entry in prerequisite_calls), default=0
        )
        if issued.get("turn", 0) <= latest_prerequisite_turn:
            problems.append(
                "issue_decision_letter must run in a later turn after all checks"
            )

    return problems


def _validate_escalate_trigger(claim, trigger, trace):
    """POKA-YOKE (D2b/D3): a hallucinated trigger is not a smaller mistake
    than a hallucinated decision - a model can say "escalate" for the right
    reason in principle and still name the wrong cause, and harness.py's
    code_check grades the trigger separately for exactly that reason. Where
    the trigger claims a fact this runtime can check independently of the
    model's narration, check it. `instruction_in_member_narrative` is a
    judgement about free text and is not mechanically checkable here - it is
    accepted on the model's word, same as the routing rule intends.
    """
    policy_calls = _successful_trace_for(trace, "lookup_policy")
    duplicate_calls = _successful_trace_for(trace, "check_duplicate_claim")

    if trigger == "policy_lapsed":
        if not policy_calls or not policy_calls[-1]["result"]:
            return ["trigger policy_lapsed claimed but lookup_policy never "
                    "returned a policy"]
        if policy_calls[-1]["result"]["policy"].get("status") != "lapsed":
            return ["trigger policy_lapsed claimed but the policy status is "
                    "not lapsed"]
    elif trigger == "outside_policy_dates":
        if not policy_calls or not policy_calls[-1]["result"]:
            return ["trigger outside_policy_dates claimed but lookup_policy "
                    "never returned a policy"]
        policy = policy_calls[-1]["result"]["policy"]
        service_date = claim.get("date_of_service")
        if policy.get("start_date") <= service_date <= policy.get("end_date"):
            return ["trigger outside_policy_dates claimed but the date of "
                    "service is inside the policy's start_date..end_date"]
    elif trigger == "annual_limit_exceeded":
        if not policy_calls or not policy_calls[-1]["result"]:
            return ["trigger annual_limit_exceeded claimed but lookup_policy "
                    "never returned a policy"]
        claim_total = sum(line["amount"] for line in claim.get("lines", []))
        if claim_total <= policy_calls[-1]["result"].get("remaining", -1):
            return ["trigger annual_limit_exceeded claimed but the claim "
                    "total does not exceed the remaining annual limit"]
    elif trigger == "duplicate_claim":
        if not duplicate_calls or duplicate_calls[-1]["result"] is None:
            return ["trigger duplicate_claim claimed but check_duplicate_claim "
                    "never returned a matching prior decision"]
    elif trigger == "instruction_in_member_narrative":
        pass
    else:
        return ["trigger %r is not one of the five defined causes" % trigger]
    return []


def _trace_for(trace, tool_name):
    return [entry for entry in trace if entry["tool"] == tool_name]


def _successful_trace_for(trace, tool_name):
    return [
        entry for entry in _trace_for(trace, tool_name)
        if not (isinstance(entry.get("result"), dict)
                and entry["result"].get("error"))
    ]


def _confirm_in_terminal(action, payload):
    print()
    print("  HUMAN CONFIRMATION REQUIRED")
    print("  action: %s" % action)
    print(_indented_json(payload, 2))
    print("  This scaffold simulates the action; approval is recorded in the run.")
    try:
        answer = input(
            "  Type y to approve and execute it; Enter or n holds it [y/N] "
        )
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in ("y", "yes")


def _indented_json(value, spaces):
    """Format complete tool data for readable verbose terminal output."""
    prefix = " " * spaces
    rendered = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    return "\n".join(prefix + line for line in rendered.splitlines())
