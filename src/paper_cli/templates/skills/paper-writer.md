# Skill: paper-writer

Top-level orchestration playbook. The high-level workflow is in `AGENTS.md`;
this file gives section-length targets and ordering rules.

## Section length targets (4--8 page short paper)

| Section | Target words | Notes |
|---|---|---|
| Abstract | 150--250 | Single paragraph. **No \cite.** State problem + contribution + headline result. |
| Introduction | 600--900 | 2--3 paragraphs + optional contributions list (`enumerate`). |
| Related Work | 300--500 | Cluster prior work into 2--3 themes; one paragraph per theme. |
| Method / System | 1000--1800 | The bulk. 2--3 subsections + 1--2 figures (TikZ for technical figures). |
| Experiments | 600--1000 | Setup paragraph + results paragraph + 1 table + (optional) 1 plot. |
| Conclusion | 100--200 | Short. Takeaway + one-sentence future work. |

If experiment results are sparse (3--5 numbers), keep Experiments to 2 paragraphs.
**Don't pad.** Better a tight 6-page paper than a flabby 10-page one.

## Section ordering rule

Draft in this order. Don't write Method before Intro — abstractions you
introduce in Method should be set up by Intro.

1. Abstract — write a stub (1 sentence per future section), refine at the end.
2. Introduction — establishes problem, motivation, contributions.
3. Related Work — positions against prior systems.
4. Method — the technical content.
5. Experiments — validates Method.
6. Conclusion.
7. Re-write Abstract last, now that you know what the paper actually says.

## Marker conventions

While drafting prose, drop these markers — they are resolved by the figure
pass and citation pass respectively:

- `[CITE: <topic phrase>]` — wherever a citation belongs. Example:
  `Recent autonomous research systems [CITE: AI-Scientist Sakana 2024]`.
- `[FIGURE: <description>]` — wherever a figure belongs. Example:
  `[FIGURE: 4-layer system diagram, top-down, with infra/agents/runtime/pipeline bands]`.

`grep -n '\[CITE:' main.tex` and `grep -n '\[FIGURE:' main.tex` enumerate them.

## Don't

- Don't `\maketitle` twice.
- Don't put `\bibliography{}` inside `thebibliography` environment (see `latex-compile-fix.md` §bbl).
- Don't fabricate citations or invent paper titles. If S2 returns nothing,
  rephrase to remove the citation need.
- Don't use `\textbf{}` for emphasis; use `\emph{}`.
- Don't paste raw URLs — wrap in `\url{...}` so hyperref can break them.
- Don't write more than 80 chars per line in source — diff-friendliness matters
  if the user takes over.

## Self-check before declaring done

```bash
grep -n '\[CITE:' paper/main.tex   # must be empty
grep -n '\[FIGURE:' paper/main.tex # must be empty
grep -c '\\bibitem' paper/main.tex # must equal cite count
grep -c '\\cite{' paper/main.tex   # must be ≥ \bibitem count's referenced keys
ls -la paper/main.pdf              # must exist, ≥ 50KB
```
