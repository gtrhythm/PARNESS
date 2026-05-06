# Skill: s2-citation

Resolve `[CITE: ...]` markers via Semantic Scholar, emit BibTeX, and insert
`\cite{key}`.

## Auth

Header: `x-api-key: $S2_API_KEY`. The key is in env. **Never hardcode.**
If `$S2_API_KEY` is unset, search will work at a much lower rate (~1 req/sec)
but may also 401. Check with `env | grep S2_API_KEY` first.

## Search

```bash
TOPIC="multi-agent LLM scientific research"
curl -sS -G "https://api.semanticscholar.org/graph/v1/paper/search" \
  --data-urlencode "query=$TOPIC" \
  --data-urlencode "limit=5" \
  --data-urlencode "fields=title,authors,year,venue,externalIds,abstract,paperId" \
  -H "x-api-key: $S2_API_KEY" | python3 -m json.tool | head -100
```

Pick the top result by abstract / title relevance to the surrounding section.

## Cite key convention

`firstauthor_year_word`, all lowercase. Examples:
- `lecun_2015_deep`
- `vaswani_2017_attention`
- `lu_2024_aiscientist`

Construction:
1. **first author last name**: `authors[0].name`, split on space, take last
   token, strip non-alpha (`[a-z]`)
2. **year**: from `year` field
3. **word**: first non-stopword from title (lowercase). Stopwords:
   `the / a / an / on / of / for / with / using / via / towards / and / in / to`

If S2 is missing fields, fall back: missing year → `nd`; missing first author
→ first creator that has a name; missing title → use `paperId[:8]`.

## BibTeX entry templates

### `@article` (journal)

```bibtex
@article{lecun_2015_deep,
  author  = {Yann LeCun and Yoshua Bengio and Geoffrey Hinton},
  title   = {Deep Learning},
  journal = {Nature},
  year    = {2015},
  volume  = {521},
}
```

### `@inproceedings` (conference)

```bibtex
@inproceedings{vaswani_2017_attention,
  author    = {Ashish Vaswani and Noam Shazeer and others},
  title     = {Attention is All You Need},
  booktitle = {Advances in Neural Information Processing Systems},
  year      = {2017},
}
```

### `@misc` / `@techreport` (preprint, tech report, web)

```bibtex
@misc{lu_2024_aiscientist,
  author = {Chris Lu and Cong Lu and Robert Lange and Jakob Foerster and Jeff Clune and David Ha},
  title  = {The {AI} Scientist: Towards Fully Automated Open-Ended Scientific Discovery},
  year   = {2024},
  note   = {arXiv preprint arXiv:2408.06292},
}
```

If `externalIds.DOI` exists, add `doi = {...}`. **Don't add a URL field** — the
arxiv style doesn't render it inline.

## Inline `\bibitem` (must mirror BibTeX entry)

The compiler service does NOT run bibtex. So you also need a matching
`\bibitem` inside the `thebibliography` block at the end of `main.tex`.
Template:

```latex
\bibitem{lecun_2015_deep}
Y. LeCun, Y. Bengio, G. Hinton.
\newblock Deep Learning.
\newblock \emph{Nature}, 521(7553):436--444, 2015.
```

Format rules:
- author names: initial + last (e.g. `Y. LeCun`); join with `, ` then ` and ` for last
- title in plain text (not bold)
- venue in `\emph{...}`
- year at end
- `\newblock` between title and venue (legacy plain-style convention)

## End-to-end procedure

1. List all markers:
   ```bash
   grep -nE '\[CITE: [^\]]+\]' paper/main.tex
   ```
2. For each marker:
   - extract topic phrase
   - query S2 (limit 5)
   - if `data` is non-empty:
     - dedup against already-cited `paperId`s (re-using a citation is fine,
       just don't duplicate the BibTeX entry)
     - construct cite key
     - append BibTeX entry to `paper/refs.bib`
     - append `\bibitem` block inside `thebibliography` in `main.tex`
     - replace the marker with `\cite{key}` (use `Edit` tool, not `sed`)
   - if `data` is empty:
     - try a more general query (drop nouns, broaden)
     - if still empty, **rephrase the surrounding sentence** to remove the
       citation need, OR drop the marker. Never fabricate.
3. Self-check:
   ```bash
   grep -c '\\cite{' paper/main.tex      # cite count
   grep -c '\\bibitem{' paper/main.tex   # bibitem count (≥ unique cite keys)
   grep -E '\[CITE:' paper/main.tex      # must be empty
   ```

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized` | bad / missing `S2_API_KEY` | check `env`; ask user |
| Empty `data` array | query too specific | broaden topic, drop adjectives |
| Same paper picked twice | not deduping | track `paperId` set; reuse cite key |
| Garbled author name (e.g. "Author 1") | S2 metadata holes | look up by `paperId`/`DOI:`/`arXiv:` for cleaner record |
| Year missing | S2 sometimes lacks year for older papers | use `n.d.` and put publication info in `note` |
| 429 rate limit | exceeded ~5 req/sec with key | add `sleep 0.3` between calls |

## Rate limits

- With key: ~5 req/sec sustained.
- Without key: ~1 req/sec.
- Be polite: `sleep 0.3` between calls in batched loops.

## Lookup-by-id (when search misses)

If the paper is well-known but search ranks it poorly, look up directly by ID:

```bash
# by S2 paperId
curl -sS -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/<paperId>?fields=title,authors,year,venue,externalIds"

# by DOI
curl -sS -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1038/nature14539?fields=title,authors,year,venue"

# by arXiv
curl -sS -H "x-api-key: $S2_API_KEY" \
  "https://api.semanticscholar.org/graph/v1/paper/arXiv:2408.06292?fields=title,authors,year,venue"
```
