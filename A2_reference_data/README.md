# PE6201 · A2 — reference data

The records your agent reads. Everything here is small, plain JSON, and yours to extend.

**Start here if you are short of time:** run the three commands below, then read
*How the files connect* — that section is the one that stops you writing an agent
that looks perfectly sound and returns nothing.

---

## What is in this folder

```
make_fixtures_A.py        generator · Problem A  →  writes data_A/
make_fixtures_B.py        generator · Problem B  →  writes data_B/
check_my_data.py          RUN THIS AFTER EVERY CHANGE - catches broken data

data_A/                   8 files · health-insurance claim first response
data_B/                   7 files · outpatient referral coordination
expected_outcomes_A.json  15 labelled cases · Problem A
expected_outcomes_B.json  15 labelled cases · Problem B
data_dictionary.json      every field, its type and what it means - machine-readable
```

**On `data_dictionary.json`.** The field descriptions in this README are also written to
that file, so you can load them rather than read them. They are kept *beside* the data and
not inside it deliberately: a `__description` key inside `claims.json` would appear in
every loop over the file, break `check_my_data.py`'s row fingerprints, and force every
team to special-case it. Documentation belongs next to the data, not in the middle of it.

The JSON is committed, so **you are not blocked if you cannot run Python on day one** —
open the files and read them. The generators are there so you can see the pattern and
add your own records, which you will have to do.

```bash
python3 make_fixtures_A.py       # rewrites data_A/
python3 make_fixtures_B.py       # rewrites data_B/
python3 check_my_data.py         # checks your data still hangs together
```

**There are only three scripts, and only two of them write anything.** The answer keys
are yours to edit by hand — nothing regenerates them, so nothing can overwrite the
labels you add.

No arguments, no packages to install, no network. Standard library only.

---

## Two kinds of file, and everything follows from the difference

**The work queue** — `claims.json` and `referrals.json`. **One row is one agent run.**
Your harness loops over these. The shape of a row is what makes the number of turns vary:
a claim with one line item is a short run, a claim with four lines and a pre-authorisation
to chase is a long one.

**Reference tables** — everything else. These are the systems of record your agent
**queries during a run**, through its tools, one fact at a time. It never receives them
up front.

That second point is the whole assignment. An agent handed all the data in its first
prompt is making a single call, not running a loop — and D0(a) will ask you which rung
of the Class 4 ladder you are actually on.

---

## The shape of every file

Generated from the data itself, so it cannot drift. `list[{a, b}]` means a list of
objects with those keys.

<!-- BEGIN GENERATED: field tables · make_data_dictionary.py -->

### Problem A · health-insurance claim first response

#### `claims.json` — 15 rows

**The work queue. One row = one agent run.** A member has been treated and the insurer must respond. The row carries who, where, when, what was done and what the member wrote — and nothing about whether any of it is payable. Every fact needed to decide it lives in another file, reached through the ids below.

| field | type | what it means | example |
|---|---|---|---|
| `claim_id` | str | Unique id for this claim. **Not** how a duplicate is detected — a resubmission arrives with a new one. | `"CLM-8842"` |
| `member_id` | str | Who was treated. Join to `members.json` to reach their policy. | `"M-2214"` |
| `hospital_id` | str | Where they were treated. Join to `hospitals.json` for panel status. | `"H-114"` |
| `date_of_service` | str | When treatment happened. Tested against the policy's start/end dates and against any pre-authorisation window. | `"2026-09-02"` |
| `narrative` | str | Free text written by the member. Useful context — and the one field on this row an outsider controls, so treat it as untrusted input. | `"Admitted for appendix removal. Surgeon als…` |
| `documents` | list[str] | Documents actually attached to this claim. Compare against `required_documents.json` for the procedures claimed. | `["itemised_bill", "discharge_summary"]` |
| `lines` | list[{code, amount}] | **One entry per procedure claimed** — each with a `code` and the `amount` in dollars. Most claims have one line; several have three or four, and every line must be decided separately. | `[{"code": "47120", "amount": 1400}, {"code"…` |

#### `members.json` — 5 rows

