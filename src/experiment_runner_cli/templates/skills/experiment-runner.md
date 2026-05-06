# Skill: experiment-runner

Top-level orchestration playbook for running one experiment.

## Phases (do in order)

1. **Plan parsing** — read `inputs/plan.md`. Extract:
   - dataset name + size
   - model architecture
   - hyperparameters
   - metrics to measure
   - baselines / comparison conditions
2. **Scope decision** (see §scope below). If the plan is too ambitious
   for available time/compute, document the descope in `work/scope_notes.md`
   and proceed with a tractable subset.
3. **Code skeleton** — write `work/run.py` with three sections:
   `setup() → train() → eval()`. Each section gets its own try/except;
   failures append a structured error to `execution.log` and set
   the corresponding field in `results.json` to `null` + `_status:"failed"`.
4. **Pre-flight** — validate that the dataset is downloadable, the model
   loads, and a 1-step training runs without crashing. **Don't proceed
   to the real run until pre-flight succeeds.**
5. **Real run** — execute. Pipe ALL stdout/stderr to `work/execution.log`
   AND echo to terminal so opencode sees progress.
6. **Result write** — populate `work/results.json` per
   `skills/results-format.md`. Do this **incrementally** — write after
   each metric is computed, don't wait for the whole pipeline.

## §scope — when to descope

The plan may ask for things that don't fit the budget. Descope when:

| Plan asks for | Descope to | Reason |
|---|---|---|
| 100 epochs on full ImageNet | 5 epochs on 10% subset | training-time budget |
| 5 random seeds | 2 random seeds | wall-clock budget |
| 4 model sizes | 2 model sizes (smallest + largest) | compute cost |
| K-fold cross-validation | single train/val/test split | runtime |
| Production-quality preprocessing | dataloader's defaults | dev velocity |

Always document the descope in `work/scope_notes.md` — the verifier reads
this to judge whether the result is still meaningful.

## Hard "don't"s

- Don't run on the GPU if `inputs/resource_constraint.txt` says CPU
- Don't call `time.sleep` in a tight loop to "look busy"
- Don't mock or fake data unless the plan explicitly says so
- Don't suppress exceptions silently — every caught error must be
  appended to `execution.log` with traceback
- Don't write results.json until at least one real metric exists; an
  empty `{}` is worse than a `{"_status": "failed", "error": "..."}`

## Self-check before stopping

```bash
# results.json exists and parses
python3 -c "import json; json.load(open('work/results.json'))" && echo OK

# execution.log non-empty
[ -s work/execution.log ] && echo OK

# at least one real metric or explicit "failed" status
python3 -c "
import json
r = json.load(open('work/results.json'))
status = r.get('_status', 'pass')
metrics = r.get('metrics', {})
assert status in ('pass', 'partial', 'failed'), f'bad status: {status}'
if status == 'pass':
    assert metrics, 'pass status but no metrics'
print(f'OK status={status} metrics_count={len(metrics)}')
"
```

If any check fails, fix it before exiting.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `ImportError: torch` | torch not in env | `pip install --user torch torchvision` |
| `CUDA out of memory` | model too big | reduce batch_size; or `device='cpu'` and document in scope_notes |
| `dataset.zip` 404 | wrong url / mirror down | try alt source; failing that, descope to a built-in dataset (CIFAR, MNIST) |
| Training loss = NaN | bad lr / init / numerical | clip gradients, lower lr, check for log(0) |
| Process killed (OOM) | dataloader too eager | `num_workers=0`, smaller batch |
| Run takes 10x predicted | bad estimate | descope; document in scope_notes |
