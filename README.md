# PE6201 Assignment 2 - Group 9

This repository contains Group 9's implementation and evaluation evidence for
NTU PE6201 Assignment 2, Problem A: health-insurance claim first response.

The submitted system is a single-agent ReAct workflow with a deterministic tool
layer, code-level guardrails, an offline scripted backend, a live OpenRouter
backend, and an evaluation harness. The committed default is fully reproducible
without an API key or network access.

## Current reproducible result

The committed scripted evaluation contains:

- 63 claim cases;
- 109 trials in total;
- one trial for each positive case and three trials for each negative case;
- 109/109 trials passing the deterministic code check;
- median 3 turns and worst case 5 turns;
- zero legitimate runs reaching the configured 8-turn step cap.

These figures are stored in `A2_scaffold/results.json`. A code-check pass rate is
only one part of the evaluation: the reasoning requirements in the generated
`judgement_queue` still require human review.

## Quick start

Requirements:

- Python 3.9 or newer;
- no third-party Python packages for the core scaffold;
- `A2_reference_data/` and `A2_scaffold/` located next to each other.

Run the exact offline evaluation used for reproducibility:

```bash
cd A2_scaffold
python3 run_eval.py
```

The expected startup line begins with `BACKEND=scripted`. This command runs all
cases that have committed scripts, prints one final decision record per case,
prints aggregate metrics, and writes `A2_scaffold/results.json`.

Useful commands:

```bash
cd A2_scaffold

# Inspect the complete system prompt without running a case.
python3 run_eval.py --prompt

# Run one case with every agent turn and tool result visible.
python3 run_eval.py CLM-8842

# Run every case in the work queue. In scripted mode, a missing script fails
# loudly instead of silently omitting the case.
python3 run_eval.py --all

# Reproduce the two D7 controlled failure experiments.
python3 demo_loop_failure.py
python3 demo_tool_failure.py
```

## Evaluation semantics

`A2_reference_data/data_A/claims.json` contains 63 distinct cases, but the full
evaluation contains 109 trials. The harness runs ordinary approval cases once
and negative cases three times because refusal, request, and escalation
behaviour is more likely to vary in a live model.

The system can return three Problem A decisions:

- `approve_in_principle`: all mandatory checks are complete; payable and
  excluded claim lines are recorded separately, and the decision-letter action
  passes the autonomy gate;
- `request_document`: required evidence, such as a valid pre-authorisation or a
  required clinical document, is absent or expired;
- `escalate`: deterministic routing rules require human handling, for example a
  lapsed policy, an out-of-period claim, an annual-limit breach, a duplicate,
  a non-panel hospital, or untrusted system-directed instructions in member
  narrative text.

Two forms of checking are intentionally separated:

1. The deterministic code check compares the decision and trigger against
   `expected_outcomes_A.json`. For approvals it also checks required tool calls,
   line dispositions, totals, pre-authorisation evidence, and the gated action.
2. The judgement queue records qualitative requirements from `must_record`.
   A human reviewer must read the reason and evidence, then fill `verdict` and
   `graded_by`. The software deliberately does not turn this into a substring
   check.

Therefore, `109/109` means every trial passed the code check. It must not be
reported as a completed human judgement review unless the queue has actually
been reviewed.

## Architecture

The main execution path is:

```text
run_eval.py
    -> harness.py loads cases and expected outcomes
    -> agent.py runs the bounded ReAct loop
    -> backends.py supplies the next model move
    -> tools.py performs a narrow lookup or simulated action
    -> guardrails.py checks limits, repetition, and autonomy
    -> agent.py produces an instrumented decision record
    -> harness.py performs the code check and builds the judgement queue
```

Important modules:

- `A2_scaffold/config.py`: backend, model, endpoint, limits, autonomy mode,
  token prices, and data discovery;
- `A2_scaffold/prompt.py`: system instructions and routing rules supplied to a
  live model;
- `A2_scaffold/agent.py`: multi-turn orchestration, final-answer validation,
  retry handling, instrumentation, and explicit stop records;
- `A2_scaffold/tools.py`: data access and simulated external actions;
- `A2_scaffold/guardrails.py`: step cap, token ceiling, duplicate-action memory,
  and autonomy gate;
- `A2_scaffold/backends.py`: deterministic script replay and the vendor-neutral
  OpenRouter-compatible live backend;
- `A2_scaffold/harness.py`: trial policy, deterministic grading, judgement
  queue creation, and aggregate reporting;
- `A2_scaffold/scripted_cases_A.json`: recorded model moves used by the offline
  backend;
- `A2_scaffold/run_eval.py`: command-line entry point used by the marker.

### Scripted backend

`BACKEND = "scripted"` does not simply print stored final answers. It replays
stored model moves while the real agent loop, tools, validation, guardrails, and
grader execute normally. This makes the run deterministic and free while still
testing the implementation surrounding the model.

Scripted token counts and model-equivalent costs are deterministic estimates.
No API call is made, so actual API cost is zero.

### Live backend

`BACKEND = "live"` sends the same prompt and transcript to the model configured
in `config.py` through an OpenAI-compatible OpenRouter endpoint. The backend
reads token usage from the provider response and stores it in each decision
record.

Before a live run:

1. Set `BACKEND = "live"` in `A2_scaffold/config.py`.
2. Set `MODEL` to a valid provider model identifier.
3. Set `PRICE_IN` and `PRICE_OUT` to that model's verified USD-per-million-token
   prices. Historical result files must not be repriced by changing these values
   after a run.
4. Export the key in the shell. Never write a key into the repository.

```bash
export OPENROUTER_API_KEY="sk-or-..."
cd A2_scaffold
python3 run_eval.py --all
```

