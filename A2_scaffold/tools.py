"""
PE6201 · A2 scaffold — THE TOOL LAYER  (D2)
====================================================================
A tool reads ONE thing from the reference data and returns ONE fact.

THE NAMES BELOW ARE OURS, NOT YOURS. Appendix A says so and so does the
brief: these describe work that has to happen, not an interface you must
implement. Rename, re-argument, merge, split, add. What you cannot do is
change the ROUTING RULE or the GATED ACTION - the answer key is written
against those.

--------------------------------------------------------------------
HOW TO READ THIS FILE

Every tool carries the same comment block, and it is worth copying the
shape for your own tools:

    WHAT IT DOES   one sentence, in domain language
    READS          which JSON file(s) it touches
    RETURNS        the exact shape that comes back
    RETURNS NONE   when, AND WHAT THAT MEANS - these are different
    WATCH OUT      the mistake this tool exists to prevent

The fourth line is the one that separates a tool from a lookup. "Returns
None" is a fact about Python. "Returns None, which means no approval
exists - NOT that the procedure is uncovered" is a fact about the
business, and it is what stops a wrong decision.

--------------------------------------------------------------------
THE SIX-FIELD DESCRIPTOR (D2b)

EVERY tool below has one, at the bottom of this file. THEY ARE NOT
DECORATION - `prompt.build_system_prompt()` assembles them into the text
the model is actually sent, so editing one changes what the agent sees.

    python3 run_eval.py --prompt      shows the exact text, and its size

That is what makes D2(b) measurable. Rewrite the descriptors, print the
prompt, and the diff is precisely what you are claiming to have
measured. The v1 you compare against should be a genuinely worse version
you wrote - and note the prompt is resent EVERY TURN, so a longer
descriptor has to earn its length on every turn of every run.

--------------------------------------------------------------------
POKA-YOKE: make the wrong call impossible rather than documented.
Two examples below - `get_clinic_slots` demands a band so you cannot
accidentally book an urgent patient into a routine slot, and
`check_coverage` resolves the policy from a required member_id so you
cannot pair a claim with an unrelated policy_id.
====================================================================
"""
import json
import os

import config

_CACHE = {}


def _load(problem, table):
    """Read one JSON file, once, and keep it in memory.

    WHAT IT DOES   internal helper - the tools below read through it.
    WATCH OUT      the agent NEVER calls this and never sees these files.
                   It asks a tool a question and gets one answer back. An
                   agent handed all the data in its first prompt is making
                   a single call, not running a loop - which is exactly
                   what D0(a) asks you to defend.

    The cache is per-process, so a run never re-reads a file. It also
    means editing a JSON file mid-session has no effect until you
    restart - if the data looks stale, that is why.
    """
    key = (problem, table)
    if key not in _CACHE:
        path = os.path.join(config.data_root(), "data_%s" % problem,
                            "%s.json" % table)
        with open(path, encoding="utf-8") as fh:
            _CACHE[key] = json.load(fh)
    return _CACHE[key]


# =====================================================================
# PROBLEM B · outpatient referral coordination
# =====================================================================

def get_referral(referral_id):
    """Fetch the one referral the agent has been asked to handle.

    WHAT IT DOES   turns an id into the actual record: patient, specialty,
                   date, tests attached, and the GP's free-text summary.
    READS          data_B/referrals.json
    RETURNS        the referral row, or None
    RETURNS NONE   when no referral has that id. That is a BROKEN CASE,
                   not a business outcome - the agent was handed an id
                   that resolves to nothing. check_my_data.py exists to
                   catch this before a run ever happens.
    WATCH OUT      this is almost always turn 1 and it must run ALONE.
                   Everything else needs the patient_id and specialty it
                   returns, so nothing can be parallelised with it.

    Note what is NOT in the row it returns: no urgency, no red-flag
    verdict, no slot, no rule. Every one of those has to be fetched.
    That is what makes this an agent loop rather than one big call.
    """
    for r in _load("B", "referrals"):
        if r["referral_id"] == referral_id:
            return r
    return None


