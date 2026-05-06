# Skill: tikz-figure

Technical figures (architecture, DAG, flowchart, layered system, sequence
diagram, phase pipeline) **must be drawn with TikZ inline** in `main.tex`.

For data plots (loss curves, accuracy bars, scatter), use **matplotlib** in a
Bash one-liner, write to `paper/figs/<name>.pdf`, then
`\includegraphics{figs/<name>.pdf}` in main.tex.

For teaser / cover / metaphorical illustrations only, see
`figure-image-generative.md` (gpt-image-2). **Never use gpt-image-2 for
technical figures** — diffusion models can't preserve text labels, arrow
semantics, or precise geometry.

## TikZ libraries pre-loaded in arxiv template

`positioning, arrows.meta, shapes.geometric, shapes.symbols, fit,
backgrounds, calc, decorations.pathreplacing`

Add more via `\usetikzlibrary{...}` in the preamble if needed.

## Decision tree

| What you want to draw | Snippet |
|---|---|
| Top-down layered stack (system layers, software layers) | §1 |
| DAG / branching / iteration / fan-out | §2 |
| Left-to-right phase pipeline with mode coloring (e.g. LLM vs deterministic) | §3 |
| Simple 3--5 box flow | §4 |
| Comparison **table** | use `tabularx` + `booktabs`, NOT TikZ |
| Loss / accuracy / metric **plot** | matplotlib (§5) |
| Sequence diagram (call ordering) | §6 |
| Tree (hierarchy) | §7 |

---

## §1 Layered stack (top-down system layers)

```latex
\begin{figure}[t]
\centering
\begin{tikzpicture}[
  layer/.style={draw, rounded corners=2pt, minimum height=6.5mm,
                minimum width=78mm, font=\small, align=center, inner sep=3pt},
  infra/.style={layer, fill=gray!12},
  runtime/.style={layer, fill=blue!8},
  agent/.style={layer, fill=orange!12},
  pipeline/.style={layer, fill=green!12},
  arrow/.style={-{Stealth[length=2.5mm]}, thick, gray!70},
  side/.style={font=\scriptsize\itshape, gray!70!black, inner sep=1pt},
  node distance=1.4mm,
]
\node[pipeline]              (l3) {L3 \;\textsc{User entry-points}};
\node[runtime, below=of l3]  (l2) {L2 \;\textsc{Runtime kernel}};
\node[agent,   below=of l2]  (l1) {L1 \;\textsc{Agents \& adapters}};
\node[infra,   below=of l1]  (l0) {L0 \;\textsc{Platform / persistence}};
\foreach \a/\b in {l3/l2, l2/l1, l1/l0}{ \draw[arrow] (\a) -- (\b); }

% optional grouping band
\begin{scope}[on background layer]
  \node[fit=(l2) (l1), fill=blue!3, rounded corners=3pt, inner sep=2.5mm] {};
\end{scope}

% optional side annotations
\node[side, anchor=west] at ($(l3.east)+(2mm,0)$) {user};
\node[side, anchor=west] at ($(l2.east)+(2mm,0)$) {kernel};
\node[side, anchor=west] at ($(l1.east)+(2mm,0)$) {domain};
\node[side, anchor=west] at ($(l0.east)+(2mm,0)$) {persistence};
\end{tikzpicture}
\caption{Layered architecture. Configuration flows down at startup;
data flows up at runtime.}
\label{fig:layers}
\end{figure}
```

## §2 DAG with routes (branching / iteration)

```latex
\begin{figure}[t]
\centering
\begin{tikzpicture}[
  node/.style={draw, rounded corners=2pt, minimum width=18mm,
               minimum height=8mm, font=\small, align=center, inner sep=2pt},
  agent/.style={node, fill=orange!12},
  next/.style={node, fill=green!10},
  ctrl/.style={node, fill=blue!8, font=\footnotesize},
  arrow/.style={-{Stealth[length=2mm]}, thick},
  lab/.style={font=\scriptsize\ttfamily, inner sep=1pt},
]
% explicit successor
\node[agent] (a1)  at (0, 1.5)  {agent};
\node[next]  (n1a) at (3.4, 2.1) {step A};
\node[next]  (n1b) at (3.4, 0.9) {step B};
\draw[arrow] (a1) -- node[lab, above, sloped] {route="A"} (n1a);
\draw[arrow, dashed, gray] (a1) -- node[lab, below, sloped] {(else)} (n1b);

% iteration via score gate
\node[agent] (a2)  at (0, -1.0) {scorer};
\node[ctrl]  (c2)  at (3.4, -1.0) {iter ctrl};
\node[next]  (b2a) at (6.5, -0.4) {refine};
\node[next]  (b2b) at (6.5, -1.6) {exit};
\draw[arrow] (a2) -- node[lab, above] {score=0.83} (c2);
\draw[arrow] (c2) -- node[lab, above, sloped] {loop} (b2a);
\draw[arrow, dashed, gray] (c2) -- node[lab, below, sloped] {else} (b2b);
\end{tikzpicture}
\caption{Two routing patterns: explicit successor (top) and
iteration via a score gate (bottom).}
\label{fig:dag}
\end{figure}
```

## §3 Phase pipeline (LLM vs deterministic coloring)

