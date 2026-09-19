# PE6201 · A2 — starter scaffold

A working single-agent ReAct loop, a tool layer, a guardrail layer, an evaluation
harness and both graders. It runs, out of the box, with no key and no network.

**It is a starting point, not a solution.** It handles two cases — one per problem —
and stops. Everything it does is something you will replace with your own design.

**Start with the notebook for your problem** (`A2_Scaffold_Tour_ProblemA.ipynb` or
`…ProblemB.ipynb`) — it walks the whole machine on one case, with every value printed.
Then work in the modules.

---

## Run it

```bash
cd A2_scaffold
python3 run_eval.py REF-5602          # one case, every turn shown
python3 run_eval.py                   # the scripted cases, graded
python3 demo_loop_failure.py          # D7 failure 1: loop-control ablation
python3 demo_tool_failure.py          # D7 failure 2: tool-interface ablation
python3 run_eval.py --prompt          # exactly what the model is told

python3 run_eval.py CLM-8842          # Problem A, once PROBLEM = "A" in config.py
```

No arguments needed, no packages to install, no network, no API key. Standard
library only. If any of that is not true on your machine, tell me — the whole
point of the scripted backend is that it works everywhere.

**If you change `PROBLEM` and nothing happens**, Python is reusing stale bytecode —
`"B"` → `"A"` is the same file size, so its cache check can miss the edit. The scaffold
detects this and prints a loud warning; the fix is `rm -rf __pycache__`, or restart the
kernel in a notebook. (This bit us while building the scaffold, which is why there is a
guard for it.)

**It expects `A2_reference_data/` to sit next to this folder.** If yours is
elsewhere: `export A2_DATA=/path/to/A2_reference_data`. It fails with instructions
rather than guessing.

---

## What is here

| File | What it is | Will you change it? |
|---|---|---|
| `config.py` | The vendor-neutral block: `BACKEND`, `MODEL`, `BASE_URL`, guardrail limits, which problem | **Yes** — this is the first file to open |
| `tools.py` | The tool layer over the reference data, with six-field descriptors | **Yes, heavily** — this is D2 |
| `backends.py` | The scripted backend and the live one. One function knows a vendor exists | **Yes** — you add a script per case |
| `agent.py` | The ReAct loop, instrumented | Some — but read every line first |
| `guardrails.py` | Step cap · budget ceiling · de-duplication · autonomy gate | Some — the limits are yours to set |
| `harness.py` | Load, run, code check, judgement queue, report | Some |
| `prompt.py` | Assembles the descriptors + routing rules into the text the model is sent | **Yes** — this is D2(b) |
| `run_eval.py` | Entry point. **This is what a marker runs** | Rarely |
| `demo_loop_failure.py` | D7 failure 1: action de-duplication ablation plus whole-set turn distribution | Yes — keep the evidence |
| `demo_tool_failure.py` | D7 failure 2: pre-authorisation date-contract ablation | Yes — keep the evidence |
| `d7_results.json` | Reproducible before/minus-X/restored evidence written by the two D7 scripts | Generated — commit it |
| `A2_Scaffold_Tour_ProblemA.ipynb` | Guided walk-through of one claim, `CLM-8842` | Read once |
| `A2_Scaffold_Tour_ProblemB.ipynb` | Guided walk-through of one referral, `REF-5602` | Read once |

---

## The two notebooks — start here

**Open the one for the problem you chose. You do not need the other.**

| | Case | What it walks through |
|---|---|---|
| `A2_Scaffold_Tour_ProblemA.ipynb` | `CLM-8842` — the partly-payable claim from Appendix A | three lines, one excluded, one needing a pre-authorisation |
| `A2_Scaffold_Tour_ProblemB.ipynb` | `REF-5602` — the booking from Appendix A | four gates, an urgency window, a slot search |

### What they are for

**To show you the whole machine working on one case before you change any of it.** Eleven
short steps, in the order the machine runs: what the agent is handed → what it has to
fetch → the run, turn by turn → the decision record → the code check → the judgement
check → a failure that raises no exception.

Every value printed is real. Wherever a cell hard-codes something — `'OPH'`, `'M-2214'`,
`'POL-3310'` — the markdown says which earlier cell it came from, so nothing appears by
magic.

**The model is simulated; the data is not.** The backend replays a fixed sequence of moves
from `backends.py`, so the run is deterministic and free. The tools underneath do genuine
lookups against the shipped JSON. Only the model's decisions are scripted.

**Each notebook has a "trap" cell** — the mistake that costs teams the case, made visible:

- **Problem B, cell 4** lists every OPH slot and marks three that are inside the window
  and free but in the **wrong band**. Filter by date alone and you book one of them.
- **Problem A, cell 5** runs four duplicate-matching strategies and shows that every
  shortcut wrongly escalates a perfectly good claim — including this one.

### What they are not

**They contain no logic of their own.** Every cell imports from the `.py` files. That is
deliberate, and it is the habit to copy:

> **Notebooks explore. Modules ship.**

Six people can edit six modules at once. Six people editing one notebook produces merge
conflicts and an unreadable diff — and section 8 of the brief leans on your commit history
to corroborate `CONTRIBUTIONS.md`.

