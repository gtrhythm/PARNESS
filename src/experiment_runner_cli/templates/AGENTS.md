# AGENTS.md — opencode session for experiment execution

You are an opencode agent tasked with **implementing and running one
experiment** end-to-end, given a plan in `inputs/plan.md`. This workspace
is **strongly isolated** — only read/write files inside this directory.
The main repo is not visible.

## Inputs (read first)

- `inputs/plan.md` — required. The experiment plan: what to do, what
  metrics to measure, what to report.
- `inputs/idea.md` — optional. Context about the underlying research idea.
- `inputs/resource_constraint.txt` — optional. e.g. "single V100 32GB".

If `inputs/plan.md` is missing, **stop and report**.

## Output you must produce

- `work/results.json` — structured experimental results. **Follow the
  schema in `skills/results-format.md` exactly** — pipeline downstream
  depends on it.
- `work/execution.log` — full log of what you ran (stdout + stderr +
  any errors caught). Append-only, plain text.

If a third party (the verifier) cannot reproduce the experiment from
your code + plan, you have failed — write what's missing.

## Workflow

1. Read `inputs/plan.md` and (if present) `inputs/idea.md`. Understand:
   what is being measured, what dataset/model, what comparison.
2. Decide a tractable scope (see `skills/experiment-runner.md` §scope).
3. Write code to `work/<name>.py` files.
4. Run code (`skills/python-sandbox.md`). **Capture every stdout/stderr
   line into `work/execution.log` as you go**. Don't lose output.
5. As soon as you have one valid metric, **append to results.json**
   incrementally — don't wait for the whole experiment to finish.
6. When the plan's deliverables are met (or you run out of time/budget),
   finalize `work/results.json` against the schema in
   `skills/results-format.md`.

## Hard rules

- ❌ Do **not** fabricate numbers. If something failed, write the
  failure to `execution.log` and set the relevant field in
  `results.json` to `null` with `_status: "failed"`.
- ❌ Do **not** modify files outside this workspace.
- ❌ Do **not** install packages globally — use `pip install --user`
  or a virtualenv inside `work/.venv/`.
- ❌ Do **not** delete `work/execution.log` even on partial failure —
  it is the verifier's primary evidence.
- ✅ Do prefer **small, fast, deterministic** experiments over
  ambitious-but-flaky ones. A clean 1k-sample run beats a botched
  100k-sample run.
- ✅ Do persist intermediate state to `work/checkpoint_<step>.json`
  if the experiment has multiple stages.

## Stopping

End the session when `work/results.json` exists, conforms to the
schema, AND `work/execution.log` is non-empty.

If you've spent >80% of your token budget without complete results,
stop, finalize whatever partial results you have (with `_status:
"partial"`), and exit. **Don't run away.**
