# PE6201 A2 - Group 9

Coursework repository for NTU PE6201 Assignment 2: Applied AI System.

This project is under active development.

## Repository structure

- `A2_scaffold/`: Python single-agent ReAct loop, tools, guardrails, backends,
  evaluation harness, and guided notebooks.
- `A2_scaffold/docs/`: D2 (tool layer) and D3 (guardrails) deliverables for
  Problem A, with reproducible commands and the live-model evidence behind
  every claim. See "D2 / D3 status" below.
- `A2_reference_data/`: reference JSON data, expected outcomes, fixture
  generators, and data validation utilities.
- `documents/`: assignment briefs and team working documents.
- `流程.md`: implementation notes and workflow analysis.
- `交接(1).md`: D2/D3 handover notes - current status and where to pick up
  next is at the top of the file.
- `A2_scaffold.zip` and `A2_reference_data.zip`: original packaged materials.

## D2 / D3 status (Problem A)

D2 (tool layer) and D3 (guardrails) are done. Read
[`A2_scaffold/docs/D2_tool_layer.md`](A2_scaffold/docs/D2_tool_layer.md) and
[`A2_scaffold/docs/D3_guardrails.md`](A2_scaffold/docs/D3_guardrails.md)
first - they hold the tool-set decisions, the v1-vs-v2 prompt comparison
(real live-model numbers), the guardrail limit justifications, and all 11
D3(b) test cases (3 of them adversarial narratives).

Supporting scripts, all runnable from `A2_scaffold/`:

```bash
python3 guardrail_tests.py        # D3(b), 11 cases, scripted, free
python3 dev_seq_vs_parallel.py    # D2(c) sequential vs parallel, scripted, free
python3 dev_v1_v2_compare.py      # D2(b) v1/v2, LIVE - needs OPENROUTER_API_KEY, costs money
```

`issue_decision_letter()` now genuinely appends to `A2_scaffold/decisions.jsonl`
(gitignored, like `results.json`) every time it runs. `check_duplicate_claim`'s
signature changed to a single `claim_id` argument - update any hand-written
script or notebook cell still calling it with the old four arguments.

## Run locally

The scaffold uses only the Python standard library.

```bash
cd A2_scaffold
python3 run_eval.py --prompt
python3 run_eval.py
```

Reference data is discovered automatically when `A2_reference_data/` is next
to `A2_scaffold/`. Set `A2_DATA` if the data directory is stored elsewhere.

The backend and selected assignment problem are configured in
`A2_scaffold/config.py`. The live backend requires `OPENROUTER_API_KEY` in the
environment; API keys must never be committed to this repository.

## Validate reference data

```bash
cd A2_reference_data
python3 check_my_data.py
```
