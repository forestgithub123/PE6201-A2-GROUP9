# PE6201 A2 - Group 9

Coursework repository for NTU PE6201 Assignment 2: Applied AI System.

## Repository structure

- `A2_scaffold/`: Python single-agent ReAct loop, tools, guardrails, backends,
  evaluation harness, and guided notebooks.
- `A2_reference_data/`: reference JSON data, expected outcomes, fixture
  generators, and data validation utilities.
- `documents/`: assignment briefs and team working documents.
- `流程.md`: implementation notes and workflow analysis.
- `A2_scaffold.zip` and `A2_reference_data.zip`: original packaged materials.

## Run locally

The scaffold uses only the Python standard library.

```bash
cd A2_scaffold
python3 run_eval.py --prompt
```

Reference data is discovered automatically when `A2_reference_data/` is next
to `A2_scaffold/`. Set `A2_DATA` if the data directory is stored elsewhere.

The backend and selected assignment problem are configured in
`A2_scaffold/config.py`. The live backend requires `OPENROUTER_API_KEY` in the
environment before running `python3 run_eval.py`; API keys must never be
committed to this repository. Set `BACKEND = "scripted"` for deterministic,
offline evaluation.

## Validate reference data

```bash
cd A2_reference_data
python3 check_my_data.py
```
