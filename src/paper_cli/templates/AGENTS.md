# AGENTS.md — opencode session for arxiv-style paper writing

You are an opencode agent tasked with writing **one** arxiv-style paper end-to-end
from the materials in `inputs/`. This workspace is **strongly isolated** — only
read/write files inside this directory. The main repo is not visible to you.

## Inputs (read these first)

- `inputs/idea.md` — the research idea / motivation / contribution sketch
- `inputs/results.json` or `inputs/results.md` — **the only authoritative
  source of experiment numbers**. Every metric you cite in the Experiments
  section must come from here.
- `inputs/results_report.md` — markdown summary (may be qualitative);
  use for *narrative*, not for *numbers*.
- `inputs/metadata.yaml` — title, authors, affiliation, target venue, keywords
- `inputs/references_seed.json` (optional) — pre-curated reference candidates
- `inputs/figs_seed/` (optional) — figures the user already has, copy into `paper/figs/`

If a required input is missing, **stop and report what's missing** before writing.

## Output you must produce

- `paper/main.tex` — the paper source (start from `paper/main.tex.skeleton`)
- `paper/refs.bib` — BibTeX entries cited in the paper
- `paper/figs/*.png` or `*.pdf` — all referenced figures
- `paper/main.pdf` — final compiled PDF; must come from a compile with `returncode==0`

## Workflow

1. Read everything under `inputs/`. Outline the section structure as a comment
   block at the top of `main.tex`.
2. Rename `paper/main.tex.skeleton` → `paper/main.tex`. Fill the metadata
   placeholders (title, authors, affiliation, abstract topic).
3. Draft sections sequentially: **abstract → intro → related → method →
   experiments → conclusion**. While drafting, drop two kinds of marker:
   - `[CITE: <topic>]` wherever you want a citation
   - `[FIGURE: <description>]` wherever you want a figure
4. **Figure pass.** For each `[FIGURE: ...]`:
   - Architecture / DAG / flowchart / layered system → **TikZ inline**
     (see `skills/tikz-figure.md`)
   - Data plot (loss / accuracy / bar) → matplotlib via Bash → write to
     `paper/figs/<name>.pdf` → `\includegraphics`
   - Teaser / cover / metaphorical illustration only → gpt-image-2
     (see `skills/figure-image-generative.md`)
5. **Citation pass.** For each `[CITE: ...]`:
   - Query S2 (see `skills/s2-citation.md`)
   - Emit a BibTeX entry to `paper/refs.bib` AND a matching `\bibitem{key}`
     to the `thebibliography` block at the end of `main.tex`
   - Replace `[CITE: ...]` with `\cite{key}`
6. **Compile loop.** See `skills/latex-compile-fix.md`. Iterate until
   `returncode==0` AND `pdf_generated==true`.
7. **Self-check before declaring done:**
   - every `\cite{key}` resolves to a `\bibitem{key}` in `thebibliography`
   - every `\ref{label}` resolves to a `\label{label}`
   - `paper/main.pdf` exists, ≥ 50KB
   - no `[CITE:` or `[FIGURE:` markers left in `main.tex`

## Key services

| Service | URL / call |
|---|---|
| LaTeX compiler | `{{LATEX_SERVICE_URL}}` — `POST /compile` with zip; full protocol in `skills/latex-compile-fix.md` |
| Semantic Scholar | `https://api.semanticscholar.org/graph/v1/paper/search` — header `x-api-key: $S2_API_KEY` |
| gpt-image-2 (teaser only) | `https://grsai.dakka.com.cn/v1/draw/completions` — header `Authorization: Bearer $GRSAI_API_KEY` |

Detailed protocols, examples and pitfalls are in `skills/*.md`. **Read the
relevant skill before each major action** — they encode hard-won gotchas
(e.g., `aspectRatio` not `aspect_ratio`; `returncode==0` not `error_count==0`).

## Hard rules

- ❌ Do **not** use gpt-image-2 for technical figures (architecture / DAG / loss curve).
  Use TikZ or matplotlib instead.
- ❌ Do **not** modify files outside this workspace.
- ❌ Do **not** skip the `returncode==0` check — `X-LaTeX-Error-Count` is unreliable.
- ❌ Do **not** fabricate citations. If S2 returns nothing, drop or rephrase.
- ❌ Do **not** fabricate experiment numbers. Every numerical claim in the
  Experiments section MUST come verbatim from `inputs/results.json`'s
  `metrics` field. If a number is not there, write a qualitative claim
  (e.g. "improves over the baseline" instead of inventing "improves by
  4.2%"). See `skills/experiments-from-results.md`.
- ❌ Do **not** use `\bibliography{refs}` — the compiler service runs only
  `latexmk -xelatex` (no bibtex stage). Inline `\begin{thebibliography}` is
  the only working form.
- ✅ Do verify each generative image is not a 1×1 px placeholder
  (`file figs/teaser.png` should report ≥ 100KB).
- ✅ Do keep `refs.bib` and the inline `thebibliography` in sync (one entry per cite key).

## Stopping

End the session when `paper/main.pdf` is present and the self-check passes.
If you've made >5 compile attempts without progress, write a short
`paper/STATUS.md` summarising what's blocking you and stop — the user will
take over.