**They are not what you submit.** D5(a) says a marker clones your repository and reproduces
your numbers. `python3 run_eval.py` is that; a notebook is not. Read the tour once, then
work in the modules.

### Running them in Colab

Upload `A2_scaffold/` and `A2_reference_data/` to the same folder in your Drive, then edit
the two paths in the setup cell. Locally, run the cells in order — no setup needed.

---

## The five ideas it exists to show

**1 · The agent never sees the data.** It asks a tool a question and gets one fact
back. An agent handed all the data in its first prompt is making a single call, not
running a loop — and D0(a) asks which rung of the Class 4 ladder you are actually
on.

**2 · `BACKEND = "scripted"` is the default, and must stay that way in what you
submit.** A marker clones your repository and runs `python3 run_eval.py`. If your
numbers do not come back, D5(a) has failed and Technical Execution is capped. Only
D5(b) — the live model battery — costs money. D3(b), D5(a) and D7 all run scripted.

**3 · Turns are decided by the data, not by you.** `requires_preauth` decides
whether Problem A makes another call. A red flag ends a Problem B run before a slot
is ever queried. You did not write those branches; the record did.

**4 · Only independent calls fold into one turn.** `REF-5602` is 6 calls in 4
turns. `CLM-8842` is 9 calls in 4 turns after the required duplicate check was
added. A dependency chain cannot be shortened by running things at once, which is
why Problem B saves 36% and Problem A saves 54%.

**5 · Instrumentation is not optional.** Every run records turns, tokens, cost,
every tool call and every guardrail event. D6's cost model and D7's loop failure
both need numbers captured *while the run happened*. Add instrumentation afterwards
and you re-run the whole battery.

---

## Your first hour

1. **Open the tour notebook for your problem** and run it top to bottom. Fifteen minutes,
   and you will have seen the whole machine on one case.
2. **Open `config.py`** and set `PROBLEM` to the one you chose.
3. **`python3 run_eval.py`** — the same case, graded, from the command line. This is what
   a marker runs.
4. **`python3 run_eval.py --prompt`** — read the exact text the model is sent, and
   its token cost. It is assembled from the descriptors in `tools.py`, so editing one
   changes what the agent sees. Write deliberately worse ones — that is your D2(b)
   **v1**, and the measured comparison is the deliverable.
5. **Open `backends.py`** and script a second case yourself. If you cannot write the
   steps down, you do not yet understand the case. Better to find that out now.

---

## What it deliberately does not do

Left undone on purpose. Doing them is the assignment.

- **Only two cases are scripted.** Your set needs 30–50. See
  `PE6201_A2_Adding_Extra_Cases.pdf`.
- **The judgement check is a queue, not a verdict.** `must_record` items are written
  in English; a substring match would be theatre. A person — or a second model —
  rules on each. If you automate it with a model, say so: a model grading a model is
  a claim that needs defending.
- **The live backend counts no tokens.** It returns zeros, on purpose. Wire in the
  usage numbers the API gives you. Estimating and calling it measured is what D6
  punishes.
- **The tool set is minimal and the names are ours.** Rename, merge, split, add. The
  routing rule and the gated action are the only fixed things.
- **The guardrail checklist is not written.** D3(b) wants ten cases, at least three
  of them hostile free text. The layer they test is in `guardrails.py`.
- **The prompt is a starting point, not a good one.** `prompt.py` assembles the
  descriptors and routing rules into what the model is sent — run `--prompt` to read
  it. Rewriting it, and measuring v1 against v2 on a fixed model, is D2(b). Note that
  comparison needs LIVE runs: the scripted backend never consults a model, so it never
  reads the prompt.

---

## Before you submit

### Reproduce D7 without an API key

Both D7 experiments force the scripted backend internally, even if `config.py`
is temporarily set to `live`. They make no network calls and do not overwrite
`results.json` or any `results_live_*.json` file.

```bash
cd A2_scaffold
python3 demo_loop_failure.py
python3 demo_tool_failure.py
```

Run both commands in that order. Each command updates its own section of
`d7_results.json`, so the final file contains both controlled ablations:

- **Loop control:** normal run, repeated action caught by the guard, the same
  repeated action with de-duplication deleted, restoration, whole-set turn
  distribution, and cap-8 versus cap-30 evidence.
- **Tool interface:** `CLM-8894` with the required service-date constraint,
  the same run with that constraint deleted, restoration, and the whole-set
  pass-rate effect.

The scripted backend's token counts and costs in this file are deterministic
estimates used for the D7 before/after comparison; actual API cost is zero.
Use the measured token usage in `results_live_*.json` for D5/D6 cost claims.

- `python3 run_eval.py` works **in a fresh clone**, on a machine with no key. Test
  it that way — "works on my laptop" has caught out every cohort.
- `BACKEND = "scripted"` is the committed default.
- `results.json` is committed, and your report's numbers come from it.
- Your extended `expected_outcomes_*.json` is committed. **A pass rate submitted
  without the key it was measured against is not a measurement.**
- Every pass rate in the report carries its trial count.