def lookup_patient(patient_id):
    """Who the patient is, what they already have booked, and how to
    reach them.

    WHAT IT DOES   answers the duplicate question and the contact question
                   in one call.
    READS          data_B/patients.json AND data_B/contacts.json
    RETURNS        {"patient": {...}, "contact": {...}}
    RETURNS NONE   when the patient_id matches nobody - again a broken
                   case, not an outcome.
    WATCH OUT      contacts and patients share the SAME KEY. Reading
                   contacts "through" patients would be a two-hop chain
                   and an extra turn for nothing. Both are fetched here
                   for that reason.

    THE DUPLICATE RULE, because this is where teams lose the case:
    `patient["existing_appointments"]` is a duplicate only when BOTH are
    true - the same specialty AND a date in the future, measured from
    as_of(). A past appointment in the same specialty is NOT a duplicate;
    the patient was seen and has been referred again. An empty list is
    normal and means nothing is booked.

    This tool does not decide that for you. It hands you the appointments
    and the decision is the agent's - which is deliberate, because the
    decision is what D4 grades.
    """
    p = next((x for x in _load("B", "patients")
              if x["patient_id"] == patient_id), None)
    if p is None:
        return None
    c = next((x for x in _load("B", "contacts")
              if x["patient_id"] == patient_id), None)
    return {"patient": p, "contact": c}


def check_referral_criteria(specialty, referral_id):
    """Run the department's protocol against this referral's free text.

    WHAT IT DOES   answers the four questions that can each end the run,
                   plus the urgency band, in one call.
    READS          data_B/specialties.json, data_B/urgency_bands.json,
                   and the referral itself
    RETURNS        {"red_flag_term":   the matched phrase, or None
                    "right_department": True/False
                    "missing_tests":   list of mandatory tests NOT attached
                    "band":            "urgent" | "soon" | "routine"
                    "window_weeks":    2 | 4 | 8}
    RETURNS NONE   when the referral or the specialty does not exist.
    WATCH OUT      THIS TOOL DECIDES NOTHING. It reports five facts. The
                   agent decides what they mean, and the ORDER matters:

                       red_flag_term is not None   -> ESCALATE, stop
                       right_department is False   -> ESCALATE, stop
                       missing_tests is non-empty  -> REQUEST INFO, stop
                       otherwise                   -> carry on to slots

                   An agent that queries a slot after finding a red flag
                   has failed the case even if it never books.

    WHY THIS IS ONE TOOL AND NOT FOUR - a design choice worth arguing
    with. The four questions are always asked, always in this order, and
    each can end the run. Splitting them into four tools would invite an
    agent to ask them out of order or skip one, and would cost three
    extra turns for no information. The cost is that this tool is doing
    four things, which is usually bad design.
    D2(a) marks your REASONING about the tool set, not ours - so if you
    split it, say why, and you are on perfectly good ground.

    HOW THE THREE TEXT CHECKS WORK, so you can see how crude they are:
      - red flags   substring match of the specialty's red_flag_terms
      - department  substring match of the specialty's `treats` words
      - band        first urgency band whose trigger_terms appear;
                    NO TRIGGER FOUND MEANS ROUTINE, which is the default
                    and not an error
    Substring matching is fragile on purpose. Your prompt-injection
    cases will attack exactly this, and improving it is fair game - just
    do not change the PROTOCOL, only how you detect it.
    """
    ref = get_referral(referral_id)
    spec = next((s for s in _load("B", "specialties")
                 if s["code"] == specialty), None)
    if ref is None or spec is None:
        return None
    text = ref["clinical_summary"].lower()

    red = next((t for t in spec["red_flag_terms"] if t.lower() in text), None)
    right_department = any(w.lower() in text for w in spec["treats"])
    attached = set(ref.get("tests_attached", []))
    missing = [t for t in spec["mandatory_tests"] if t["code"] not in attached]

    band, weeks = "routine", 8            # <- routine is the DEFAULT
    for b in _load("B", "urgency_bands"):
        if any(t.lower() in text for t in b["trigger_terms"]):
            band, weeks = b["band"], b["window_weeks"]
            break

    return {"red_flag_term": red,
            "right_department": right_department,
            "missing_tests": missing,
            "band": band,
            "window_weeks": weeks}


