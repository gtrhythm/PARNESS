# Skill: results-format

The schema your `work/results.json` MUST follow. The verifier and the
downstream paper-writing pipeline both consume this — drift = silent
breakage.

## Top-level schema

```json
{
  "_status": "pass" | "partial" | "failed",
  "metrics": { ... },
  "config": { ... },
  "scope_notes": "...",
  "_runtime_seconds": 123.45,
  "_started_at": "2026-05-05T14:00:00Z",
  "_finished_at": "2026-05-05T14:02:03Z"
}
```

### `_status` (required)

- `"pass"` — experiment completed, all planned metrics present
- `"partial"` — some metrics computed, some failed/skipped (must
  include `_status` reasoning in `scope_notes`)
- `"failed"` — experiment did not produce any usable metric

### `metrics` (required for pass / partial)

Keys are metric names (snake_case). Values are floats or small
JSON-serializable structures. Examples:

```json
{
  "metrics": {
    "test_accuracy": 0.8234,
    "test_loss": 0.412,
    "f1_macro": 0.7891,
    "psnr_db": 24.7,
    "training_time_seconds": 89.3,
    "per_class_accuracy": {
      "cat": 0.91, "dog": 0.86, "bird": 0.78
    },
    "loss_curve": [2.31, 1.84, 1.42, 1.10, 0.92]
  }
}
```

Rules:
- Use SI units; explicit suffix in the key (`_seconds`, `_db`, `_pct`,
  `_mb`)
- Don't put per-iteration logs here; they belong in execution.log
- A list inside metrics should have ≤100 entries (downsample if longer)

### `config` (required for pass / partial)

The exact configuration that produced the metrics. Required fields:

```json
{
  "config": {
    "dataset": "CIFAR-10",
    "dataset_size": 50000,
    "model": "ResNet-18",
    "model_params": 11_173_962,
    "epochs": 5,
    "batch_size": 128,
    "lr": 0.001,
    "optimizer": "Adam",
    "device": "cuda",
    "seed": 42,
    "framework": "pytorch 2.1.0"
  }
}
```

Anything that, if changed, would change the result. Reproducibility lives
here.

### `scope_notes` (required for partial; recommended otherwise)

Free-text note describing any descope, deviation from the original plan,
or known caveats. The verifier reads this verbatim.

```json
{
  "scope_notes": "Descoped from full ImageNet (1.28M images) to 10% subset due to disk space; trained 5 epochs instead of 100 due to time budget; two random seeds instead of five."
}
```

### Failure shape

If `_status: "failed"`:

```json
{
  "_status": "failed",
  "error": "CUDA out of memory at batch 23",
  "traceback": "Traceback (most recent call last):\n  ...",
  "config": { "dataset": "...", "model": "...", "batch_size": 128 },
  "_runtime_seconds": 45.2,
  "_started_at": "2026-05-05T14:00:00Z",
  "_finished_at": "2026-05-05T14:00:45Z"
}
```

Do NOT silently emit empty `metrics: {}` on failure — explicitly set
`_status: "failed"` and include `error` + `traceback`.

## Validation snippet

Run this before declaring done:

```bash
python3 - <<'PY'
import json, sys
r = json.load(open("work/results.json"))
assert "_status" in r, "missing _status"
assert r["_status"] in ("pass", "partial", "failed"), f"bad status: {r['_status']}"
if r["_status"] in ("pass", "partial"):
    assert r.get("metrics"), "no metrics for non-failed status"
    assert r.get("config"), "no config for non-failed status"
if r["_status"] == "failed":
    assert r.get("error"), "failed status requires error field"
print(f"OK schema, status={r['_status']}, metrics={len(r.get('metrics', {}))}")
PY
```

## What downstream consumers do

- The **verifier** checks: schema conformance, sanity of numbers
  (no NaN, no obviously-impossible accuracy), consistency between
  `config` and what was actually claimed in plan.md.
- The **paper writer** (paper_cli_runner) reads `metrics` and `config`
  to write the experiments section. **Numbers in the paper come from
  here verbatim** — so if you fabricate, the paper fabricates.