The bridge from a claim to a policy, and nothing else. A claim names a member; a member names a policy; the policy holds the money and the rules. Two hops, and the first one carries no decision information at all.

| field | type | what it means | example |
|---|---|---|---|
| `member_id` | str | The id a claim points at. | `"M-2214"` |
| `name` | str | Display name. Carries no decision information. | `"Tan Wei Ling"` |
| `policy_id` | str | The join onward to `policies.json`. This is the only field on this row that matters to a decision. | `"POL-3310"` |
| `join_date` | str | When they joined. Not a coverage date — the policy's own dates govern. | `"2024-04-01"` |

#### `policies.json` — 5 rows

**Where most refusals come from.** Is the cover live on the date of service, how much of the annual limit is left, and which procedure codes this product never pays for. Three different reasons to refuse, in one row.

| field | type | what it means | example |
|---|---|---|---|
| `policy_id` | str | The id a member points at. | `"POL-3310"` |
| `product` | str | Plan name. Cosmetic; the rules are in the other fields. | `"Shield Plus"` |
| `status` | str | `active` or `lapsed`. A lapsed policy ends the run — nothing further needs checking. | `"active"` |
| `start_date` | str | Cover begins. A date of service before this is not covered even if the status says active. | `"2026-04-01"` |
| `end_date` | str | Cover ends. | `"2027-03-31"` |
| `annual_limit` | int | Total the policy will pay in the year, in dollars. | `12000` |
| `used_to_date` | int | Already spent this year. **`annual_limit` − `used_to_date` is the headroom**, and the claim total is tested against that, not against the limit. | `2800` |
| `exclusions` | list[{code, rule}] | Procedure codes this product never pays for, each with the `rule` id to cite. One excluded line does not refuse the whole claim — it refuses that line. | `[{"code": "31255", "rule": "EX-14 cosmetic…` |

#### `procedures.json` — 10 rows

The catalogue of what a code means and whether it needed permission first. `requires_preauth` is the field that varies your turn count — it decides whether the agent makes another call or stops.

| field | type | what it means | example |
|---|---|---|---|
| `code` | str | The procedure code that a claim line refers to. | `"47120"` |
| `description` | str | What the code means, in words. For your decision record, not for the logic. | `"Laparoscopic appendicectomy"` |
| `requires_preauth` | bool | **The branch.** `true` means look for a pre-authorisation; `false` means do not. This single boolean is why the run length varies between claims. | `false` |

#### `preauthorisations.json` — 3 rows

Permission granted *before* treatment. Only consulted when a procedure requires it. Matching is on member **and** procedure code, and then the date of service must fall inside the validity window — an approval that exists but has expired is not an approval.

| field | type | what it means | example |
|---|---|---|---|
| `preauth_id` | str | The id to cite in the decision record when an approval is found. | `"PA-5521"` |
| `member_id` | str | Half of the match. An approval belongs to one member. | `"M-2214"` |
| `procedure_code` | str | The other half. Both must match, plus the dates. | `"62480"` |
| `valid_from` | str | Approval window opens. The claim's `date_of_service` must be on or after this. | `"2026-08-01"` |
| `valid_to` | str | Approval window closes. On or before this. Outside the window, the approval does not apply. | `"2026-10-31"` |

#### `hospitals.json` — 4 rows

Panel or not. A single boolean that changes the outcome: treatment at a non-panel hospital is not automatically refused, but it is never a silent approval.

| field | type | what it means | example |
|---|---|---|---|
| `hospital_id` | str | The id a claim points at. | `"H-114"` |
| `name` | str | Display name. | `"Riverside General"` |
| `panel` | bool | `true` = inside the insurer's network. `false` changes the outcome and must be recorded. | `true` |
| `country` | str | Where the hospital is. All shipped rows are `SG`. | `"SG"` |

#### `required_documents.json` — 3 rows

Which procedures cannot be assessed without a specific document attached. This is what turns a claim into an *ask* rather than an approve or a decline.

| field | type | what it means | example |
|---|---|---|---|
| `procedure_code` | str | The procedure that triggers the requirement. | `"62480"` |
| `document` | str | The document that must be present. Compare with the claim's `documents` list; a missing one is an *ask*, not a refusal. | `"discharge_summary"` |