def get_clinic_slots(specialty, band, **window):
    """Find appointment slots that exist AND are free AND are legal.

    WHAT IT DOES   three filters at once: right department, right band,
                   inside the window, with a place left.
    READS          data_B/clinic_slots.json
    RETURNS        list of {clinic, specialty, band, date, time,
                   capacity_remaining} - possibly empty
    RETURNS EMPTY  when nothing is free in that window. EMPTY IS AN
                   ANSWER, not a failure: it means ESCALATE with trigger
                   `no_slot_in_window`. It does NOT mean widen the
                   window, and it does NOT mean drop to another band.
    WATCH OUT      capacity_remaining == 0 means the slot EXISTS AND IS
                   FULL. That is a different fact from the slot not
                   existing, and this tool filters those rows out for
                   you - so an empty list can mean either. If your
                   record needs to distinguish them, read the file.

    POKA-YOKE: `band` IS A REQUIRED ARGUMENT, and this is the clearest
    example in the scaffold of designing an interface so the wrong call
    cannot be made.

    On the shipped data, REF-5602 is a routine referral with an 8-week
    window closing 2026-11-04. THREE slots sit earlier inside that window
    with capacity free - OPH-C1 on 09-15 and 09-22 (urgent) and OPH-C3 on
    09-29 (soon). A team filtering by date alone books one of them and
    fails the case. Only the band excludes them, and making band an
    argument rather than an optional filter is what makes forgetting it
    impossible rather than merely documented.

    The window is passed as **kwargs so `from` can be used as a name -
    it is a Python keyword and cannot be a normal parameter. That is a
    small ugliness bought deliberately, to keep the domain word.
    """
    lo = window.get("from", "0000-00-00")
    hi = window.get("to", "9999-99-99")
    return [s for s in _load("B", "clinic_slots")
            if s["specialty"] == specialty
            and s["band"] == band
            and lo <= s["date"] <= hi
            and s["capacity_remaining"] > 0]


def book_slot(clinic, date, time, referral_id):
    """>>> THE IRREVERSIBLE STEP FOR PROBLEM B <<<

    WHAT IT DOES   commits the appointment. A patient is now expected at
                   a clinic on a date.
    READS          nothing - it WRITES, conceptually
    RETURNS        a confirmation carrying everything the record needs
    WATCH OUT      this is the ONE call in Problem B that cannot be taken
                   back. Every other tool can be re-run harmlessly.

    THIS IS WHAT THE AUTONOMY GATE SITS IN FRONT OF - see guardrails.py
    and the GATED_ACTION table below. Note WHERE the gate goes: in front
    of THIS ACTION, not in front of the agent as a whole. An agent gated
    as a whole is not an agent, it is a form, and D3(a) asks you to
    defend the placement.

    In this scaffold it returns a dict rather than touching anything -
    there is no real booking system. Your evaluation runs would be
    unrepeatable if there were, which is worth noticing: an agent that
    genuinely changes the world is much harder to test, and that is a
    real cost of autonomy, not a detail of this exercise.
    """
    return {"booked": True, "clinic": clinic, "date": date,
            "time": time, "referral_id": referral_id}


def as_of():
    """The clock for Problem B.

    WHAT IT DOES   returns the single date every urgency window is
                   measured FROM.
    READS          data_B/as_of.json
    RETURNS        a date string, e.g. "2026-09-09"
    WATCH OUT      windows are counted from THIS, not from the referral's
                   `date_received`. They happen to be equal for some
                   shipped referrals, which is exactly the sort of
                   coincidence that hides a bug until a case where they
                   differ.

    Move this date and every booking case in the answer key silently
    becomes wrong. The data guide says leave it alone, and it means it.
    """
    return _load("B", "as_of")["as_of"]


# =====================================================================
# PROBLEM A · health-insurance claim first response
# =====================================================================

def get_claim(claim_id):
    """Fetch the one claim the agent has been asked to decide.

    WHAT IT DOES   turns an id into the record: member, hospital, date,
                   attached documents, the member's narrative, and the
                   LINE ITEMS.
    READS          data_A/claims.json
    RETURNS        the claim row, or None
    RETURNS NONE   when no claim has that id - a broken case, not an
                   outcome.
    WATCH OUT      `lines` is a LIST. Nine of the fifteen shipped claims
                   have one line; six have two to four. Every line needs
                   its own coverage check and its own disposition, and an
                   agent that checks only the first line quietly approves
                   things it should refuse.

    Like get_referral, this must run ALONE on turn 1 - everything after
    it needs the member, the hospital and the lines it returns. It is
    also the reason Problem A has anything to parallelise: those per-line
    checks do not depend on each other, so they fold into one turn.
    """
    for c in _load("A", "claims"):
        if c["claim_id"] == claim_id:
            return c
    return None


