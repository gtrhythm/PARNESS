# Skill: log-analyzer

Extract evidence from `inputs/runner_workspace/work/execution.log` to
classify what really happened during the run.

You have 200k context — read the whole log unless it's > 1MB. For very
long logs, sample: first 5k lines + last 5k lines + any line containing
`error|fail|nan|inf|warning|exception|killed`.

## Failure-mode taxonomy

| Pattern in log | Likely cause | Verdict signal |
|---|---|---|
| log is empty / 0 bytes | runner crashed before any output | **fail** |
| only `Traceback` + exit | hard crash early | **fail** |
| `MemoryError` / `OOM killed` / `Killed` | OOM | retry with smaller batch |
| `CUDA out of memory` | GPU OOM | retry with CPU or smaller batch |
| `nan` / `inf` in loss | numerical instability | retry with lower lr / clip |
| `ConnectionError` / 404 / ssl error | dataset download failed | retry with alt source |
| no `epoch` / `step` / iteration markers, just import + exit | smoke run not real run | retry |
| process killed mid-epoch | timeout / sigterm | partial-pass acceptable if metrics from earlier epochs are present, else retry |
| training loss flat / never decreases | bug in optimizer wiring or lr=0 | retry |
| 100% accuracy on epoch 0 | data leak or trivial task | flag in reasoning, can still pass if scope_notes documents it |
| extensive `mock` / `placeholder` / `TODO` strings | runner punted | retry |

## Useful greps

```bash
# crash signature
grep -nE "Traceback|Exception|Error:" inputs/runner_workspace/work/execution.log | head -20

# any NaN / Inf
grep -nE "nan|inf" inputs/runner_workspace/work/execution.log | head -10

# epoch / step progress (proves training really happened)
grep -cE "epoch [0-9]+|step [0-9]+|iter [0-9]+" inputs/runner_workspace/work/execution.log

# the explicit timestamps from python-sandbox.md
grep -E "^=== .* (start|end) ===" inputs/runner_workspace/work/execution.log

# OOM / kill signals
grep -nE "OOM|out of memory|Killed|SIGKILL|SIGTERM" inputs/runner_workspace/work/execution.log

# whether code was actually run (vs only imported)
grep -cE "device:|cuda|cpu" inputs/runner_workspace/work/execution.log
```

## Detecting "fake" runs

The runner is instructed not to fabricate. You verify:

- **Real training**: presence of decreasing loss across multiple
  epoch/step markers. If loss is monotonic and varied, training is real.
- **Real evaluation**: an `eval` / `test` section that follows `train`,
  with metric values that are plausible.
- **Real timing**: `_finished_at - _started_at` (in seconds) ≈
  `_runtime_seconds` ≈ implied wall-clock from log timestamps.
- **Suspicious**: results.json has 5+ metrics but execution.log < 100
  lines = almost certainly fake. Flag.

## Evidence quoting

In your `verdict.json.reasoning` field, quote SPECIFIC log lines as
evidence. Format:

```
"reasoning": "Training appears genuine: loss decreased from 2.31 to 0.92 over 5 epochs (lines 42, 67, 93, 119, 145 of execution.log). Final test_accuracy=0.823 sanity-checks against the loss trajectory. No OOM/crash signals."
```

Without evidence, the verdict is opinion. With evidence, it's auditable.
