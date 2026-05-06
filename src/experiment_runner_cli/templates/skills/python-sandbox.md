# Skill: python-sandbox

How to run experiment code, capture logs reliably, and recover from
common subprocess failures inside this workspace.

## The cardinal rule

**Every byte of stdout/stderr from your runs MUST end up in
`work/execution.log`.** Lost output = unverifiable experiment = retry
or fail at the verifier.

## Bash idiom: tee while running

```bash
cd work
# write to file AND show in terminal — opencode sees progress, file gets full log
python3 run.py 2>&1 | tee -a execution.log
```

`tee -a` appends; use it always. Never overwrite execution.log mid-run.

## Multi-step runs

```bash
cd work
{
  echo "=== $(date -u +%FT%TZ) train start ==="
  python3 run.py --phase train 2>&1
  echo "=== $(date -u +%FT%TZ) train end ==="
  echo "=== $(date -u +%FT%TZ) eval start ==="
  python3 run.py --phase eval 2>&1
  echo "=== $(date -u +%FT%TZ) eval end ==="
} | tee -a execution.log
```

The timestamped section markers are gold for the verifier.

## Virtualenv inside work/

Don't pollute the system Python. If you need packages:

```bash
cd work
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet -r requirements.txt 2>&1 | tee -a execution.log
```

Or one-shot per-package: `pip install --user <pkg>` (faster, no venv,
acceptable for ad-hoc).

## Capture a Python crash with full traceback

```python
# inside run.py
import sys, traceback, json, datetime
try:
    main()
except Exception as e:
    err = {
        "_status": "failed",
        "error": str(e),
        "traceback": traceback.format_exc(),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    with open("results.json", "w") as f:
        json.dump(err, f, indent=2, ensure_ascii=False)
    print(traceback.format_exc(), file=sys.stderr)
    sys.exit(1)
```

This guarantees `results.json` exists even on hard failure — verifier
needs it.

## Long-running jobs

For training that takes >5 minutes, **stream metrics to results.json as
you go**. Don't wait until the end.

```python
results = {"metrics": {}, "_status": "running"}
for epoch in range(num_epochs):
    train_one_epoch()
    val_acc = evaluate()
    results["metrics"][f"val_acc_epoch_{epoch}"] = val_acc
    json.dump(results, open("results.json", "w"), indent=2)
    print(f"epoch {epoch} val_acc={val_acc:.4f}")
results["_status"] = "pass"
json.dump(results, open("results.json", "w"), indent=2)
```

If the process gets killed (timeout, OOM), the verifier still has the
last good checkpoint.

## Subprocess timeouts

If you call subprocesses from Python (e.g. for benchmarks), always pass
a timeout:

```python
import subprocess
r = subprocess.run(
    ["python3", "subscript.py"],
    capture_output=True, text=True, timeout=600,
)
```

Without a timeout, a hung subprocess will eat your whole opencode
budget.

## "Permission denied" / file-system surprises

The workspace is the only writable area. If your code wants to write
to `/tmp/...` or `~/.cache/...`, it might succeed (paper_cli's strong
isolation only applies to the launching process, not subprocesses) —
but **don't rely on that surviving** between runs. Always write
artifacts you care about into `work/`.

## GPU / CPU detection

```python
import torch
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"device: {device}", flush=True)
```

If `inputs/resource_constraint.txt` says CPU, force `device="cpu"` even
if CUDA is available — the constraint is binding.