#### `decided_claims.json` — 4 rows

History — claims already dealt with, and the only way to recognise a resubmission. **Exactly one row in the queue is a true duplicate of a row here.** Two of the others are deliberate near-misses: each matches a claim on three of the four facts and differs on the fourth, so a shortcut match produces a false positive. Match on member, hospital, date of service **and** lines.

| field | type | what it means | example |
|---|---|---|---|
| `claim_id` | str | The id of the earlier claim — cite it in your record. Matching does **not** use it; a resubmission arrives with a new id. | `"CLM-8710"` |
| `member_id` | str | Part of the duplicate match. One row here differs from a queued claim on this field alone. | `"M-2214"` |
| `hospital_id` | str | Part of the duplicate match. | `"H-114"` |
| `date_of_service` | str | Part of the duplicate match. One row here differs from a queued claim on this field alone. | `"2026-08-20"` |
| `lines` | list[{code, amount}] | Part of the duplicate match, and the one most often skipped. **Same member + same hospital + same date + same lines = the same episode**, whatever the claim id says. One row here shares all three other facts with a queued claim and differs only in its lines — that claim is *not* a duplicate. | `[{"code": "47120", "amount": 1500}]` |
| `decision` | str | What was decided the first time round. | `"approve_in_principle"` |
| `decided_on` | str | When it was decided. | `"2026-08-22"` |

### Problem B · outpatient referral coordination

#### `referrals.json` — 15 rows

**The work queue. One row = one agent run.** A GP has referred a patient to a hospital specialty. The row carries the patient, the specialty, the date, the tests attached and the GP's free-text clinical summary — and that prose, not any id, is what decides how urgent this is and whether it is safe to book at all.

| field | type | what it means | example |
|---|---|---|---|
| `referral_id` | str | Unique id for this referral. | `"REF-5590"` |
| `patient_id` | str | Who is being referred. Joins to **both** `patients.json` and `contacts.json` — they share this key. | `"P-1192"` |
| `referring_clinic` | str | Which GP practice sent it. Context for the record; carries no rule. | `"Bedok Family Practice"` |
| `specialty` | str | Which department it was sent to, as a code. Joins to `specialties.json`, and is half the key into `clinic_slots.json`. | `"OPH"` |
| `date_received` | str | When the referral arrived. **Windows are counted from `as_of.json`, not from this field** — a common and silent mistake. | `"2026-09-08"` |
| `clinical_summary` | str | **The GP's free text, and the most important field in Problem B.** Two decisions come out of it and out of nothing else: whether a red-flag term appears, and which urgency band applies. It is also written by someone outside your organisation, so it is untrusted input. | `"Sudden visual loss in the right eye on wak…` |
| `tests_attached` | list[str] | Test codes actually attached. Compare against the specialty's `mandatory_tests`; anything missing makes this a request, not a booking. | `["VF-01"]` |
| `tests_attached_on` | str · **optional** (12 of 15 rows) | When the tests were done. **Absent on some rows** — absence means no test was attached, so your loader must not assume the key exists. | `"2026-09-05"` |

#### `specialties.json` — 5 rows

**The department's protocol, expressed as data.** For each specialty: which tests must be attached before anyone books, which phrases mean stop and escalate, and which body words indicate the referral was sent to the right department. You are automating this protocol, not rewriting it.

| field | type | what it means | example |
|---|---|---|---|
| `code` | str | The specialty code a referral names. | `"OPH"` |
| `name` | str | Full department name, for the record. | `"Ophthalmology"` |
| `mandatory_tests` | list[{code, name}] | Tests that must be attached before a booking is allowed, each with a `code` and a readable `name`. Missing one ends the run as a request for information. | `[{"code": "VF-01", "name": "visual field te…` |
| `red_flag_terms` | list[str] | Phrases that mean **stop and escalate immediately**. Checked against `clinical_summary`. A red flag outranks everything else, including an available slot. | `["sudden visual loss", "flashes and floater…` |
| `treats` | list[str] | Body words this department handles. Used to tell whether a referral reached the right department at all. | `["eye", "vision", "visual", "retina", "cata…` |

