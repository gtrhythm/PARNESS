# Skill: verdict-emitter

The schema your `verdict.json` MUST follow. Pipeline downstream depends
on it.

## Top-level schema

```json
{
  "verdict": "pass" | "retry" | "fail",
  "score": 0.0,
  "reasoning": "...",
  "evidence": ["...", "..."],
  "improvement_suggestions": ["...", "..."],
  "results_status_observed": "pass" | "partial" | "failed" | "missing" | "malformed",
  "_metadata": {
    "verifier_version": "0.1",
    "issued_at": "2026-05-05T14:00:00Z"
  }
}
```

### `verdict` (required)

- `"pass"` — accept the result; pipeline proceeds to paper-writing
- `"retry"` — the experiment is fixable; pipeline goes back to runner
  with `improvement_suggestions` as guidance
- `"fail"` — give up on this experiment; pipeline either skips Phase 3
  outputs or reroutes the idea

The pipeline gate consumes this: `pass` and `fail` are terminal,
`retry` decrements the retry counter and goes back.

### `score` (required, 0.0–1.0)

Confidence in the verdict, intended for upstream ranking when multiple
candidate experiments compete. Calibration:

- **0.85–1.00**: clean pass, all checks green
- **0.65–0.85**: pass with minor descope or one yellow flag
- **0.30–0.55**: retry — fixable issues identified
- **0.00–0.20**: fail — fundamentally broken or fabricated

### `reasoning` (required)

A 2–4 sentence prose explanation of the verdict. **Must reference
specific evidence** from execution.log or results.json. Bad reasoning:
"the experiment looks fine". Good reasoning: "Training loss decreased
2.31 → 0.92 over 5 epochs (log lines 42–145), final test_accuracy=0.823
within plan target band [0.75, 0.95], no OOM/crash."

### `evidence` (required, list)

Bullet-point evidence items, ≤ 5 entries. Each is a string referencing
a specific artifact:

```json
"evidence": [
  "results.json _status=pass with 7 metrics",
  "execution.log lines 42-145 show monotonic loss decrease",
  "config.dataset='CIFAR-10' matches plan.md",
  "no NaN/Inf in any metric",
  "_runtime_seconds=89.3 ≈ wall-clock from log timestamps (87s)"
]
```

### `improvement_suggestions` (required if verdict=retry; optional otherwise)

Concrete actionable suggestions. Each item is a directive the runner
can act on:

```json
"improvement_suggestions": [
  "lower learning rate from 0.01 to 0.001 — current setting caused NaN at epoch 3",
  "reduce batch_size from 256 to 128 — current setting caused OOM",
  "add gradient clipping (clip_grad_norm_=1.0) to prevent loss explosion"
]
```

For verdict=fail, populate this with what would need to be true for a
re-run to succeed (e.g., "dataset must be available locally before retry").

### `results_status_observed` (required)

What you found in `inputs/runner_workspace/work/results.json`:

- `"pass"`, `"partial"`, `"failed"` — the literal `_status` you read
- `"missing"` — file didn't exist
- `"malformed"` — file existed but didn't parse / didn't have `_status`

This is independent of your `verdict` — you can verdict=fail with
`results_status_observed=pass` (e.g., the runner claimed pass but
fabricated, you caught it).

## Emit example: clean pass

```json
{
  "verdict": "pass",
  "score": 0.92,
  "reasoning": "Real training run: loss decreased 2.31→0.92 over 5 epochs (execution.log lines 42-145). Final test_accuracy=0.823, plausible for ResNet-18/CIFAR-10/5-epoch budget. config.dataset matches plan.md. No NaN/Inf. _runtime_seconds=89.3 ≈ 87s wall-clock from timestamps.",
  "evidence": [
    "results.json _status=pass with 7 metrics",
    "execution.log shows monotonic loss decrease across 5 epochs",
    "config.dataset='CIFAR-10' matches plan.md",
    "no NaN/Inf in any metric",
    "runtime self-consistent (89.3s ≈ 87s log span)"
  ],
  "improvement_suggestions": [],
  "results_status_observed": "pass",
  "_metadata": {"verifier_version": "0.1", "issued_at": "2026-05-05T15:00:00Z"}
}
```

## Emit example: retry

```json
{
  "verdict": "retry",
  "score": 0.42,
  "reasoning": "Training collapsed: loss became NaN at epoch 3 (execution.log line 87). results.json _status=partial with only 2 of 5 planned metrics. Likely cause: lr=0.01 too high for the lite ResNet variant.",
  "evidence": [
    "execution.log line 87: 'Loss: nan'",
    "results.json _status=partial",
    "only 2 of 5 plan-required metrics present",
    "config.lr=0.01"
  ],
  "improvement_suggestions": [
    "lower lr from 0.01 to 0.001",
    "add gradient clipping clip_grad_norm_=1.0",
    "verify pre-flight 1-step check passes before full training"
  ],
  "results_status_observed": "partial",
  "_metadata": {"verifier_version": "0.1", "issued_at": "2026-05-05T15:00:00Z"}
}
```

## Emit example: fail (fabrication caught)

```json
{
  "verdict": "fail",
  "score": 0.05,
  "reasoning": "Suspected fabrication. results.json _status=pass with 7 metrics including test_accuracy=0.834, but execution.log is only 12 lines containing import statements and one 'training complete' string — no epoch/step markers, no loss values, no timing. Runner did not actually train.",
  "evidence": [
    "execution.log = 12 lines, no training markers",
    "results.json claims _runtime_seconds=89.3 but log spans <1s by timestamps",
    "no 'epoch' / 'step' / 'iter' substring anywhere in log",
    "metrics present but training never observed"
  ],
  "improvement_suggestions": [
    "runner must actually execute training code; do not write results.json without preceding epoch/step output",
    "add the §self-check from skills/results-format.md as a pre-stop assertion"
  ],
  "results_status_observed": "pass",
  "_metadata": {"verifier_version": "0.1", "issued_at": "2026-05-05T15:00:00Z"}
}
```

## Validation snippet

Before declaring done:

```bash
python3 - <<'PY'
import json
v = json.load(open("verdict.json"))
assert v["verdict"] in ("pass", "retry", "fail"), v["verdict"]
assert 0.0 <= v["score"] <= 1.0, v["score"]
assert v["reasoning"], "empty reasoning"
assert isinstance(v["evidence"], list) and v["evidence"], "empty evidence"
if v["verdict"] == "retry":
    assert v["improvement_suggestions"], "retry verdict needs improvement_suggestions"
print(f"OK verdict={v['verdict']} score={v['score']}")
PY
```
