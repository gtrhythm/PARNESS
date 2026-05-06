<div align="center">

# PARNESS

**End-to-End Automated Academic Research Pipeline**

*DAG-Orchestrated · LLM-Agent-Driven · Fully Configurable*

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Pipelines](https://img.shields.io/badge/pipelines-38-orange.svg)](config/pipelines/)
[![Modules](https://img.shields.io/badge/modules-140%2B-blueviolet.svg)](src/orchestrator/modules/)

</div>

---

## Overview

PARNESS automates the full lifecycle of academic research — from paper discovery through insight extraction, idea generation, experiment execution, to paper writing — powered by a **declarative DAG orchestration engine** with 140+ pluggable agent modules.

```
Paper Crawling ➜ PDF Parsing ➜ Insight Extraction ➜ Idea Generation/Evaluation ➜ Experiment Design/Execution ➜ Paper Writing
```

**What makes PARNESS different** is its pipeline engine: every workflow is a **pure YAML file**. No Python code is required to compose, extend, or rewire research pipelines. The framework provides topology sorting and data passing — all domain decisions (branching, iteration, evaluation) are made by autonomous agent nodes on the graph.

---

## Pipeline Engine

### Zero-Code Composition

Pipelines are declarative YAML DAGs. You compose research workflows by wiring existing modules through `depends_on`, `input_mapping`, `output_mapping`, and `routes` — no code changes needed.

```yaml
name: my_research_pipeline
config:
  topic: "Graph Neural Networks"

nodes:
  - id: search
    module: search_crawler
    params:
      max_results: 20

  - id: parse
    module: pdf_kit_parse
    depends_on: [search]

  - id: generate_ideas
    module: idea_generator
    depends_on: [parse]
    input_mapping:
      papers: output.parse.parsed_papers

  - id: judge
    module: idea_judge
    depends_on: [generate_ideas]
    params:
      threshold: 7.0
    routes:                          # ← conditional branching
      accept: idea_saver
      reject: idea_counter

  - id: idea_saver
    module: idea_saver
    depends_on: [judge]

  - id: idea_counter
    module: idea_counter
    depends_on: [judge]
    routes:
      continue: generate_ideas      # ← loop back
      exhausted: null
```

### Control Flow

The engine supports rich control flow — all driven by agent output, not hardcoded node types:

| Feature | Mechanism | Example |
|---------|-----------|---------|
| **Conditional routing** | Node emits `_route: "key"` → routes to mapped target | Accept/reject ideas |
| **Fan-out** | Node emits `_routes: ["a", "b"]` → multiple targets run in parallel | Save + persist simultaneously |
| **Iteration loops** | Route maps back to an earlier node | Generate ideas until 50 accepted |
| **Iteration controllers** | 5 built-in strategies: threshold, patience, improving, LLM-judged, multi-criteria | Retry until score ≥ 0.85 |
| **Backtrack edges** | `backtrack: true` on edges re-visits completed nodes | Re-process on parse failure |
| **Parallel levels** | Nodes with no dependency relation run concurrently via topological sort | Crawl 5 sources in parallel |
| **Result aggregation** | `result_aggregator` merges branches: concat, merge_dict, best_score, all | Merge multi-source search results |

### Resilient Execution

```yaml
nodes:
  - id: llm_agent
    module: idea_evaluator
    timeout: 120                      # per-node timeout (seconds)
    retry:
      max_attempts: 3
      backoff: exponential            # constant | linear | exponential
```

- Each node runs in a **fresh subprocess** — GPU memory is fully released on exit
- Per-node timeout and retry with configurable backoff
- Global `max_rounds` ceiling prevents infinite loops
- **Incremental persistence** taps can be wired onto any node to flush results to JSONL in real time — no data loss even on pipeline crash

### Data Flow

Every data dependency is explicit via dot-path addressing:

```yaml
input_mapping:
  papers: output.crawl.metadata       # read from another node's output
  topic: config.topic                 # read from pipeline global config
  idea: output.judge.idea             # nested field access
```

The validation script (`validate_pipeline.py`) statically checks all connections **before execution** — catch wiring errors instantly.

---

## Module Catalog

140+ registered building blocks, organized by category. All modules are **lazy-loaded** — only those referenced in your pipeline YAML are imported.

| Category | Modules | Highlights |
|----------|---------|------------|
| **Research Agents** | 18 | Reader, Analyst, Connector, Contrarian, Synthesizer, Critic, Transfer, Hypothesis, Theory, Meta-Analysis, Adversarial, Replication, ... |
| **Paper Crawlers** | 17 sources | arXiv, S2, OpenAlex, Crossref, NCBI, bioRxiv, Europe PMC, DBLP, ACL, CVF, IEEE, Frontiers, SSRN, Springer, ACS, PLOS, ICLR |
| **Idea Pipeline** | 9 | Generator, Evaluator, Reviewer, Deduplicator, Judge, Saver, Counter, Scheduler, Scout |
| **Experiment System** | 12 | Plan Generator/Evaluator/Reviser, Runner (local + OpenCode CLI), Verifier, Goal Evaluator, Report Generator, Chart Code Generator |
| **Paper Writing** | 9 | Writer, Section Writer, Editor, Reviewer, Formatter, Outline Generator, Coherence Checker, MD Assembler, LaTeX CLI |
| **Knowledge Graph** | 20 | Extract, Dedup, Embed, Build Edges (structural/semantic/LLM), Random Walk, Retrospect, Vector Search, NL Query, Cross-Paper Discovery, Rebuild, Prune |
| **Iteration Controllers** | 7 | Threshold, Patience, Improving, LLM-Judged, Multi-Criteria, Result Aggregator, Quality Scorer |
| **PDF Processing** | 7 | Parser (daemon + batch), PDF-Extract-Kit integration, PDF Queue Feeder |
| **Gates & Persistence** | 19 | Parse/Title/Summary Result Gates, Incremental Persistence, Paper/Idea/Experiment Persist, PDF Mover |
| **Reference Management** | 5 | Collector, Gap Analyzer, BibTeX Generator, Citation Inserter, Integrity Checker |

### Creating New Modules

```python
# src/my_module/my_adapter.py
from src.orchestrator.adapters.base import BaseModule

class MyAdapter(BaseModule):
    async def execute(self, inputs: dict) -> dict:
        result = do_something(inputs["data"])
        return {
            "output_data": result,
            "_route": "accept",       # optional: control flow
            "_score": 0.92,           # optional: self-assessment
        }
```

Then register it and use it in any pipeline YAML. Or use the scaffold generator:

```bash
python scripts/design_adapter.py --name my_adapter \
    --upstream idea_generator --downstream experiment_designer
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 9  Paper Writer (LaTeX generation)                     │
│  Layer 8  Knowledge Graph (Neo4j)                             │
│  Layer 7  PDF Parser (PDF-Extract-Kit)                        │
│  Layer 6  Crawlers (arXiv, S2, ICLR, CVPR, OpenAlex, ...)    │
│  Layer 5  Persistence (SQLite + JSONL incremental)             │
│  Layer 4  Monitoring (WebSocket dashboard + live progress)     │
│  Layer 3  DAG Orchestrator (YAML pipelines, ~900 LOC)          │
│  Layer 2  Module System (140+ pluggable agents, lazy-loaded)   │
│  Layer 1  LLM Provider (OpenAI, Anthropic, MiniMax, GLM, ...) │
└──────────────────────────────────────────────────────────────┘
```

The orchestrator engine (Layer 3) is deliberately thin (~900 lines). All intelligence lives in the 140+ module implementations. The framework provides only:
- Topological level sorting + parallel execution
- Explicit data flow via `input_mapping` / `output_mapping`
- Agent-driven routing via `_route` / `_routes` protocol
- Per-node subprocess isolation, timeout, and retry

---

## Quick Start

### Prerequisites

- Python 3.10+
- *(Optional)* NVIDIA GPU + CUDA for PDF parsing
- *(Optional)* Neo4j for knowledge graph features

### Installation

```bash
git clone https://github.com/gtrhythm/PARNESS.git
cd parness

python -m venv .venv && source .venv/bin/activate
pip install -e .                # base install
pip install -e ".[pdf]"         # with PDF parsing (CUDA required)
pip install -e ".[dev]"         # with dev/test dependencies
```

### Configuration

```bash
cp .env.example .env           # add your API keys
```

Configure LLM providers in `config/llm_config.yaml`:

```yaml
default_provider: openai
providers:
  openai:
    api_key: "your-api-key"
    model: "gpt-4"
```

### Run a Pipeline

```bash
# Run a single pipeline
python scripts/run_pipeline.py config/pipelines/simple_idea_test.yaml

# End-to-end: idea discovery → experiment → paper
python scripts/run_auto_idea_to_paper.py

# Validate pipeline wiring before execution
python scripts/validate_pipeline.py config/pipelines/simple_idea_test.yaml
python scripts/validate_pipeline.py config/pipelines/         # validate all
```

---

## Pipeline Examples

### Simple Linear Pipeline
Evaluate an idea, run an experiment, write a paper:
```yaml
nodes:
  - { id: evaluate,  module: idea_evaluator }
  - { id: design,    module: experiment_designer,  depends_on: [evaluate] }
  - { id: run,       module: experiment_runner_cli, depends_on: [design] }
  - { id: write,     module: paper_cli_runner,      depends_on: [run] }
```

### Iterative Loop with Quality Gate
Generate ideas until 50 are accepted:
```yaml
nodes:
  - { id: retrieve, module: paper_retriever }
  - { id: generate, module: idea_generator,  depends_on: [retrieve] }
  - { id: evaluate, module: idea_evaluator,  depends_on: [generate] }
  - id: judge
    module: idea_judge
    depends_on: [evaluate]
    routes:
      accept: idea_saver
      reject: counter
  - { id: idea_saver, module: idea_saver,   depends_on: [judge] }
  - id: counter
    module: idea_counter
    depends_on: [judge, idea_saver]
    routes:
      continue: generate      # loop back
      exhausted: null          # done
```

### Full Research Automation (4 Phases)
The `auto_paper_e2e_opencode.yaml` pipeline runs the complete lifecycle:
1. **Phase 1**: Iterative paper retrieval + summarization (nested inner/outer loops)
2. **Phase 2**: Idea scoring + best selection
3. **Phase 3**: Experiment plan → execute (OpenCode CLI) → verify → retry gate
4. **Phase 4**: Paper writing via OpenCode CLI
Plus incremental persistence taps at every stage for crash resilience.

### All Pre-built Pipelines

| Category | Pipeline | Description |
|----------|----------|-------------|
| **Search** | `paper_search_multi_source` | Search S2, OpenAlex, arXiv simultaneously |
| **Search** | `paper_search_multi_intent` | Multi-intent paper discovery |
| **PDF** | `pdf_parse_persist_layer` → `title_persist_layer` → `db_persist_layer` | 3-layer parsing architecture |
| **PDF** | `pdf_reparse_daemon_pipeline` | Continuous reprocessing daemon |
| **Indexing** | `paper_intra_index` | Full paper index build |
| **Indexing** | `paper_intra_index_incremental` | Incremental index update |
| **Ideas** | `idea_generation_loop` | Iterative generation with quality gates |
| **Ideas** | `idea_mining` | Bulk idea mining from paper corpus |
| **Ideas** | `idea_driven_crawl` | Crawl papers driven by idea gaps |
| **Automation** | `auto_idea_to_paper` | End-to-end idea → paper |
| **Automation** | `auto_paper_e2e_opencode` | 4-phase full lifecycle |
| **Experiments** | `experiment_opencode` | OpenCode-based experiment execution |
| **Benchmarks** | `bfs_vs_dfs` / `merge_vs_quick_sort` / `two_sum_comparison` | Algorithm benchmarking |
| **KG** | `kg_ingest` / `kg_query` / `kg_maintenance` | Knowledge graph lifecycle |
| **KG** | `kg_abstract_enrich` | Enrich KG nodes with abstracts |
| **Full** | `iterative_research_pipeline` | 5-phase research pipeline with monitoring |

---

## AI Coding Skills

PARNESS ships with skills for OpenCode and Claude Code that understand the pipeline architecture:

| Skill | Purpose |
|-------|---------|
| `design-adapter` | Generate adapter scaffold with input/output contracts |
| `design-new-agent` | End-to-end agent design workflow |
| `generate-pipeline-yaml` | Create pipeline YAML from natural language |
| `validate-pipeline` | Validate pipeline YAML integrity |
| `parse-pdf` | PDF parsing with layout detection, OCR, formula recognition |
| `multi-agent-update` | Parallel multi-agent modification workflow |

```bash
# OpenCode
cp -r skills/design-adapter ~/.opencode/skills/

# Claude Code
cp -r skills/design-adapter ~/.claude/skills/
```

---

## PDF-Extract-Kit

Integrates [PDF-Extract-Kit](https://github.com/opendatalab/PDF-Extract-Kit) for high-quality PDF parsing. Model weights are **not** included in the repo.

```bash
cd src/PDF-Extract-Kit
python -c "from huggingface_hub import snapshot_download; \
    snapshot_download('opendatalab/pdf-extract-kit-1.0', local_dir='.')"
```

---

## Project Structure

```
parness/
├── config/
│   ├── pipelines/                  # 38 YAML pipeline definitions
│   ├── kg_config.yaml              # Knowledge graph settings
│   ├── opencode_config.yaml        # OpenCode integration
│   └── resource_config.yaml        # Resource limits
├── scripts/
│   ├── run_pipeline.py             # Main pipeline runner
│   ├── run_auto_idea_to_paper.py   # Full automation script
│   ├── validate_pipeline.py        # Pipeline validator
│   └── design_adapter.py           # Adapter scaffold generator
├── src/
│   ├── orchestrator/               # DAG engine & adapter framework
│   │   ├── adapters/               # 140+ adapter modules
│   │   ├── iteration/              # Graph runner, controllers, state
│   │   ├── modules/                # Module registry & catalog
│   │   └── registry.py             # Lazy-load module factory
│   ├── llm_provider/               # Multi-provider LLM interface
│   ├── llm_dispatcher/             # LLM routing, rate limiting, retry
│   ├── knowledge_graph/            # Neo4j knowledge graph
│   ├── crawler/                    # Paper crawlers (17 sources)
│   ├── pdf_parser/                 # PDF parsing + daemon
│   ├── paper_cli/                  # Paper writing CLI
│   ├── paper_writer/               # Section-by-section writer agents
│   ├── idea_agents/                # Idea generation & evaluation
│   ├── experiment_*/               # Experiment design & execution
│   ├── db/                         # SQLite persistence layer
│   └── ...
├── skills/                         # OpenCode / Claude skills
├── pyproject.toml
└── .env.example
```

---

## Acknowledgments

- [PDF-Extract-Kit](https://github.com/opendatalab/PDF-Extract-Kit) — PDF parsing toolkit

## License

[MIT](LICENSE)