#### `urgency_bands.json` — 3 rows

How soon the patient must be seen, and the phrases that put them in each band. Three bands: urgent (2 weeks), soon (4), routine (8). The window is counted from `as_of.json`, not from the referral date.

| field | type | what it means | example |
|---|---|---|---|
| `band` | str | `urgent`, `soon` or `routine`. Also half the key into `clinic_slots.json`. | `"urgent"` |
| `window_weeks` | int | How many weeks from `as_of` the appointment must fall inside. Urgent 2, soon 4, routine 8. | `2` |
| `trigger_terms` | list[str] | Phrases in `clinical_summary` that put a referral in this band. No trigger found means the routine band. | `["worsening over days", "rapidly worsening"…` |

#### `clinic_slots.json` — 22 rows

Every appointment slot that exists, per clinic, per band, with what is left. `capacity_remaining: 0` means the slot exists and is **full** — that is a different fact from the slot not existing, and your agent must not confuse them.

| field | type | what it means | example |
|---|---|---|---|
| `clinic` | str | The clinic offering the slot. Record this on a booking. | `"OPH-C1"` |
| `specialty` | str | Which department the slot belongs to. Half the lookup key. | `"OPH"` |
| `band` | str | Which urgency band the slot serves. The other half. **A routine slot cannot take an urgent referral**, even if the date fits. | `"urgent"` |
| `date` | str | Slot date. Must fall inside the window measured from `as_of`. | `"2026-09-15"` |
| `time` | str | Slot time. Record it on a booking. | `"09:40"` |
| `capacity_remaining` | int | Places left. **`0` means full, not missing** — the slot exists and cannot be booked. Take the first slot with a value above zero. | `1` |

#### `patients.json` — 7 rows

Who the patient is and what they already have booked. `existing_appointments` is how a duplicate referral is caught — but only a *future* appointment in the *same* specialty counts.

| field | type | what it means | example |
|---|---|---|---|
| `patient_id` | str | The id a referral points at. | `"P-1180"` |
| `date_of_birth` | str | For the record. No rule depends on it. | `"1968-03-14"` |
| `existing_appointments` | list[{specialty, clinic, date}] | What this patient already has booked, each with `specialty`, `clinic` and `date`. **A duplicate needs both: the same specialty AND a date in the future.** A past appointment in the same specialty is not a duplicate. An empty list is normal. | `[{"specialty": "ORT", "clinic": "ORT-C1", "…` |

#### `contacts.json` — 7 rows

How the department would write back — one preferred channel per patient. Reached directly from the referral's `patient_id`; it is not a hop through `patients`. Values are masked, as real contact details would be.

| field | type | what it means | example |
|---|---|---|---|
| `patient_id` | str | The id a referral points at — the same key as `patients.json`, reached directly from the referral. | `"P-1180"` |
| `method` | str | Preferred channel: `sms`, `phone` or `email`. Record which one you would use. | `"sms"` |
| `value` | str | The masked address or number. Masked deliberately; you are recording an intent to contact, not sending anything. | `"+65 8••• ••21"` |

#### `as_of.json` — single object

**The clock.** A single date. Every urgency window in Problem B is measured from it, so it decides which slots are legal for every case. Change it and the answer key stops being true.

| field | type | what it means | example |
|---|---|---|---|
| `as_of` | str | **Today, for Problem B.** Every urgency window is counted forward from this date. | `"2026-09-09"` |
<!-- END GENERATED -->

---

## How the files connect

A record does not carry the facts needed to decide it. **It carries ids**, and your agent
follows them. This is the part worth reading twice.

### First, the notation

The maps below use one piece of shorthand. `lines[].code` means:

> take the `lines` list on this row, and for **every object in it**, read its `code` field.

So a claim whose `lines` is

```json
[{"code": "47120", "amount": 1400},
 {"code": "62480", "amount": 780},
 {"code": "31255", "amount": 300}]
```

has **three** codes — `47120`, `62480`, `31255` — and every arrow drawn from
`lines[].code` fires **once per code**, not once per claim.