Live execution costs money. It also depends on provider availability, network
latency, valid model identifiers, and model output conforming to the JSON move
contract. `API_TIMEOUT_SECONDS` and `MAX_OUTPUT_TOKENS` bound each request.

Each run writes `A2_scaffold/results.json`, so preserve a completed live battery
before starting another one:

```bash
cp results.json ../model_trace/results_live_<model-name>.json
```

After live evaluation, restore `BACKEND = "scripted"` before committing the
submission.

## Guardrails and autonomy

The guardrail layer is deterministic code, not another model prompt. It provides:

- a step cap (`MAX_TURNS`);
- a token budget ceiling (`MAX_TOKENS_PER_RUN`);
- exact action de-duplication across turns;
- an autonomy gate immediately before the simulated irreversible action;
- explicit `stopped_by` and `guardrails_fired` evidence in each decision record.

`AUTONOMY` has three modes:

- `suggest`: the action is proposed but held;
- `confirm`: a live run asks a person to approve the action;
- `act`: the action proceeds automatically and the passed gate is still logged.

The committed configuration uses `act` so the marker's offline batch run does
not pause for input. Actions are simulated locally; no real decision letter is
sent.

## D7 failure reproduction

The D7 experiments are controlled working-system-minus-X ablations. Both force
the scripted backend internally, make no network call, and update only
`A2_scaffold/d7_results.json`.

Run them in this order:

```bash
cd A2_scaffold
python3 demo_loop_failure.py
python3 demo_tool_failure.py
```

`demo_loop_failure.py` removes the duplicate-action memory while keeping the
faulty repeated model behaviour fixed. It records the normal run, the fault
caught by the guard, the minus-X run, the restored run, and whole-suite turn
distributions for the configured and loose caps.

`demo_tool_failure.py` removes the service-date validity condition from the
pre-authorisation tool for `CLM-8894`. The faulty interface returns an expired
authorisation and supports an incorrect approval; restoration returns the
correct `request_document` outcome.

The resulting JSON distinguishes estimated scripted tokens and
model-equivalent cost from actual API cost.

## Reference data

Problem A source data is in `A2_reference_data/data_A/`:

- `claims.json`: work queue;
- `members.json`, `policies.json`, and `hospitals.json`: member and policy facts;
- `procedures.json`: procedure coverage and pre-authorisation rules;
- `preauthorisations.json`: dated authorisation records;
- `required_documents.json`: document requirements;
- `decided_claims.json`: evidence used for duplicate detection.

Expected outcomes are stored separately in
`A2_reference_data/expected_outcomes_A.json`. The agent and tools do not read
this file; only the evaluation harness uses it after a run. Runtime guardrails
therefore do not know the expected answer for a new case.

Validate the datasets before evaluating:

```bash
cd A2_reference_data
python3 check_my_data.py
```

If the reference-data folder is not next to `A2_scaffold/`, point the scaffold
to a directory containing both `data_A/` and `data_B/`:

```bash
export A2_DATA=/absolute/path/to/A2_reference_data
```

## Evidence and deliverables

Canonical committed evidence is organised as follows:

- `A2_scaffold/results.json`: current reproducible scripted run and judgement
  queue;
- `A2_scaffold/d7_results.json`: D7 ablation measurements;
- `model_trace/`: preserved live-model result JSON files, including the prompt
  v1/v2 comparison and model battery;
- `output/`: canonical generated report and cost-analysis files;
- `A2_reference_data/`: submitted data, labels, schema documentation, and
  validation utilities;
- `teammate_data/`: source case contributions retained for provenance.

Assignment PDFs, translations, internal workflow notes, downloaded zip
snapshots, temporary rendering files, Office lock files, and duplicate root
exports are intentionally ignored. Local files under `documents/` are not part
of the repository. A completed declaration or self-appraisal that must be
submitted should be placed in a tracked submission location such as `output/`,
not left only under the ignored `documents/` directory.

## Troubleshooting

### Reference data cannot be found

Keep `A2_reference_data/` beside `A2_scaffold/`, or set `A2_DATA` to its absolute
path. The selected directory must contain both `data_A/` and `data_B/`.

### Live mode reports a missing API key

Export `OPENROUTER_API_KEY` in the same terminal session used to run Python.
Do not put the key in `config.py`, a notebook, a trace, or a committed `.env`
file.

### HTTP 400 from a live model

Confirm that `MODEL` is an exact model identifier currently accepted by the
provider. A guessed or unavailable identifier is rejected before the case can
run. If the identifier is valid, inspect the response detail emitted by
`backends.py` for a model-specific request or JSON-format limitation.

### A batch appears stuck while a single case works

A full live battery may require hundreds of sequential API calls because each
case contains multiple turns and negative cases run three times. It can remain
quiet between aggregate outputs. First test one case, then monitor network
errors and per-request timeouts; do not assume the batch has frozen solely
because no case-level output is printed.

### Python appears to ignore a config edit

Remove stale bytecode and rerun:

```bash
cd A2_scaffold
rm -rf __pycache__
```

### `results.json` was overwritten

Every batch run writes the same working filename. Preserve important live runs
under `model_trace/` before changing the model or returning to scripted mode.

## Submission checklist

- `A2_scaffold/config.py` has `BACKEND = "scripted"`.
- `python3 run_eval.py` works from `A2_scaffold/` with no key and no network.
- `python3 ../A2_reference_data/check_my_data.py` reports valid data when run
  from `A2_scaffold/`, or the checker is run directly from its own directory.
- `results.json`, `d7_results.json`, expected outcomes, and live model traces
  correspond to the figures cited in the report.
- Every reported pass rate includes its trial count.
- Human judgement findings are reported separately from code-check accuracy.
- No API key, temporary file, Office lock file, or ignored reference document is
  staged for commit.
- Required final administrative documents are copied to a tracked submission
  location before the final commit.
