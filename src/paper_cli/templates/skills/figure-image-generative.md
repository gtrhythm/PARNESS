# Skill: figure-image-generative (gpt-image-2)

**Use ONLY for non-technical, non-data figures**: paper teasers, section
opener illustrations, metaphorical diagrams (e.g., "research as factory",
"agents as pipelines"). **Never** for architecture diagrams, DAGs,
flowcharts, loss curves, tables — those go to TikZ or matplotlib (see
`tikz-figure.md`).

## Auth

Header: `Authorization: Bearer $GRSAI_API_KEY`. **Optional.** If unset,
**don't try** — the paper compiles fine without a teaser. Skip the figure
and move on.

```bash
if [ -z "$GRSAI_API_KEY" ]; then
  echo "GRSAI_API_KEY not set; skipping teaser"
  exit 0
fi
```

## Endpoint

```
POST https://grsai.dakka.com.cn/v1/draw/completions
Authorization: Bearer $GRSAI_API_KEY
Content-Type: application/json

{"model":"gpt-image-2", "prompt":"...", "aspectRatio":"16:9"}
```

## Critical pitfall — `aspectRatio` is camelCase

The JSON field is **`aspectRatio`**, not `aspect_ratio`. Snake-case is
silently ignored and the API defaults to `1:1`. Valid values:
`16:9`, `1:1`, `4:3`, `9:16`.

## Two response shapes

The API may respond as JSON or SSE. Both must be handled.

### JSON shape

```json
{"status":"succeeded","results":[{"url":"https://file5.aitohumanize.com/file/<hash>.png"}]}
```

`results[0].url` is a download link, **not** base64. Issue a second `GET` to
fetch the binary PNG.

### SSE shape

```
data: {"progress": 17, "status": "running"}
data: {"progress": 64, "status": "running"}
data: {"status": "succeeded", "results": [{"url": "https://..."}]}
```

Each `data:` line is one JSON event. Parse line by line; act on the
`status=="succeeded"` line.

## End-to-end Bash recipe

```bash
TEASER_PROMPT="A schematic of a multi-agent research pipeline, top-down view, minimal flat illustration, no text labels, soft pastel palette"

RESP=$(curl -sS -X POST "https://grsai.dakka.com.cn/v1/draw/completions" \
  -H "Authorization: Bearer $GRSAI_API_KEY" \
  -H "Content-Type: application/json" \
  --data "{\"model\":\"gpt-image-2\",\"prompt\":$(printf '%s' "$TEASER_PROMPT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),\"aspectRatio\":\"16:9\"}" \
  -m 300)

URL=$(echo "$RESP" | python3 - <<'PY'
import sys, json
buf = sys.stdin.read()
# try JSON
try:
    d = json.loads(buf)
    if d.get("status") == "succeeded" and d.get("results"):
        print(d["results"][0]["url"]); sys.exit(0)
except Exception:
    pass
# fall back to SSE
for line in buf.splitlines():
    line = line.strip()
    if line.startswith("data:"):
        line = line[5:].strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("status") == "succeeded" and d.get("results"):
        print(d["results"][0]["url"]); sys.exit(0)
sys.exit(1)
PY
)

if [ -z "$URL" ]; then
  echo "no URL parsed from response; first 200 bytes:"
  printf '%s' "$RESP" | head -c 200
  exit 1
fi

curl -sS -m 120 "$URL" -o paper/figs/teaser.png

# placeholder check
SIZE=$(stat -c%s paper/figs/teaser.png 2>/dev/null || echo 0)
if [ "$SIZE" -lt 100000 ]; then
  echo "WARNING: teaser.png is only $SIZE bytes — likely a placeholder; deleting"
  rm paper/figs/teaser.png
  exit 1
fi
echo "OK teaser.png ($SIZE bytes)"
```

Then in `main.tex`:

```latex
\begin{figure}[t]
\centering
\includegraphics[width=0.92\linewidth]{figs/teaser.png}
\caption{Caption that explains the metaphor (don't rely on text labels in the image).}
\label{fig:teaser}
\end{figure}
```

## When generation fails

The API can fail for: bad key, rate limit, content policy, transient backend
error. **None of these should block the paper.** If teaser generation fails
twice, drop the teaser entirely — the paper does not need a teaser to be
publishable.

## Quality guidance for prompts

- Keep prompts under 50 words.
- Don't ask for text in the image (the model often misspells).
- Prefer "minimal flat illustration", "soft pastel palette", "isometric view"
  type stylistic anchors — these reduce variance.
- For technical metaphors: describe the metaphor, not the technical content.
  Good: "abstract image of branching paths converging to a single point".
  Bad: "diagram of a multi-agent system with router, executor, and reviewer".

## Pitfalls summary

- `aspectRatio` (camelCase), not `aspect_ratio`.
- Response may be JSON or SSE; handle both.
- `results[0].url` requires a second GET — it's a redirect to a CDN.
- Download timeout 120s (CDN sometimes slow).
- Image URLs are **not permanent** — download immediately, don't store URLs.
- Placeholder PNG is 1×1 px (~69 bytes); always check file size ≥ 100KB.
- `placeholder=true` would be in metadata if the official adapter were used,
  but here we go raw — file size is the only signal.