**This is the single most important sentence on this page.** It is why a claim is not one
lookup but *n* lookups, why claims vary in length (nine of the fifteen have one line, six
have two to four), why an agent that checks only the first line quietly approves things it
should refuse — and why Problem A has something to parallelise at all: those *n* lookups
do not depend on each other, so they can go in one turn.

`existing_appointments[].specialty` in Problem B reads the same way.

### Problem A

```
    claims.json                      ← the queue: one claim per run
        │
        ├─ member_id ──────────────→ members.json
        │                                │
        │                                └─ policy_id ──→ policies.json
        │                                                    status, dates,
        │                                                    annual_limit − used_to_date,
        │                                                    exclusions[] (with rule id)
        │
        ├─ hospital_id ────────────→ hospitals.json          panel: true | false
        │
        ├─ lines[].code ───────────→ procedures.json         requires_preauth: true | false
        │   (ONCE PER LINE)              │
        │                                │  ONLY IF requires_preauth is true
        │                                └───────────────→ preauthorisations.json
        │                                                    matched on member_id
        │                                                    + procedure_code,
        │                                                    and the date of service
        │                                                    must fall inside
        │                                                    valid_from … valid_to
        │
        ├─ lines[].code ───────────→ required_documents.json is a document needed,
        │   (ONCE PER LINE)                                  and was it attached?
        │
        └─ member + hospital + date
           + lines ──────────────→ decided_claims.json     has this already been decided?
                                                             ALL FOUR must match.
                                                             Three of the four rows
                                                             here are near-misses.
```

**Read the arrow marked ONLY IF.** That branch is why Problem A needs a loop rather than
a checklist: `procedures.requires_preauth` decides whether your agent makes another call
or stops, and the claim decides that, not you.

**And read the last arrow, because it is the easiest one to get wrong.** The duplicate
check does not match on `claim_id` — a resubmission arrives with a *new* id. It matches
on the facts, and it matches on **all four of them**.

`decided_claims.json` holds four rows and only one queued claim is a true duplicate of
any of them. The other three history rows are **near-misses**, each differing from a real
claim on exactly one fact:

| History row | Looks like | Differs on |
|---|---|---|
| `CLM-8710` | `CLM-8933` | **nothing — this is the true duplicate** |
| `CLM-8702` | `CLM-8850` | the date of service |
| `CLM-8726` | `CLM-8960` | the lines |
| `CLM-8688` | nothing | it is just history |

So an agent that matches on the date alone, or on member and date, or on member,
hospital and date — **wrongly escalates a claim that is perfectly fine**. Only the full
comparison, lines included, gets all fifteen right.

### Problem B

Problem B has **no `lines[]`** — a referral is one patient, one specialty, one decision,
so nothing here fires once per line. What it has instead is a **chain of gates**, and
each one can end the run. The `ONLY IF` markers below are the equivalent of Problem A's
branch, and there are four of them rather than one.

```
    referrals.json                   ← the queue: one referral per run
        │
        ├─ specialty ──────────────→ specialties.json        mandatory_tests[]
        │                                                    red_flag_terms[]
        │                                                    treats[]
        │
        │   ── GATE 1 ───────────────────────────────────────────────────────
        ├─ clinical_summary ──────→ specialties.red_flag_terms
        │       (free text)                    a term matches?  ESCALATE, STOP
        │
        │   ── GATE 2 ──── ONLY IF no red flag ──────────────────────────────
        ├─ clinical_summary ──────→ specialties.treats
        │       (free text)                    wrong department?  ESCALATE, STOP
        │
        │   ── GATE 3 ──── ONLY IF the department is right ───────────────────
        ├─ tests_attached ────────→ specialties.mandatory_tests
        │                                      one missing?  REQUEST INFO, STOP
        │
        │   ── GATE 4 ──── ONLY IF every mandatory test is attached ──────────
        ├─ patient_id ────────────→ patients.json            existing_appointments[]
        │                                      same specialty AND in the future?
        │                                                     ESCALATE, STOP
        │                                      in the past = NOT a duplicate
        │
        │   ── ONLY IF all four gates pass do you ever look at a slot ────────
        ├─ clinical_summary ──────→ urgency_bands.trigger_terms  → window_weeks
        │       (free text)                    no trigger = routine
        │
        ├─ specialty + band ──────→ clinic_slots.json        first slot with
        │                                                     capacity_remaining > 0
        │                                                     inside the window;
        │                                                     none?  ESCALATE
        │
        └─ patient_id ────────────→ contacts.json            how you would write back
                                                   (direct from the referral — the same
                                                    key as patients.json, not a hop
                                                    through it)
```

