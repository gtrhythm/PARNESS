# Skill: latex-compile-fix

How to compile, read errors, and fix them. The compiler service is the
source of truth — `$LATEX_SERVICE_URL` in env.

## Compile in one shot (with full log)

```bash
cd paper

# zip everything the compiler needs
ZIP=/tmp/paper_$$.zip
rm -f "$ZIP"
zip -q "$ZIP" main.tex arxiv.sty
[ -f refs.bib ] && zip -q "$ZIP" refs.bib
if [ -d figs ] && [ -n "$(ls -A figs 2>/dev/null)" ]; then
  zip -qr "$ZIP" figs
fi

# POST to compiler service
curl -sS -X POST "$LATEX_SERVICE_URL/compile" \
  -F "file=@$ZIP" -F "log=1" \
  -m 320 -o /tmp/result.json

# parse + extract
python3 - <<'PY'
import json, base64, sys, pathlib
d = json.load(open("/tmp/result.json"))
rc = d["returncode"]
print(f"rc={rc}  pdf_generated={d['pdf_generated']}  errors={d['error_count']}  warnings={d['warning_count']}")
if d.get("pdf_generated"):
    pathlib.Path("main.pdf").write_bytes(base64.b64decode(d["pdf_base64"]))
    print(f"wrote main.pdf ({d['pdf_size']} bytes)")
print("--- last 60 log lines ---")
print("\n".join(d["full_log"].splitlines()[-60:]))
PY
```

## Read the result

- **`rc==0` AND `pdf_generated==true`** → success. Stop. **Ignore `error_count`** —
  the compiler counts `error` substring matches in stdout, which includes noise
  like `error summary` and `Running '...'`. The authoritative signal is `rc==0`.
- **`rc!=0`** → look at the **last 60 log lines**, then `errors` array.

## Error → fix table

| Log pattern | Cause | Fix |
|---|---|---|
| `! Undefined control sequence \xxx` | missing `\usepackage{...}` | add to preamble (most are already in main.tex.skeleton; if not, e.g. `\usepackage{amssymb}`) |
| `Citation 'foo' on page X undefined` | `\cite{foo}` has no `\bibitem{foo}` in `thebibliography` | grep both, add the missing `\bibitem` |
| `Overfull \hbox (X pt too wide)` on a URL | unbreakable token | wrap in `\url{...}` |
| `Overfull \hbox` on prose | tight line | reword OR `\sloppy` locally (don't suppress with `\hbadness`) |
| `Package fontspec Error: ... cannot be found` | wrong font name | use `TeX Gyre Termes` / `TeX Gyre Heros` / `TeX Gyre Cursor` (already in skeleton) |
| `! LaTeX Error: File 'figs/foo.png' not found` | path wrong or fig not zipped | `ls paper/figs/`; ensure path is `figs/foo.png` (relative to main.tex), and `figs/` was added to the zip |
| `LaTeX Warning: Reference 'X' on page Y undefined` | typo in `\ref{}`, or `\label{}` missing | `grep -n 'label{' main.tex`; latexmk auto-reruns so first compile may have stale refs that resolve on rerun |
| `! Missing $ inserted` | unescaped `_` `&` `%` `#` outside math mode | escape with backslash, OR wrap the chunk in `\verb||` or `$...$` |
| `! Extra }, or forgotten \endgroup` | brace mismatch | bisect: comment out latter half, recompile |
| `! Package inputenc Error: Unicode character ...` | wrong engine | the service uses xelatex; non-ASCII should work. If not, check that `\usepackage{fontspec}` is loaded |
| `error: subprocess.TimeoutExpired` (client side) | compile took >300s server-side, server killed it | minimize: comment out heaviest figure / TikZ block, recompile to localize |

## Recovery moves

- After 2 failed fix attempts on the same error, **minimize**: comment out the most
  recent figure / equation / table / TikZ block, recompile, then add back chunks
  one at a time to localize the offender.
- After 5 failed compile attempts total, **stop** and write `paper/STATUS.md`
  with: last error, what you've tried, suspected cause. Don't doom-loop.

## §bbl — why we use inline `thebibliography`

The compiler service runs `latexmk -xelatex` **once**. There is no `bibtex`
or `biber` stage. So:

- ✅ `\begin{thebibliography}{99} \bibitem{key} ... \end{thebibliography}` — works
- ❌ `\bibliography{refs} \bibliographystyle{plain}` — produces `[?]` everywhere

Therefore: write BibTeX entries to `refs.bib` **for hygiene/portability**, and
**also** emit a `thebibliography` block in `main.tex` with one `\bibitem` per
cited paper. **Both must stay in sync** — the citation pass writes both.

The service doc explicitly calls this out:
> 引用文献必须把 `.bbl` 一起打包。服务只跑一次 `latexmk -xelatex`，不跑
> `bibtex` / `biber`。如果 zip 里只有 `.bib`，引用会渲染成 `[?]`。

## Diagnostic shortcut

If you only need a quick check that the file parses, skip the zip step and use
a smaller harness:

```bash
echo '{"main":"main.tex","log":"1"}' >/dev/null  # placeholder; just zip + curl
```

(Always go through the full zip → POST flow — there's no shortcut that's actually
faster, and inconsistent zip contents are the #1 cause of "works for me, fails
in service".)
