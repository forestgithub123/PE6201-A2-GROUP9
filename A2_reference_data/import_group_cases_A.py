#!/usr/bin/env python3
"""Import the six independently-authored Problem A case bundles.

The source bundles reuse CLM-9101..9108 and CLM-9201..9208, so this importer
assigns a stable, non-overlapping range to each contributor and updates the
matching expected-outcome ids. It is safe to run repeatedly: previously
imported rows in these ranges are replaced, while the shipped rows are kept.
"""

import copy
import json
import os


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLAIMS_PATH = os.path.join(HERE, "data_A", "claims.json")
OUTCOMES_PATH = os.path.join(HERE, "expected_outcomes_A.json")

# source filename -> first id in its assigned eight-case range
SOURCES = [
    ("wsm_data_A.json", 9001),
    ("liuyalin_data_A.json", 9101),
    ("gcx_data_A.json", 9201),
    ("zhangyushuang_data_A.json", 9301),
    ("huangyiqian_data_A.json", 9401),
    ("wangyue_data_A.json", 9501),
]

# Corrections required by the fixed Problem A routing table. These are keyed
# by source file and source id, before ids are remapped.
OUTCOME_CORRECTIONS = {
    ("liuyalin_data_A.json", "CLM-9108"): {
        "trigger": "policy_lapsed",
    },
    ("zhangyushuang_data_A.json", "CLM-9203"): {
        "trigger": "policy_lapsed",
    },
    ("zhangyushuang_data_A.json", "CLM-9204"): {
        "expected_decision": "request_document",
        "missing": "current pre-authorisation for line 29881, valid on 2026-09-18",
        "family": "preauth_expired",
        "trigger": None,
    },
    ("zhangyushuang_data_A.json", "CLM-9208"): {
        "expected_decision": "request_document",
        "missing": "itemised bill for line 45378",
        "family": "required_document_absent",
        "trigger": None,
    },
    ("wangyue_data_A.json", "CLM-9106"): {
        "expected_decision": "escalate",
        "trigger": "annual_limit_exceeded",
        "family": "annual_limit_exceeded",
        "must_record": [
            "claim total 1400",
            "600 remaining on POL-4102",
            "that lines were not individually priced",
        ],
        "note": "The annual-limit rule fires before line-level processing.",
    },
}


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def dump(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def remap_for(source_name, claims):
    """Return source claim id -> stable destination claim id."""
    start = dict(SOURCES)[source_name]
    if len(claims) != 8:
        raise ValueError("%s must contain exactly 8 claims" % source_name)
    return {
        claim["claim_id"]: "CLM-%04d" % (start + index)
        for index, claim in enumerate(claims)
    }


def main():
    existing_claims = load(CLAIMS_PATH)
    existing_outcomes = load(OUTCOMES_PATH)
    imported_ids = {
        "CLM-%04d" % number
        for _, start in SOURCES
        for number in range(start, start + 8)
    }

    # Makes reruns idempotent without modifying the original shipped rows.
    claims = [row for row in existing_claims
              if row.get("claim_id") not in imported_ids]
    outcomes = [row for row in existing_outcomes
                if row.get("case_id") not in imported_ids]

    for source_name, _ in SOURCES:
        bundle = load(os.path.join(ROOT, source_name))
        source_claims = bundle.get("claims", [])
        source_outcomes = bundle.get("expected_outcomes", [])
        id_map = remap_for(source_name, source_claims)
        if {row.get("case_id") for row in source_outcomes} != set(id_map):
            raise ValueError("%s claims and expected outcomes do not match"
                             % source_name)

        for source_claim in source_claims:
            claim = copy.deepcopy(source_claim)
            claim["claim_id"] = id_map[source_claim["claim_id"]]
            claims.append(claim)

        for source_outcome in source_outcomes:
            source_id = source_outcome["case_id"]
            outcome = copy.deepcopy(source_outcome)
            correction = OUTCOME_CORRECTIONS.get((source_name, source_id), {})
            outcome.update(correction)
            if outcome.get("trigger") is None:
                outcome.pop("trigger", None)
            outcome["case_id"] = id_map[source_id]
            outcomes.append(outcome)

    claim_ids = [row["claim_id"] for row in claims]
    outcome_ids = [row["case_id"] for row in outcomes]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("duplicate claim id after import")
    if len(outcome_ids) != len(set(outcome_ids)):
        raise ValueError("duplicate expected-outcome id after import")
    if set(claim_ids) != set(outcome_ids):
        raise ValueError("claims and expected outcomes differ after import")

    dump(CLAIMS_PATH, claims)
    dump(OUTCOMES_PATH, outcomes)
    print("Imported 48 group cases; Problem A now has %d cases." % len(claims))


if __name__ == "__main__":
    main()