**Notice what the free text does.** Three of those hops are decided by prose a general
practitioner typed, not by an id: the red flag, the department check and the urgency
band all come out of `clinical_summary`. That is where this problem is hard, and it is
why your negative cases matter more here than in Problem A.

**Notice the order, because it is the whole difference between the two problems.** In
Problem A the branch is *how many* calls to make — the run gets longer or shorter but it
always reaches a decision. In Problem B the branches are *whether to continue at all*.
An early exit is correct behaviour, not a truncated run, and an agent that queries a slot
after finding a red flag has failed the case even if it never books.

**And notice the last arrow.** `contacts.json` is reached straight from the referral's
`patient_id`. It is not read through `patients.json`; both files simply key on the same
id. Reading it as a two-hop chain makes the run one turn longer than it needs to be.

### The clock — Problem B only

`data_B/as_of.json` holds **2026-09-09**. Every window is measured from it: a referral
received on that date in the urgent band may be booked up to 2026-09-23, and no later.
Move the clock and every window moves with it, and the answer key stops being true.
Leave it alone until you understand what it controls.

Problem A's dates are absolute and need no clock.

---

## The answer keys

**There is one for each problem, and they are equals.** `expected_outcomes_A.json` labels
all 15 claims; `expected_outcomes_B.json` labels all 15 referrals. Same shape, same rules,
written at the same time — if you chose Problem A, your key is `_A`.

Each labels **every record in the starting set** with the outcome the routing table in
Appendix A requires, and the single trigger that produces it.

| field | in | what it is |
|---|---|---|
| `case_id` | both | joins to `claim_id` (A) / `referral_id` (B) |
| `expected_decision` | both | the outcome. **A:** `approve_in_principle` · `request_document` · `escalate`. **B:** `book` · `request_information` · `escalate` |
| `trigger` | both | escalations only — the **one** reason |
| `missing` | both | requests only — the **one** named thing |
| `booked` | **B only** | bookings only — clinic, date, time. Problem A never books anything, so this field does not appear in `_A` |
| `family` | both | which negative-case family this record exercises |
| `must_record` | both | what a full-marks decision record carries for this case, beyond the decision |
| `note` | both | why the case is here |

One row from each, so you can see they are the same thing:

```json
// expected_outcomes_A.json — a claim that is partly payable
{ "case_id": "CLM-8842",
  "expected_decision": "approve_in_principle",
  "family": "partly_payable",
  "must_record": ["a disposition for all 3 lines",
                  "31255 refused under EX-14 cosmetic dermatology",
                  "PA-5521 cited for line 62480",
                  "approved_total 2180", "refused_total 300"] }

// expected_outcomes_B.json — a referral that must not be booked
{ "case_id": "REF-5590",
  "expected_decision": "escalate",
  "trigger": "red_flag_term",
  "family": "red_flag",
  "must_record": ["the red-flag term \"sudden visual loss\"",
                  "escalate_to triage nurse",
                  "that an urgent slot on 2026-09-15 existed and was NOT taken"] }
```

**How to use it.** Join on `case_id`, compare your agent's decision, then compare the
trigger. **A run that reaches the right outcome by the wrong trigger is not a pass** — it
got there by luck, and it will not get there next time.

**What it does not do.** It labels the 15 records you were given, not the 30–50 your
evaluation set needs. It also labels the *decision*, not the turn count, the wording, or
the cost — two agents can both be right here and cost very different amounts, which is
the subject of D6.

---

## The data is not uniform, and that is deliberate

