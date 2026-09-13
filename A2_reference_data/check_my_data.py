#!/usr/bin/env python3
"""
PE6201 · A2 — check your data
=============================
RUN THIS EVERY TIME YOU ADD RECORDS.

    python3 check_my_data.py

It catches the four things that go wrong when a team extends the fixture data,
and it catches them in seconds rather than in an evening of debugging an agent
that is behaving perfectly.

  1. AN ID THAT RESOLVES TO NOTHING.
     A claim whose member_id matches no member. A referral naming a specialty
     that does not exist. Your tool returns nothing, your agent reasons about
     nothing, and the run looks superficially fine. This is the single most
     expensive mistake available to you here, and it is completely silent.

  2. A SHIPPED RECORD THAT CHANGED.
     The records we gave you are the ones a marker re-runs your harness against,
     and the answer key is written against them. Add freely; edit nothing. This
     script holds a fingerprint of every shipped row and will tell you exactly
     which one moved.

  3. A DUPLICATE ID.
     Two claims called CLM-9001. One of them is invisible.

  4. A CASE WITH NO LABEL, OR A LABEL WITH NO CASE.
     An unlabelled case cannot be scored. A label pointing at a record you
     deleted is worse - it looks like a pass rate and is not one.

It does NOT check whether your labels are RIGHT. That judgement is yours, and it
is a large part of what D4 is marked on.

Exit code 0 = your data hangs together.
"""

import json
import os
import sys
import hashlib

HERE = os.path.dirname(os.path.abspath(__file__))

# Which field identifies a row, per table. A tuple means the id is composite.
IDS = {
    "procedures": "code", "hospitals": "hospital_id", "policies": "policy_id",
    "members": "member_id", "preauthorisations": "preauth_id",
    "claims": "claim_id", "decided_claims": "claim_id",
    "required_documents": "procedure_code",
    "specialties": "code", "urgency_bands": "band",
    "clinic_slots": ("clinic", "date", "time"),
    "patients": "patient_id", "contacts": "patient_id",
    "referrals": "referral_id",
}

# (table, path to the id inside a row, table it must exist in, that table's key).
# "lines[].code" means: for each item in the row's `lines` list, take `code`.
LINKS = {
    "A": [
        ("claims", "member_id", "members", "member_id"),
        ("claims", "hospital_id", "hospitals", "hospital_id"),
        ("claims", "lines[].code", "procedures", "code"),
        ("members", "policy_id", "policies", "policy_id"),
        ("preauthorisations", "member_id", "members", "member_id"),
        ("preauthorisations", "procedure_code", "procedures", "code"),
        ("policies", "exclusions[].code", "procedures", "code"),
        ("required_documents", "procedure_code", "procedures", "code"),
        ("decided_claims", "member_id", "members", "member_id"),
        ("decided_claims", "lines[].code", "procedures", "code"),
    ],
    "B": [
        ("referrals", "patient_id", "patients", "patient_id"),
        ("referrals", "specialty", "specialties", "code"),
        ("clinic_slots", "specialty", "specialties", "code"),
        ("clinic_slots", "band", "urgency_bands", "band"),
        ("patients", "existing_appointments[].specialty", "specialties", "code"),
        ("contacts", "patient_id", "patients", "patient_id"),
    ],
}

QUEUE = {"A": ("claims", "claim_id"), "B": ("referrals", "referral_id")}
DECISIONS = {
    "A": {"approve_in_principle", "request_document", "escalate"},
    "B": {"book", "request_information", "escalate"},
}

problems, warnings = [], []


def fail(msg):
    problems.append(msg)


def warn(msg):
    warnings.append(msg)


