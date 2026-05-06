# Skill: result-validator

Schema-check + sanity-check the runner's `results.json`.

## Step 1: schema check

The runner's results.json must follow this top-level shape (echoed from
the runner's own `results-format.md`):

```json
{
  "_status": "pass" | "partial" | "failed",
  "metrics": { ... },
  "config": { ... },
  "scope_notes": "...",
  "_runtime_seconds": ...,
  "_started_at": "...",
  "_finished_at": "..."
}
```

```bash
python3 - <<'PY'
import json, sys
try:
    r = json.load(open("inputs/runner_workspace/work/results.json"))
except FileNotFoundError:
    print("MISSING_RESULTS"); sys.exit(0)
except json.JSONDecodeError as e:
    print(f"MALFORMED: {e}"); sys.exit(0)

issues = []
if "_status" not in r:
    issues.append("missing _status")
elif r["_status"] not in ("pass", "partial", "failed"):
    issues.append(f"bad _status: {r['_status']}")
if r.get("_status") in ("pass", "partial"):
    if not r.get("metrics"):
        issues.append("non-failed status but empty metrics")
    if not r.get("config"):
        issues.append("non-failed status but empty config")
if r.get("_status") == "failed":
    if not r.get("error"):
        issues.append("failed status missing error field")
print("OK" if not issues else "ISSUES: " + " | ".join(issues))
PY
```

If `MISSING_RESULTS` → verdict=`fail` (runner crashed before writing).
If `MALFORMED` → verdict=`fail` (runner wrote junk).
If `ISSUES: ...` → verdict=`retry` with the list of issues in
improvement_suggestions.

## Step 2: sanity check the metrics

Per-metric heuristics. Failures here = `retry` (runner may have a bug).

| Metric | Sanity range | Red flag |
|---|---|---|
| accuracy / acc / val_acc / test_acc | 0.0–1.0 (or 0–100 if explicit `_pct` suffix) | NaN, > 1.0 with no `_pct` suffix, < 0, exactly 1.0 with no scope_notes |
| loss / *_loss | typically 0–10 for cross-entropy | NaN, < 0, exploding (> 100 unless documented) |
| f1 / precision / recall / auroc | 0.0–1.0 | NaN, > 1.0, < 0 |
| psnr_db | 10–60 typical | NaN, < 0, > 100 |
| ssim | 0.0–1.0 | NaN, > 1.0, < 0 |
| training_time_seconds | should match `_finished_at - _started_at` ± 10% | discrepancy > 50% means the field is fake |
| any score >= 0.95 | suspicious unless plan asked for SOTA | flag for human review |
| any score == 0.0 exactly | likely placeholder | flag |
| any score with > 6 significant digits in a noisy metric | over-precise = suspicious | trim or flag |

## Step 3: cross-check against plan.md

```bash
python3 - <<'PY'
import json, re
r = json.load(open("inputs/runner_workspace/work/results.json"))
cfg = r.get("config", {})
plan = open("inputs/plan.md").read().lower()

# extract dataset / model from plan via simple keyword search
issues = []
declared_dataset = (cfg.get("dataset") or "").lower()
if declared_dataset and declared_dataset not in plan:
    issues.append(f"runner used dataset '{cfg['dataset']}' not mentioned in plan")
declared_model = (cfg.get("model") or "").lower()
if declared_model and declared_model not in plan:
    issues.append(f"runner used model '{cfg['model']}' not mentioned in plan")
print("ALIGN_OK" if not issues else "ALIGN_ISSUES: " + " | ".join(issues))
PY
```

Mismatch + no `scope_notes` justification → verdict=`retry`. With
justification (and the descope is reasonable for the budget) → still
`pass` is allowable, but score lower.

## Combined gate

| Findings | Verdict | Score |
|---|---|---|
| schema OK + sanity OK + plan-aligned + status=pass | **pass** | 0.85–1.0 |
| schema OK + sanity OK + minor descope (documented) | **pass** | 0.65–0.85 |
| schema OK + 1–2 sanity flags | **retry** | 0.30–0.55 |
| any of: missing/malformed results, status=failed, blatant fabrication signal | **fail** | 0.00–0.20 |
| schema OK + status=partial + plan-meaningful subset | **pass** | 0.50–0.70 |

The score is for upstream gating thresholds; verdict is the categorical
decision the pipeline routes on.