def lookup_policy(member_id, claim_lines=None):
    """Follow the claim to the money and the rules.

    WHAT IT DOES   claim -> member -> policy, and does the headroom
                   arithmetic for you.
    READS          data_A/members.json AND data_A/policies.json
    RETURNS        {"member": {...}, "policy": {...}, "remaining": int}
                   plus claim_total and within_annual_limit when claim_lines
                   is supplied.
    RETURNS NONE   when the member or their policy does not exist.
    WATCH OUT      `remaining` is annual_limit MINUS used_to_date. The
                   claim total is tested against THAT, not against
                   annual_limit. Testing against the limit is a silent
                   wrong answer on any policy with spend on it.

    THREE SEPARATE REASONS TO REFUSE live in the row this returns, and
    they are easy to conflate:
      1. status == "lapsed"              -> escalate, nothing else matters
      2. date_of_service outside
         start_date .. end_date          -> escalate, even if status is active
      3. lines exceed `remaining`         -> escalate
    Note (2): a policy can say "active" and still not cover the date. The
    shipped data has a claim that tests exactly this.

    The member row itself carries NO decision information - it is a
    bridge. `join_date` in particular is not a coverage date; the
    policy's own dates govern.
    """
    m = next((x for x in _load("A", "members")
              if x["member_id"] == member_id), None)
    if m is None:
        return None
    p = next((x for x in _load("A", "policies")
              if x["policy_id"] == m["policy_id"]), None)
    if p is None:
        return None
    remaining = p["annual_limit"] - p["used_to_date"]
    result = {"member": m, "policy": p, "remaining": remaining}
    if claim_lines is not None:
        if not isinstance(claim_lines, list):
            raise ValueError("claim_lines must be a list")
        try:
            claim_total = sum(line["amount"] for line in claim_lines)
        except (KeyError, TypeError):
            raise ValueError("claim_lines must contain amount on every line")
        result["claim_total"] = claim_total
        result["within_annual_limit"] = claim_total <= remaining
    return result


def lookup_hospital(hospital_id):
    """Is the hospital inside the insurer's network?

    WHAT IT DOES   one boolean and a name.
    READS          data_A/hospitals.json
    RETURNS        {hospital_id, name, panel, country} or None
    WATCH OUT      panel status does NOT by itself decide the claim. A
                   non-panel hospital means the member paid and is
                   claiming it back rather than the insurer settling
                   directly - so it changes what the record must SAY, not
                   what the decision IS.

    It is still a required call. An agent that never checked cannot
    claim it did, and the decision record is what a marker reads.
    """
    return next((h for h in _load("A", "hospitals")
                 if h["hospital_id"] == hospital_id), None)


def check_coverage(code, policy_id=None, attached_documents=None,
                   member_id=None):
    """Is this ONE procedure payable under THIS policy?

    WHAT IT DOES   resolves one line item: what the code means, whether
                   it needed permission first, and whether this product
                   excludes it.
    READS          data_A/procedures.json, data_A/policies.json AND
                   data_A/required_documents.json
    RETURNS        {"code", "description", "requires_preauth" (bool),
                    "excluded" (bool), "exclusion_rule" (str or None),
                    "required_documents" (list[str]),
                    "missing_documents" (list[str] or None)}
    RETURNS NONE   when the code or the policy does not exist.
    WATCH OUT      CALL THIS ONCE PER LINE. A three-line claim needs
                   three calls - and because they are independent of each
                   other, all three belong in the same turn.

    TWO FIELDS THAT DRIVE EVERYTHING AFTER THIS:

      `requires_preauth` is THE BRANCH. True means go and look for an
      approval; False means do not. This single boolean is why claims
      vary in run length, and an agent that calls get_preauthorisation
      for every line has not read it.

      `excluded` refuses THE LINE, not the claim. Three lines approved
      and one excluded is ONE decision letter covering both - "approve in
      principle" with a disposition per line. Escalating the whole claim
      because one line is excluded is a distinct, and common, failure.
      When excluded, `exclusion_rule` gives you the rule id to cite; the
      record should name it, not merely say "excluded".

      `required_documents` lists the documents required for this line.
      When `attached_documents` is supplied from get_claim,
      `missing_documents` contains the required documents that were not
      attached. A non-empty list means request_document, not refusal.

    PRIMARY INTERFACE: pass `member_id` from get_claim. The tool follows
    that id to the member's policy internally, so lookup_policy and all
    per-line coverage checks can run in the same turn after get_claim.

    BACKWARD COMPATIBILITY: the old `policy_id` argument remains available
    for existing notebooks and scripts. New model calls should use
    `member_id`; supplying both ids is an error.
    """
    if member_id is not None and policy_id is not None:
        raise ValueError("pass member_id or policy_id, not both")
    if member_id is not None and attached_documents is None:
        raise ValueError(
            "attached_documents is required when checking coverage by member_id"
        )
    if member_id is not None:
        member = next((m for m in _load("A", "members")
                       if m["member_id"] == member_id), None)
        policy_id = member["policy_id"] if member else None

    proc = next((p for p in _load("A", "procedures") if p["code"] == code), None)
    pol = next((p for p in _load("A", "policies")
                if p["policy_id"] == policy_id), None)
    if proc is None or pol is None:
        return None
    excl = next((e for e in pol["exclusions"] if e["code"] == code), None)
    required_documents = [
        row["document"]
        for row in _load("A", "required_documents")
        if row["procedure_code"] == code
    ]
    missing_documents = None
    if attached_documents is not None:
        attached = set(attached_documents)
        missing_documents = [
            document for document in required_documents
            if document not in attached
        ]
    return {"code": code,
            "description": proc["description"],
            "requires_preauth": proc["requires_preauth"],
            "excluded": excl is not None,
            "exclusion_rule": excl["rule"] if excl else None,
            "required_documents": required_documents,
            "missing_documents": missing_documents}


