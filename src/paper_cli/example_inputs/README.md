# Example inputs for paper-cli

This directory shows the expected shape of the `--inputs` argument to
`paper-cli run`. Required files:

| File | Required | Format | Purpose |
|---|---|---|---|
| `idea.md` | yes | markdown | research idea, motivation, hypothesis, contribution sketch |
| `results.json` *or* `results.md` | yes | JSON or markdown | experiment numbers / observations |
| `metadata.yaml` | yes | YAML | title, authors, affiliation, venue, keywords, abstract_seed |
| `references_seed.json` | no | JSON | pre-curated reference candidates (skip → opencode finds via S2) |
| `figs_seed/` | no | dir | figures the user already has, copied verbatim into `paper/figs/` |

The opencode session reads everything in `inputs/` verbatim (no schema
enforcement on the Python side), so additional context files (e.g.
`prior_work_notes.md`) are also welcome — opencode will pick them up
during the planning phase.
