# Skill: experiments-from-results

How to write the Experiments section so that **every number traces back
to `inputs/results.json`**. This is the most-violated rule in past runs:
LLMs see a table-shaped placeholder and confidently invent numbers.

## The single rule

> Every decimal number, percentage, "X% improvement", row of a results
> table, or numerical claim in §Experiments **MUST** be a value present
> in `inputs/results.json` — either in `metrics` (preferred) or in
> `config` (for hyperparameter values).

If you can't find a number in `results.json`, **rephrase qualitatively**
("improves over the baseline", "consistently lower than", "comparable to")
rather than fabricate.

## Workflow before writing §Experiments

1. **Read results.json end-to-end.** Don't sample — read every metric.

   ```bash
   python3 -c "
   import json
   r = json.load(open('inputs/results.json'))
   print(f'_status: {r.get(\"_status\")}')
   print(f'config keys: {list(r.get(\"config\", {}).keys())}')
   print(f'metric count: {len(r.get(\"metrics\", {}))}')
   print('metric names:')
   for k in r.get('metrics', {}).keys():
       print(f'  {k}')
   "
   ```

2. **Build a number bank** — every value you might cite, written down
   in a comment block at the top of the Experiments section:

   ```latex
   % --- number bank from inputs/results.json (do not invent any other) ---
   % cora_test_acc=0.807  cora_fgsm_eps0.01=0.787  cora_pgd_eps0.05=0.287
   % citeseer_test_acc=0.679  citeseer_fgsm_eps0.05=0.391  ...
   % training_time=3.52s  num_params=92231
   % --- end number bank ---
   ```

   This is your contract — every \%-figure or table cell must be in this
   list.

3. **Match plan.md → metrics.** If the plan asked for "FGSM @ ε=0.05
   accuracy on Cora", look for `cora_fgsm_eps0.05_accuracy` (or close
   variant). If absent, **don't write that row**.

4. **Status awareness:**
   - `_status: pass` → all metrics are real, use them confidently
   - `_status: partial` → some metrics missing, document gaps in
     §Experiments prose
   - `_status: failed` → say so honestly: "We attempted X but
     execution failed (see appendix); this paper presents the
     methodology only." Don't write made-up numbers

## Tables: build cell-by-cell from the dict

Bad (fabrication-prone):

```latex
\begin{tabular}{lcc}
  Method & Acc & Robust Acc \\
  Baseline & 0.812 & 0.643 \\   % invented
  Ours & 0.847 & 0.731 \\        % invented
\end{tabular}
```

Good (each cell sourced from results.json):

```latex
% Method=GCN-baseline:    metrics.cora_gcn_test_accuracy=0.807, metrics.cora_gcn_fgsm_eps0.05_accuracy=0.289
% Method=HCRAP (ours):    metrics.cora_hcrap_test_accuracy=0.805, metrics.cora_hcrap_fgsm_eps0.05_accuracy=0.291
\begin{tabular}{lcc}
  Method & Test Acc & FGSM @ ε=0.05 \\
  GCN baseline & 0.807 & 0.289 \\
  HCRAP (ours) & 0.805 & 0.291 \\
\end{tabular}
```

## Plot data: matplotlib reads from results.json

```bash
python3 - <<'PY'
import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
r = json.load(open("inputs/results.json"))
m = r["metrics"]
# Build the curve from real keys; raise if missing
epsilons = [0.01, 0.05, 0.1]
ours_pgd = [m[f"cora_hcrap_pgd_eps{e}_accuracy"] for e in epsilons]
base_pgd = [m[f"cora_gcn_pgd_eps{e}_accuracy"] for e in epsilons]
plt.plot(epsilons, ours_pgd, marker="o", label="HCRAP (ours)")
plt.plot(epsilons, base_pgd, marker="s", label="GCN baseline")
plt.xlabel("PGD perturbation budget ε"); plt.ylabel("Robust accuracy")
plt.legend(); plt.tight_layout(); plt.savefig("paper/figs/robust_curve.pdf")
PY
```

If a key isn't in `m`, the script raises `KeyError` immediately — better
than silently faking numbers in TeX.

## Self-check at the end

```bash
python3 - <<'PY'
import json, re
r = json.load(open("inputs/results.json"))
# every numeric value in metrics + config (with various decimal precisions)
allowed = set()
for v in list(r.get("metrics", {}).values()) + list(r.get("config", {}).values()):
    if isinstance(v, (int, float)):
        for p in (2, 3, 4):
            allowed.add(f"{v:.{p}f}".rstrip("0").rstrip("."))

tex = open("paper/main.tex").read()
m = re.search(r"\\section\{[^}]*Experiment", tex)
end = re.search(r"\\section\{|\\begin\{thebibliography\}", tex[m.end():])
body = tex[m.start():m.start() + (end.start() + (m.end() - m.start()) if end else 6000)]

paper_nums = set(re.findall(r"\d+\.\d{2,4}", body))
suspicious = paper_nums - allowed
print(f"Experiments section: {len(paper_nums)} unique numbers")
print(f"  in results.json: {len(paper_nums & allowed)}")
print(f"  NOT in results.json (likely fabricated): {len(suspicious)}")
if suspicious:
    print(f"  examples: {sorted(suspicious)[:8]}")
    print("FIX: replace these with qualitative phrasing or remove them.")
else:
    print("OK — all numbers traceable to results.json")
PY
```

If suspicious > 5, **go back and fix** before declaring done. Run this
check every time you change the Experiments section.

## What if results.json says `_status: failed`?

Then there is no real data. The paper should **document this honestly**:

```latex
\section{Experiments}

We implemented the proposed approach and attempted to evaluate it on
\dataset{}. The experiment runner reported a \texttt{failed} status
during \emph{<phase from results.json.error>}, so this paper presents
the methodology and design rationale; quantitative results will appear
in a follow-up version once the execution environment is resolved.
```

Don't pretend.