def get_preauthorisation(member_id, procedure_code, date_of_service):
    """Was permission granted BEFORE treatment, and is it still good?

    WHAT IT DOES   looks for an approval matching this member AND this
                   procedure AND valid on this date.
    READS          data_A/preauthorisations.json
    RETURNS        {preauth_id, member_id, procedure_code, valid_from,
                    valid_to} or None
    RETURNS NONE   in TWO different situations that this tool cannot tell
                   apart: no approval was ever granted, OR one exists but
                   had expired before the date of service.
    WATCH OUT      >>> NONE DOES NOT MEAN "NOT COVERED". <<<

    This is the single most expensive misreading available in Problem A.
    None means THE EVIDENCE IS MISSING, which under the routing table is
    a REQUEST - "pre-authorisation reference for 62480, valid on
    2026-09-02" - naming the code and the date. It is not a refusal, and
    deciding otherwise fails the case.

    ALL THREE conditions must hold for a match. An approval for the right
    procedure belonging to another member does not count. An approval for
    the right member and procedure that expired the day before treatment
    does not count either - the shipped data has one of each, precisely
    so a partial match is punished.

    Call this ONLY when check_coverage said requires_preauth is True.
    """
    for pa in _load("A", "preauthorisations"):
        if (pa["member_id"] == member_id
                and pa["procedure_code"] == procedure_code
                and pa["valid_from"] <= date_of_service <= pa["valid_to"]):
            return pa
    return None


def check_duplicate_claim(member_id, hospital_id, date_of_service, lines):
    """Has this episode already been decided?

    WHAT IT DOES   compares the claim against the claims history on ALL
                   FOUR facts.
    READS          data_A/decided_claims.json
    RETURNS        the prior decision row, or None
    RETURNS NONE   when nothing matches - which is the normal case and
                   means carry on.
    WATCH OUT      THE CLAIM ID IS NOT ONE OF THE FACTS. A resubmission
                   arrives with a NEW id, so matching on it finds nothing,
                   ever, and the case fails silently.

    MATCH ON ALL FOUR: member, hospital, date of service, lines. The
    shipped history holds four rows and only ONE queued claim is a true
    duplicate of any of them. The other three history rows are
    NEAR-MISSES, each differing from a real claim on exactly one fact:

        CLM-8710  vs CLM-8933   nothing differs - the true duplicate
        CLM-8702  vs CLM-8850   the date of service differs
        CLM-8726  vs CLM-8960   the LINES differ
        CLM-8688  vs nothing    just history to walk past

    So an agent matching on the date alone, or on member and date, or on
    member and hospital and date, WRONGLY ESCALATES a claim that is
    perfectly fine. Only the full comparison gets all fifteen right. The
    near-misses are in the data deliberately, to make that testable.
    """
    def norm(ls):
        return sorted((l["code"], l["amount"]) for l in ls)
    for d in _load("A", "decided_claims"):
        if (d["member_id"] == member_id
                and d["hospital_id"] == hospital_id
                and d["date_of_service"] == date_of_service
                and norm(d["lines"]) == norm(lines)):
            return d
    return None


