#!/usr/bin/env python3
"""
PE6201 · A2 scaffold — D7 WORKED EXAMPLE: the loop failure
====================================================================
    python3 demo_loop_failure.py

This is the shape D7 asks for, done once so you can copy the method.

D7 requires each failure to be built as a DELETION FROM YOUR WORKING
AGENT - "the working agent, minus X" - not as a separately written bad
agent. Putting X back must recover the behaviour. That is what makes it
a diagnosis rather than a story.

Here X is ACTION DE-DUPLICATION. Everything else is untouched.

WHAT YOU SHOULD NOTICE: with the guard deleted the run does not crash.
No exception. No error. It repeats a call it already made, burns turns
and tokens - AND STILL RETURNS THE RIGHT ANSWER. A pass-rate table
would show it as a clean pass. Neither the step cap nor the budget
ceiling fires, because neither is breached: they bound the damage, they
do not detect the fault.

You only ever see this IF YOU ARE COUNTING. That is why instrumentation
is a requirement and not a nicety, and it is the whole lesson of D7.

Everything below runs on the SCRIPTED backend, so it costs nothing and
reproduces exactly. D7 needs no API key.
====================================================================
"""
import copy

import backends
import config
from agent import run_case
from guardrails import Guardrails

# Works for either problem. The default follows config.PROBLEM.
CASES = {"B": "REF-5602", "A": "CLM-8842"}


def _looping_script(CASE):
    """The working script, with one call repeated - a model that has
    forgotten it already asked. This is the observable behaviour; the
    deletion below is what lets it continue."""
    steps = copy.deepcopy(backends.SCRIPTS[CASE])
    repeat = copy.deepcopy(steps[1])          # ask the same thing again
    repeat["thought"] = "Let me check the criteria again to be sure."
    return steps[:2] + [repeat, repeat] + steps[2:]


def main(case=None, problem=None):
    problem = problem or config.PROBLEM
    CASE = case or CASES[problem]

    print()
    print(config.summary())
    print("  demonstrating on %s (Problem %s)" % (CASE, problem))
    print()
    original = backends.SCRIPTS[CASE]

    # ---- BEFORE: the working agent ----------------------------------
    before = run_case(CASE, problem=problem)
    print("BEFORE - the working agent, guard in place")
    print("  turns %d · tool calls %d · tokens %d · cost US$%.5f · decision %s"
          % (before["turns"], len(before["evidence"]),
             before["tokens_in"] + before["tokens_out"],
             before["cost_usd"], before["decision"]))

    # ---- AFTER: the same agent, MINUS the de-duplication guard ------
    backends.SCRIPTS[CASE] = _looping_script(CASE)
    real_check = Guardrails.check_duplicate
    Guardrails.check_duplicate = lambda self, tool, args: None   # <- the deletion
    try:
        after = run_case(CASE, problem=problem)
    finally:
        Guardrails.check_duplicate = real_check                  # <- put it back
        backends.SCRIPTS[CASE] = original

    print()
    print("AFTER - the working agent MINUS action de-duplication")
    print("  turns %d · tool calls %d · tokens %d · cost US$%.5f · decision %s"
          % (after["turns"], len(after["evidence"]),
             after["tokens_in"] + after["tokens_out"],
             after["cost_usd"], after["decision"]))
    print("  stopped by: %s" % after["stopped_by"])

    # ---- the four things D7 asks you to report ----------------------
    spend = (after["tokens_in"] + after["tokens_out"]) / \
            max(1, before["tokens_in"] + before["tokens_out"])
    print()
    print("=" * 68)
    print("  1 · THE INSTRUMENTATION THAT FOUND IT")
    print("      turns and cost logged per run. NOTHING RAISED AN EXCEPTION.")
    print("      The run cost %.1fx more and still answered %r"
          % (spend, after["decision"]))
    if after["decision"] == before["decision"]:
        print("      - THE SAME ANSWER AS THE WORKING AGENT. A pass-rate table")
        print("      alone would show this run as a clean pass. It is only")
        print("      visible because turns and cost were counted.")
    print("  2 · THE TURN DISTRIBUTION")
    print("      before: %d turns   after: %d turns   cap: %d"
          % (before["turns"], after["turns"], config.MAX_TURNS))
    print("      runs that hit the cap: %d of 2"
          % sum(1 for r in (before, after) if r["stopped_by"] == "step_cap"))
    print("  3 · THE FIX, AND WHY THE OTHER TWO LAYERS WERE WRONG")
    print("      Action de-duplication caught it, in the CODE layer.")
    # Say what ACTUALLY happened, not what sounds right. On this data the
    # other two guards did not fire at all - which is the stronger lesson.
    if after["stopped_by"] != "step_cap":
        print("      The STEP CAP never fired: the loop finished at %d turns,"
              % after["turns"])
        print("      inside the cap of %d. A cap bounds the damage; it does not"
              % config.MAX_TURNS)
        print("      detect this. Raise the repeat count and it would - later,")
        print("      and still without naming the cause.")
    else:
        print("      The step cap DID stop it, at %d turns - later than the"
              % after["turns"])
        print("      de-duplication guard, and without naming the cause.")
    print("      The BUDGET CEILING never fired either: %d tokens against a"
          % (after["tokens_in"] + after["tokens_out"]))
    print("      ceiling of %d." % config.MAX_TOKENS_PER_RUN)
    print("      A PROMPT fix cannot be relied on - the model is the thing")
    print("      that forgot. Only the code layer remembers.")
    print("  4 · BEFORE AND AFTER")
    print("      pass rate must not fall when the guard is restored - a cap")
    print("      that also truncates legitimate long runs has traded one")
    print("      failure for another. Check it on your whole set, not one case.")
    print("=" * 68)
    print()
    print("  Now do this for YOUR second failure, in the TOOL INTERFACE or")
    print("  the PROMPT - not loop control again. State which layer the fix")
    print("  belongs in and why the other two were the wrong place. That")
    print("  judgement is most of the mark.")
    print()


if __name__ == "__main__":
    main()