def load(letter, name):
    path = os.path.join(HERE, "data_%s" % letter, name + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def row_id(table, row):
    k = IDS[table]
    if isinstance(k, tuple):
        return "|".join(str(row.get(x, "?")) for x in k)
    return str(row.get(k, "?"))


def fingerprint(row):
    return hashlib.sha1(
        json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:10]


def values_at(row, path):
    """Resolve 'lines[].code' or 'member_id' to a list of values."""
    if "[]." in path:
        outer, inner = path.split("[].")
        return [item.get(inner) for item in row.get(outer, []) or []]
    v = row.get(path)
    return [] if v is None else [v]


# ─────────────────────────────────────────────────────────────────────────────
def check_problem(letter):
    tables = {}
    for table in [t for t in IDS if t in [x[0] for x in LINKS[letter]]
                  or t in [x[2] for x in LINKS[letter]]
                  or t == QUEUE[letter][0]]:
        rows = load(letter, table)
        if rows is not None:
            tables[table] = rows
    if not tables:
        return False

    print("\nProblem %s" % letter)
    for name in sorted(tables):
        print("   %4d  %s" % (len(tables[name]), name))

    # 3 · duplicate ids ------------------------------------------------------
    for table, rows in tables.items():
        seen = {}
        for row in rows:
            rid = row_id(table, row)
            if rid in seen:
                fail("%s: TWO rows share the id %r. One of them can never be found."
                     % (table, rid))
            seen[rid] = row

    # 1 · every id resolves --------------------------------------------------
    for src, path, dst, dstkey in LINKS[letter]:
        if src not in tables or dst not in tables:
            continue
        known = {r.get(dstkey) for r in tables[dst]}
        for row in tables[src]:
            for v in values_at(row, path):
                if v not in known:
                    fail("%s %s: %s = %r does not exist in %s.json"
                         % (src, row_id(src, row), path, v, dst))

    # 2 · shipped rows unchanged ---------------------------------------------
    shipped = SHIPPED.get(letter, {})
    for table, prints in shipped.items():
        if table not in tables:
            fail("%s.json is missing entirely." % table)
            continue
        have = {row_id(table, r): fingerprint(r) for r in tables[table]}
        for rid, fp in prints.items():
            if rid not in have:
                fail("%s: shipped row %r has been DELETED. Add records, remove none."
                     % (table, rid))
            elif have[rid] != fp:
                fail("%s: shipped row %r has been EDITED. The answer key is written "
                     "against the original." % (table, rid))

    # a few things that are legal but almost always a mistake ----------------
    if letter == "A" and "preauthorisations" in tables:
        needs = {p["code"] for p in tables.get("procedures", [])
                 if p.get("requires_preauth")}
        for pa in tables["preauthorisations"]:
            if pa.get("procedure_code") not in needs:
                warn("preauthorisations %s authorises %s, but that procedure does "
                     "not require one - your agent will never look for it."
                     % (pa.get("preauth_id"), pa.get("procedure_code")))
    if letter == "B" and "patients" in tables and "contacts" in tables:
        have = {c["patient_id"] for c in tables["contacts"]}
        for p in tables["patients"]:
            if p["patient_id"] not in have:
                warn("patients %s has no row in contacts.json." % p["patient_id"])
        bands = {b["band"] for b in tables.get("urgency_bands", [])}
        served = {s["band"] for s in tables.get("clinic_slots", [])}
        for b in bands - served:
            warn("urgency band %r has no clinic slots at all. Every referral in "
                 "that band will escalate - deliberate?" % b)

    # 4 · labels ---------------------------------------------------------------
    qtable, qkey = QUEUE[letter]
    keypath = os.path.join(HERE, "expected_outcomes_%s.json" % letter)
    if not os.path.exists(keypath):
        warn("expected_outcomes_%s.json not found - skipping the label check." % letter)
        return True
    with open(keypath, encoding="utf-8") as fh:
        key = json.load(fh)
    labelled = {}
    for row in key:
        cid = row.get("case_id")
        if cid in labelled:
            fail("answer key %s: %r is labelled twice." % (letter, cid))
        labelled[cid] = row
    cases = {r[qkey] for r in tables.get(qtable, [])}

    for cid in sorted(cases - set(labelled)):
        fail("%s has no label in expected_outcomes_%s.json - it cannot be scored."
             % (cid, letter))
    for cid in sorted(set(labelled) - cases):
        fail("expected_outcomes_%s.json labels %r, but no such record exists."
             % (letter, cid))

    for cid, row in labelled.items():
        dec = row.get("expected_decision")
        if dec not in DECISIONS[letter]:
            fail("%s: expected_decision %r is not one of %s"
                 % (cid, dec, sorted(DECISIONS[letter])))
        if dec == "escalate" and not row.get("trigger"):
            fail("%s: an escalation with no single trigger. Which one rule sent it "
                 "to a human?" % cid)
        if dec in ("request_document", "request_information") and not row.get("missing"):
            fail("%s: a request with nothing named. \"More information required\" "
                 "scores nothing." % cid)
        if dec == "book" and not row.get("booked"):
            fail("%s: a booking with no clinic, date and time." % cid)
    return True


def main():
    print("Checking your fixture data …")
    found = [l for l in ("A", "B") if check_problem(l)]
    if not found:
        sys.exit("\nNo data_A/ or data_B/ found. Run the generators first.")

    print()
    for w in warnings:
        print("  note  " + w)
    for p in problems:
        print("  FAIL  " + p)

    if problems:
        print("\n%d problem(s). Fix these before you trust a single result."
              % len(problems))
        return 1
    print("\nYour data hangs together%s." %
          ("  (%d note(s) above)" % len(warnings) if warnings else ""))
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Fingerprints of the rows we shipped. Generated - do not edit by hand.
# ─────────────────────────────────────────────────────────────────────────────
SHIPPED = json.loads(r"""{
 "A": {
  "claims": {
   "CLM-8842": "4ad613af83",
   "CLM-8850": "5a40474c46",
   "CLM-8861": "9ec4a51f5c",
   "CLM-8874": "eb5e59f6f7",
   "CLM-8888": "330ac54920",
   "CLM-8894": "6fea844b05",
   "CLM-8901": "14573662c5",
   "CLM-8910": "cd160f79c6",
   "CLM-8917": "ab38b18cf0",
   "CLM-8925": "7f349c185c",
   "CLM-8933": "d36eac8df2",
   "CLM-8941": "5f1ca5d4b3",
   "CLM-8952": "6aeeb8f5de",
   "CLM-8960": "ca977e2e1a",
   "CLM-8971": "32bf06058b"
  },
  "decided_claims": {
   "CLM-8688": "1557c774fc",
   "CLM-8702": "51009fa4e1",
   "CLM-8710": "b59c76cf52",
   "CLM-8726": "22bd7f6199"
  },
  "hospitals": {
   "H-114": "a1dbe4a468",
   "H-207": "74454f8d00",
   "H-330": "f50ad97715",
   "H-451": "d9b5656204"
  },
  "members": {
   "M-2214": "49a60192ef",
   "M-3390": "96485ee473",
   "M-4471": "8146213bd4",
   "M-5502": "4d2c6d9788",
   "M-6118": "883972e3cb"
  },
  "policies": {
   "POL-3310": "464995abe8",
   "POL-4102": "66228cb99e",
   "POL-5588": "cce631a8d4",
   "POL-6001": "3e16b7eec4",
   "POL-7220": "92dc4236d4"
  },
  "preauthorisations": {
   "PA-5521": "4c5917615f",
   "PA-5640": "36233b727c",
   "PA-5702": "b5350316ee"
  },
  "procedures": {
   "15823": "73c4a0ad79",
   "27447": "41ca014e93",
   "29881": "b1d81f9960",
   "31255": "4e43bd0d72",
   "45378": "7026e469a0",
   "47120": "2f536751d7",
   "62480": "5b1d8a32cd",
   "70553": "a524cc31cc",
   "80053": "4169960807",
   "99213": "cb8ed69b10"
  },
  "required_documents": {
   "27447": "73a06f541d",
   "45378": "ef05d66e89",
   "62480": "1f8dc2fe38"
  }
 },
 "B": {
  "clinic_slots": {
   "CARD-C1|2026-09-16|08:30": "dabba78e36",
   "CARD-C1|2026-09-18|15:00": "634ab457f7",
   "CARD-C2|2026-10-21|10:00": "bb64db45fe",
   "CARD-C3|2026-09-25|09:30": "1fe06d294a",
   "DER-C1|2026-09-30|10:40": "ebb187ba8d",
   "DER-C1|2026-10-19|09:00": "50d8a3d0fa",
   "DER-C2|2026-09-24|11:00": "5d617c8553",
   "ENT-C1|2026-10-21|13:20": "5bc04c8b85",
   "ENT-C1|2026-11-10|09:40": "5eea478cf7",
   "ENT-C2|2026-10-06|14:00": "913816a75e",
   "OPH-C1|2026-09-15|09:40": "77c59742fa",
   "OPH-C1|2026-09-22|10:00": "2853f6161b",
   "OPH-C2|2026-09-23|11:20": "dfbfb3bb20",
   "OPH-C2|2026-09-30|11:20": "fef9c97523",
   "OPH-C2|2026-10-14|11:20": "ffc1cef472",
   "OPH-C2|2026-10-14|14:00": "955609b2c8",
   "OPH-C2|2026-10-28|09:00": "6ef2a9d577",
   "OPH-C3|2026-09-29|10:00": "042bc188ce",
   "ORT-C1|2026-10-07|09:20": "dd4fbf7f9e",
   "ORT-C1|2026-10-21|11:00": "08bf8f1ab5",
   "ORT-C2|2026-09-17|14:40": "539e0144f6",
   "ORT-C3|2026-09-28|15:00": "a2acf4109a"
  },
  "contacts": {
   "P-1180": "42aff4fa85",
   "P-1192": "843344f621",
   "P-1204": "72f60a4746",
   "P-1215": "1ddc43a73c",
   "P-1227": "93961f8ff5",
   "P-1233": "b0d3882d03",
   "P-1241": "610a048d02"
  },
  "patients": {
   "P-1180": "0140f59bb4",
   "P-1192": "f17b6ca50c",
   "P-1204": "a426020cbf",
   "P-1215": "d6055e62c6",
   "P-1227": "2256153ad1",
   "P-1233": "8bccef209e",
   "P-1241": "7240d6b509"
  },
  "referrals": {
   "REF-5590": "e56c876954",
   "REF-5602": "e222b4ba7c",
   "REF-5614": "ccdd4a9580",
   "REF-5620": "ee85d3adff",
   "REF-5631": "1f6fcbdabf",
   "REF-5645": "55dc19c516",
   "REF-5658": "162f0608d7",
   "REF-5663": "e6881209ab",
   "REF-5671": "247760df79",
   "REF-5684": "c7f7d448eb",
   "REF-5697": "c11fc37093",
   "REF-5703": "3c79a0c200",
   "REF-5711": "3689622e2c",
   "REF-5725": "aab995868e",
   "REF-5738": "eee6e95467"
  },
  "specialties": {
   "CARD": "d5b312b516",
   "DER": "44f8a7d1bb",
   "ENT": "6dbd72eded",
   "OPH": "3fe6b7234b",
   "ORT": "e38dec8030"
  },
  "urgency_bands": {
   "routine": "5e30a5d72a",
   "soon": "b5d685efd8",
   "urgent": "2b641290d0"
  }
 }
}
""")


if __name__ == "__main__":
    sys.exit(main())