def issue_decision_letter(claim_id, decision, line_dispositions=None,
                          lines_resolved=None, approved_total=None,
                          refused_total=None):
    """>>> THE IRREVERSIBLE STEP FOR PROBLEM A <<<

    WHAT IT DOES   sends the decision to the member. The insurer is now
                   committed to it.
    READS          nothing - it WRITES, conceptually
    RETURNS        a confirmation carrying the automatically calculated totals
    WATCH OUT      everything before this can be re-run harmlessly. This
                   one cannot be taken back, which is what makes it the
                   gated action - see GATED_ACTION below.

    IT IS A TURN LIKE ANY OTHER. Gated, not free. Appendix A's CLM-8842
    record counts it as turn 4 of 4, and your D2(c) arithmetic has to
    count it too.

    `line_dispositions` must contain one object per claim line. Each object
    has `code`, `amount`, and `status` (`covered` or `not_covered`). Amounts
    are summed here, in code, so the model cannot introduce an arithmetic
    error by typing approved/refused totals. The old total arguments remain
    in the signature so stale callers fail with a clear validation message;
    they are never trusted for the returned totals.
    """
    if decision != "approve_in_principle":
        raise ValueError(
            "issue_decision_letter only supports approve_in_principle; "
            "request_document and escalate are final outcomes"
        )
    if not isinstance(line_dispositions, list) or not line_dispositions:
        raise ValueError(
            "line_dispositions is required; provide one entry per claim line"
        )

    approved = 0
    refused = 0
    for line in line_dispositions:
        if not isinstance(line, dict):
            raise ValueError("each line disposition must be an object")
        status = line.get("status")
        amount = line.get("amount")
        if status not in ("covered", "not_covered"):
            raise ValueError("line status must be covered or not_covered")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise ValueError("line amount must be numeric")
        if status == "covered":
            approved += amount
        else:
            refused += amount

    resolved = len(line_dispositions) if lines_resolved is None else lines_resolved
    return {"sent": True, "claim_id": claim_id, "decision": decision,
            "lines_resolved": resolved,
            "approved_total": approved, "refused_total": refused}


# =====================================================================
# THE REGISTRY
# =====================================================================
# What the agent is allowed to call, per problem. Adding a tool means
# writing the function, adding it here, and writing its descriptor.
REGISTRY = {
    "B": {
        "get_referral": get_referral,
        "lookup_patient": lookup_patient,
        "check_referral_criteria": check_referral_criteria,
        "get_clinic_slots": get_clinic_slots,
        "book_slot": book_slot,
        "as_of": as_of,
    },
    "A": {
        "get_claim": get_claim,
        "lookup_policy": lookup_policy,
        "lookup_hospital": lookup_hospital,
        "check_coverage": check_coverage,
        "get_preauthorisation": get_preauthorisation,
        "check_duplicate_claim": check_duplicate_claim,
        "issue_decision_letter": issue_decision_letter,
    },
}

# THE ONE IRREVERSIBLE ACTION PER PROBLEM. Appendix A fixes this and the
# answer key is written against it, so it is not yours to change. What IS
# yours is where you put the gate - and the answer is: in front of this
# action, not in front of the agent.
GATED_ACTION = {"B": "book_slot", "A": "issue_decision_letter"}