Several shipped records are edge cases: values that sit just inside a boundary, dates
that look like one thing and are another, and free text that imitates a tool result.
They are there because your evaluation set has to catch exactly that kind of thing, and
because an agent that passes only the easy records has not been tested.

**If a record surprises you, read it carefully before assuming it is a mistake.** If you
still think it is one, see the last section — reporting it earns credit.

---
## Extending the data

You will have to. D4 wants **30–50 cases with 6–10 negatives**, and 15 are shipped, so you
are writing roughly 25 more.

> **The full guide is a separate document: `PE6201_A2_Adding_Extra_Cases.pdf`, on
> NTULearn.** It has the coverage plan for a 40-case set, two fully worked examples you can
> copy — a second duplicate claim for Problem A and a duplicate-appointment referral for
> Problem B — and the rules about writing labels. What follows here is the quick
> reference; the PDF is the authority.

### The rule

**Add new rows with new ids. Never edit or delete a shipped row.**

The shipped records are what a marker re-runs your harness against, and the answer key is
written against them. Within that rule you may add to **any** table, not only the queue.

### Where to type

You never edit a JSON file by hand. You edit one Python file, in one place, and re-run it.

| | Problem A | Problem B |
|---|---|---|
| **Open** | `make_fixtures_A.py` | `make_fixtures_B.py` |
| **Search for** | `EXTRA_PROCEDURES` | `EXTRA_SPECIALTIES` |
| **You land** | ~40 lines from the bottom | ~35 lines from the bottom |

That block of empty lists is the **only** part of the file you touch — the comment beside
each list is the shape of one row. Everything above it is shipped data.

Use ids that are obviously yours: claims from `CLM-9001`, members `M-7001`, policies
`POL-8001`, referrals `REF-6001`, patients `P-2001`.

### The answer key grows — and you write it by hand

There is **one** answer key per problem and it is the same file throughout.
`expected_outcomes_A.json` starts as 15 rows and ends as however many your set holds: our
15, whose labels you must not change, plus one row per case you write. Your harness joins
on `case_id` and does not care which is which.

**Nothing generates those rows.** A script that could work out the right answer would be
the agent you are being asked to build. `check_my_data.py` checks that a label *exists*;
it never checks whether it is *right*.

**Write the label from the routing table in Appendix A, before you run the agent.** A key
written from your agent's output measures nothing — it agrees with itself by
construction. When the agent later disagrees with your key, that is the finding: either a
real bug, or a label you got wrong and should fix and say so. The PDF explains how to tell
the difference.

### The loop

```bash
# 1 · edit the EXTRA_* lists near the bottom of make_fixtures_A.py / _B.py
python3 make_fixtures_A.py        # 2 · regenerate
python3 check_my_data.py          # 3 · names anything broken or unlabelled
# 4 · add the label to expected_outcomes_A.json / _B.json  <- BY HAND
python3 check_my_data.py          # 5 · "Your data hangs together."
```

Steps 2 to 5 take seconds. **Run them after every change**, not once at the end.

`check_my_data.py` catches the four things that actually go wrong, all of them silent:

1. **An id that resolves to nothing** — a claim whose `member_id` matches nobody. Your
   tool returns nothing, your agent reasons about nothing, and **the run looks fine.**
2. **A shipped record that changed** — it holds a fingerprint of every shipped row and
   names the one that moved.
3. **A duplicate id** — two claims called `CLM-9001`; one of them is invisible.
4. **A case with no label, or a label with no case.**

### Submit the key

**Your extended answer key is a submitted artefact.** It goes in the repository alongside
the agent, together with the generator you edited and the generated data. A pass rate
submitted without the key it was measured against is not a measurement — nobody can
reproduce it, and a marker who clones your repository will try.

## Found a problem? Tell me, and it counts

This data was written for this assignment and has not been through a hundred hands. If
you find a record that contradicts itself, a field that is never populated, or something
in the brief that cannot be satisfied against this data — **email me, and early.**
Acknowledged bugs earn credit under Class Participation.

You are not required to wait for a fix. Say in your repository what you found, what you
assumed instead, and carry on.