```latex
\begin{figure*}[t]
\centering
\begin{tikzpicture}[
  phase/.style={draw, rounded corners=2pt, minimum width=20mm,
                minimum height=8mm, font=\small, align=center},
  llm/.style={phase, fill=orange!18},
  det/.style={phase, fill=blue!10},
  arrow/.style={-{Stealth[length=2mm]}, thick, gray!70!black},
  legend/.style={font=\scriptsize, inner sep=1pt},
  node distance=4mm,
]
\node[llm] (p1)                  {1.~extract};
\node[det, right=of p1]   (p2)   {2.~dedup};
\node[det, right=of p2]   (p3)   {3.~embed};
\node[llm, right=of p3]   (p4)   {4.~merge};
\node[det, right=of p4]   (p5)   {5.~persist};
\foreach \a/\b in {p1/p2, p2/p3, p3/p4, p4/p5}{ \draw[arrow] (\a) -- (\b); }

\node[legend, draw, fill=orange!18, rounded corners=1pt, anchor=north west]
  at ($(p1.south west)+(0,-7mm)$) (k1) {LLM phase};
\node[legend, draw, fill=blue!10, rounded corners=1pt, right=2mm of k1] {deterministic phase};
\end{tikzpicture}
\caption{Five-phase processing pipeline.}
\label{fig:phases}
\end{figure*}
```

## §4 Simple 3--5 box flow

```latex
\begin{figure}[t]
\centering
\begin{tikzpicture}[
  box/.style={draw, rounded corners=2pt, minimum width=22mm,
              minimum height=9mm, font=\small},
  arrow/.style={-{Stealth[length=2mm]}, thick},
  node distance=6mm,
]
\node[box] (a) {Input};
\node[box, right=of a] (b) {Process};
\node[box, right=of b] (c) {Output};
\draw[arrow] (a) -- (b);
\draw[arrow] (b) -- (c);
\end{tikzpicture}
\caption{Simple flow.}
\label{fig:flow}
\end{figure}
```

## §5 Data plot via matplotlib (NOT TikZ)

```bash
cd paper && python3 - <<'PY'
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(5, 3.2))
xs = [1, 2, 3, 4, 5]
ys = [0.40, 0.60, 0.70, 0.78, 0.82]
ax.plot(xs, ys, marker="o", linewidth=1.5)
ax.set_xlabel("epoch")
ax.set_ylabel("accuracy")
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig("figs/acc.pdf")
PY
```

In main.tex:

```latex
\begin{figure}[t]
\centering
\includegraphics[width=0.7\linewidth]{figs/acc.pdf}
\caption{Accuracy over epochs.}
\label{fig:acc}
\end{figure}
```

## §6 Sequence diagram (call ordering between actors)

```latex
\begin{figure}[t]
\centering
\begin{tikzpicture}[
  actor/.style={draw, rounded corners=2pt, minimum width=20mm, minimum height=7mm,
                font=\small, fill=gray!10},
  msg/.style={-{Stealth[length=2mm]}, thick},
  lab/.style={font=\scriptsize, inner sep=1pt, fill=white},
  node distance=22mm,
]
\node[actor] (u) at (0, 0) {User};
\node[actor, right=of u] (a) {Agent};
\node[actor, right=of a] (s) {Service};

% lifelines
\foreach \n in {u, a, s} {
  \draw[gray, dashed] (\n.south) -- ++(0, -3.2);
}

% messages, top→bottom
\draw[msg] ($(u.south)+(0, -0.3)$) -- node[lab, above] {request} ($(a.south)+(0, -0.3)$);
\draw[msg] ($(a.south)+(0, -1.0)$) -- node[lab, above] {API call} ($(s.south)+(0, -1.0)$);
\draw[msg] ($(s.south)+(0, -1.7)$) -- node[lab, above] {response} ($(a.south)+(0, -1.7)$);
\draw[msg] ($(a.south)+(0, -2.4)$) -- node[lab, above] {result} ($(u.south)+(0, -2.4)$);
\end{tikzpicture}
\caption{Sequence diagram for a single agent invocation.}
\label{fig:seq}
\end{figure}
```

## §7 Tree (hierarchy)

```latex
\begin{figure}[t]
\centering
\begin{tikzpicture}[
  every node/.style={draw, rounded corners=2pt, minimum width=20mm,
                     minimum height=7mm, font=\small, align=center},
  level 1/.style={sibling distance=42mm, level distance=12mm},
  level 2/.style={sibling distance=22mm, level distance=12mm},
  edge from parent/.style={draw, -{Stealth[length=2mm]}, thick, gray!70},
]
\node {Root}
  child { node {Branch A}
    child { node {Leaf A1} }
    child { node {Leaf A2} }
  }
  child { node {Branch B}
    child { node {Leaf B1} }
    child { node {Leaf B2} }
  };
\end{tikzpicture}
\caption{Tree hierarchy.}
\label{fig:tree}
\end{figure}
```

---

## TikZ pitfalls

- `\foreach \a/\b in {...}{ \draw ...; }` — the `;` is **inside** the body braces.
- `node distance=Xmm` only takes effect with relative positioning (`right=of`,
  `below=of`); absolute `(x,y)` ignores it.
- `\node[fit=(a) (b)]` requires the `fit` library AND a non-zero `inner sep`
  for visible padding around the fitted region.
- `on background layer` requires `\usetikzlibrary{backgrounds}`.
- Special chars in node text: escape `_`, `&`, `%`, `#` with `\` or wrap text
  in `{\detokenize{...}}` (rarely needed).
- `figure*` (two-column wide) uses `\textwidth`; `figure` (single column) uses
  `\linewidth`. For arxiv single-column layout both work, but use `figure*`
  for diagrams that need horizontal space.
- TikZ inside a `\begin{figure}` doesn't auto-center; add `\centering`.
- Long compile times: a complex TikZ figure can add 5--10s to compile. If
  you have 5+ TikZ figures consider externalizing (`\usetikzlibrary{external}`),
  but only after the paper compiles — don't optimize first.

## When TikZ won't fit

If the diagram is genuinely too complex for TikZ (>50 nodes, organic shapes,
photos), draw it externally and `\includegraphics` a PDF/PNG. **Document in
the figure caption that the source is in `figs/<name>.svg`** so the user
can regenerate.