# =====================================================================
# THE SIX-FIELD DESCRIPTORS  (D2b)
# =====================================================================
# Two worked examples. Write one for EVERY tool you ship, and note that
# the descriptor is what the MODEL reads - the comments above are what
# YOU read. They overlap, but they are not the same document: a
# descriptor is written to be acted on, a comment to be understood.
DESCRIPTORS = {
    # ---- Problem B -------------------------------------------------
    "get_referral": {
        "name": "get_referral",
        "purpose": "Fetch the referral you have been asked to handle.",
        "when": "Turn 1, alone. Everything else needs what it returns, so "
                "nothing can be run alongside it.",
        "args": {"referral_id": "str, the case id you were given"},
        "returns": "{referral_id, patient_id, referring_clinic, specialty, "
                   "date_received, clinical_summary, tests_attached, "
                   "tests_attached_on (may be absent)}",
        "failure": "Returns None when no referral has that id. That is a "
                   "broken case, not an outcome - stop and say so rather "
                   "than inventing a decision.",
    },
    "lookup_patient": {
        "name": "lookup_patient",
        "purpose": "The patient's existing appointments and how to contact them.",
        "when": "Any time after get_referral. Independent of the criteria "
                "check, so the two can go in one turn.",
        "args": {"patient_id": "str, from the referral"},
        "returns": "{patient: {patient_id, date_of_birth, "
                   "existing_appointments[]}, contact: {method, value}}",
        "failure": "Returns None when the patient does not exist - a broken "
                   "case. An EMPTY existing_appointments list is normal and "
                   "means nothing is booked, which is not the same thing.",
    },
    "check_referral_criteria": {
        "name": "check_referral_criteria",
        "purpose": "Run the department's protocol against the referral's free "
                   "text: red flags, right department, mandatory tests, band.",
        "when": "Immediately after get_referral. Its answers decide whether "
                "the run continues at all.",
        "args": {"specialty": "str, the code on the referral",
                 "referral_id": "str, the case id"},
        "returns": "{red_flag_term (str or None), right_department (bool), "
                   "missing_tests (list), band, window_weeks}",
        "failure": "Returns None when the referral or specialty does not "
                   "exist. IT DECIDES NOTHING - it reports five facts. Apply "
                   "them in order: red flag, then wrong department, then "
                   "missing test, then duplicate. STOP at the first that "
                   "fires. band 'routine' is the default when no trigger "
                   "phrase appears; that is normal, not a failure.",
    },
    "book_slot": {
        "name": "book_slot",
        "purpose": "Commit the appointment. THE IRREVERSIBLE STEP.",
        "when": "Last, and only when all four checks passed and a legal slot "
                "was found. Never speculatively.",
        "args": {"clinic": "str, from the chosen slot",
                 "date": "str, from the chosen slot",
                 "time": "str, from the chosen slot",
                 "referral_id": "str, the case id"},
        "returns": "{booked: true, clinic, date, time, referral_id}",
        "failure": "This call is GATED: it may be held for human approval "
                   "depending on the autonomy setting. If it is held, that is "
                   "the correct outcome and not an error - report that the "
                   "booking awaits approval, and name the slot you would take.",
    },
    "as_of": {
        "name": "as_of",
        "purpose": "The date every urgency window is measured FROM.",
        "when": "Before computing any window. Cheap - call it rather than "
                "assuming.",
        "args": {},
        "returns": "a date string, e.g. '2026-09-09'",
        "failure": "Never fails. WATCH OUT: windows are counted from THIS, "
                   "not from the referral's date_received. They are equal on "
                   "some referrals and not on others.",
    },

    # ---- Problem A -------------------------------------------------
    "get_claim": {
        "name": "get_claim",
        "purpose": "Fetch the claim you have been asked to decide.",
        "when": "Turn 1, alone. Everything else needs the member, hospital "
                "and line items it returns.",
        "args": {"claim_id": "str, the case id you were given"},
        "returns": "{claim_id, member_id, hospital_id, date_of_service, "
                   "narrative, documents[], lines[{code, amount}]}",
        "failure": "Returns None when no claim has that id - a broken case. "
                   "NOTE lines is a LIST: every line needs its own coverage "
                   "check and its own disposition.",
    },
    "lookup_policy": {
        "name": "lookup_policy",
        "purpose": "The member's policy, and how much of the annual limit is "
                   "left.",
        "when": "After get_claim. Independent of the coverage checks and the "
                "hospital lookup, so all of them fit in one turn.",
        "args": {"member_id": "str, from the claim",
                 "claim_lines": "list[{code, amount}], exactly the lines from get_claim; pass this for a deterministic annual-limit check"},
        "returns": "{member: {...}, policy: {status, start_date, end_date, "
                   "annual_limit, used_to_date, exclusions[]}, remaining: int; "
                   "when claim_lines is passed also claim_total and "
                   "within_annual_limit: bool}",
        "failure": "Returns None when the member or policy does not exist. "
                   "USE `remaining`, not annual_limit - it is the limit minus "
                   "what is already spent. Three separate escalation reasons "
                   "live here: lapsed status, a date of service outside "
                   "start_date..end_date EVEN IF status is active, and lines "
                   "exceeding `remaining`. When claim_lines is supplied the "
                   "tool also returns claim_total and within_annual_limit; "
                   "use those fields instead of doing arithmetic yourself.",
    },
    "lookup_hospital": {
        "name": "lookup_hospital",
        "purpose": "Whether the hospital is on the insurer's panel.",
        "when": "After get_claim, alongside the other independent lookups.",
        "args": {"hospital_id": "str, from the claim"},
        "returns": "{hospital_id, name, panel (bool), country}",
        "failure": "Returns None when the hospital does not exist. panel "
                   "false does NOT decide the claim - it changes what the "
                   "record must SAY, not what the decision is. Record it "
                   "either way.",
    },
    "check_coverage": {
        "name": "check_coverage",
        "purpose": "Whether ONE procedure code is payable under ONE policy.",
        "when": "After get_claim, ONCE PER LINE. Each call uses only values "
                "from that claim, so all line checks can run alongside "
                "lookup_policy and lookup_hospital in the same turn.",
        "args": {"code": "str, one line's procedure code",
                 "member_id": "str, REQUIRED, from get_claim; the tool finds "
                              "the member's policy internally",
                 "attached_documents": "list[str], REQUIRED with member_id; "
                                       "pass the complete documents list from "
                                       "get_claim without modification"},
        "returns": "{code, description, requires_preauth (bool), excluded "
                   "(bool), exclusion_rule (str or None), "
                   "required_documents (list[str]), missing_documents "
                   "(list[str] or None)}. A non-empty missing_documents list "
                   "means request_document for this line. None means "
                   "attached_documents was not supplied; an empty list means "
                   "all requirements are satisfied.",
        "failure": "Returns None when the code, member or policy does not "
                   "exist. TWO "
                   "FIELDS DRIVE WHAT HAPPENS NEXT: requires_preauth true "
                   "means look for an approval, false means do not. excluded "
                   "refuses THAT LINE, not the claim - cite exclusion_rule by "
                   "name, and keep deciding the other lines.",
    },
    "check_duplicate_claim": {
        "name": "check_duplicate_claim",
        "purpose": "Whether this episode has already been decided.",
        "when": "Before issuing any decision.",
        "args": {"member_id": "str, from the claim",
                 "hospital_id": "str, from the claim",
                 "date_of_service": "str, from the claim",
                 "lines": "the claim's lines list, unchanged"},
        "returns": "the prior decided claim, or None",
        "failure": "Returns None when nothing matches - the normal case, "
                   "carry on. MATCH ON ALL FOUR FACTS. The claim id is NOT "
                   "one of them: a resubmission arrives with a new id. The "
                   "history contains near-misses that differ on exactly one "
                   "fact each, so any shortcut match wrongly escalates a "
                   "perfectly good claim.",
    },
    "issue_decision_letter": {
        "name": "issue_decision_letter",
        "purpose": "Send the decision to the member. THE IRREVERSIBLE STEP.",
        "when": "Last, once every line has a disposition.",
        "args": {"claim_id": "str, the case id",
                 "decision": "str, one of the three outcomes",
                 "line_dispositions": "list of {code, amount, status}; one per claim line",
                 "lines_resolved": "int, optional compatibility field; normally omit"},
        "returns": "{sent: true, claim_id, decision, lines_resolved, "
                   "approved_total, refused_total}",
        "failure": "This call is GATED and may be held for human approval. "
                   "If held, that is the correct outcome, not an error. "
                   "The code calculates approved_total as the sum of amounts "
                   "with status=covered and refused_total as the sum with "
                   "status=not_covered. Do not send or calculate totals yourself. "
                   "line_dispositions must contain every claim line exactly once.",
    },

    "get_clinic_slots": {
        "name": "get_clinic_slots",
        "purpose": "Find appointment slots that actually exist and are free, "
                   "for one specialty in one urgency band inside a date window.",
        "when": "AFTER all four gates pass. Never before - a red flag or a "
                "missing mandatory test ends the run and a slot query at that "
                "point is a wasted call and a wrong record.",
        "args": {
            "specialty": "str, the code from the referral, e.g. 'OPH'",
            "band": "str, REQUIRED, one of urgent|soon|routine, from "
                    "check_referral_criteria - not your own judgement",
            "from/to": "str dates, the window measured from as_of()",
        },
        "returns": "list of {clinic, specialty, band, date, time, "
                   "capacity_remaining}, only rows with capacity above zero",
        "failure": "Returns an EMPTY LIST when nothing is free in that window. "
                   "Empty means escalate - 'no slot in window' - and it does "
                   "NOT mean widen the window or drop the band. A slot with "
                   "capacity_remaining 0 exists and is full; that is a "
                   "different fact from a slot not existing, and neither is a "
                   "reason to book outside the band.",
    },
    "get_preauthorisation": {
        "name": "get_preauthorisation",
        "purpose": "Find a pre-authorisation covering one member for one "
                   "procedure on one date.",
        "when": "ONLY when check_coverage said requires_preauth is true. "
                "Calling it for every line means you did not read the flag.",
        "args": {
            "member_id": "str, from the claim",
            "procedure_code": "str, the line's code",
            "date_of_service": "str date, from the claim - the approval must "
                               "be valid ON this date",
        },
        "returns": "{preauth_id, member_id, procedure_code, valid_from, "
                   "valid_to} or None",
        "failure": "Returns None when no approval exists OR when one exists "
                   "but had expired before the date of service. NONE DOES NOT "
                   "MEAN UNCOVERED. It means the evidence is missing, which is "
                   "a REQUEST for the reference - naming the code and the date "
                   "- not a refusal. Deciding otherwise fails the case.",
    },
}


def call(problem, name, args):
    """Dispatch a tool call by name.

    WATCH OUT      unknown tool names fail LOUDLY. A silent no-op here
                   would produce a run that looks fine and decided
                   nothing on evidence it never gathered - the most
                   expensive kind of bug in this assignment, because
                   nothing about the output says anything went wrong.
    """
    table = REGISTRY[problem]
    if name not in table:
        raise KeyError(
            "No tool named %r for Problem %s. Available: %s"
            % (name, problem, ", ".join(sorted(table))))
    return table[name](**args)
