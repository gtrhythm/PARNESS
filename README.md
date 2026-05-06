# PARNESS

**PARNESS** is an automated academic research pipeline powered by DAG-based orchestration and LLM agents.

```
Paper Crawling → PDF Parsing → Insight Extraction → Idea Generation/Evaluation → Experiment Design/Execution → Paper Writing
```

## Architecture

PARNESS implements a 9-layer stack:

| Layer | Component | Description |
|-------|-----------|-------------|
| 1 | LLM Provider | Unified interface to multiple LLM providers (OpenAI, Anthropic, MiniMax, etc.) |
| 2 | Module System | Pluggable agent architecture with registry and factory pattern |
| 3 | DAG Orchestrator | YAML-driven pipeline execution with dependency resolution |
| 4 | Monitoring | Real-time execution dashboard via WebSocket |
| 5 | Persistence | SQLite-based dual-layer storage with JSON reconstruction views |
| 6 | Crawlers | Multi-source academic paper crawling (arXiv, ICLR, CVPR, etc.) |
| 7 | PDF Parser | Integration with PDF-Extract-Kit for layout detection, OCR, formula recognition |
| 8 | Knowledge Graph | Neo4j-based paper relationship and concept graph |
| 9 | Paper Writer | LaTeX paper generation with experiment integration |

## Quick Start

### Prerequisites

- Python 3.10+
- (Optional) NVIDIA GPU with CUDA support for PDF parsing
- (Optional) Neo4j for knowledge graph features

### Installation

```bash
git clone https://github.com/your-org/parness.git
cd parness

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# For PDF parsing features (requires CUDA):
pip install -e ".[pdf]"
```

### Configuration

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in your API keys:
   ```
   S2_API_KEY=your-semantic-scholar-key
   ```

3. Configure your LLM provider in `config/llm_config.yaml`:
   ```yaml
   default_provider: openai
   providers:
     openai:
       api_key: "your-api-key"
       model: "gpt-4"
   ```

### Running a Pipeline

```bash
# Run a specific pipeline
python scripts/run_pipeline.py config/pipelines/simple_idea_test.yaml

# Run the full auto idea-to-paper pipeline
python scripts/run_auto_idea_to_paper.py
```

### Validating Pipelines

```bash
# Validate a single pipeline YAML
python scripts/validate_pipeline.py config/pipelines/simple_idea_test.yaml

# Validate all pipelines
python scripts/validate_pipeline.py config/pipelines/
```

### Designing New Adapters

```bash
# Generate adapter scaffold code
python scripts/design_adapter.py --name my_adapter --upstream idea_generator --downstream experiment_designer
```

## Project Structure

```
parness/
├── config/                  # Configuration files
│   ├── pipelines/           # Pipeline YAML definitions (38 pipelines)
│   ├── kg_config.yaml       # Knowledge graph config
│   ├── opencode_config.yaml # OpenCode integration config
│   └── resource_config.yaml # Resource limits
├── scripts/                 # Operational scripts
│   ├── run_pipeline.py      # Main pipeline runner
│   ├── run_auto_idea_to_paper.py  # Full automation script
│   ├── validate_pipeline.py # Pipeline validator
│   └── design_adapter.py    # Adapter code generator
├── src/                     # Source code
│   ├── orchestrator/        # DAG engine and adapter framework
│   ├── llm_provider/        # LLM provider integrations
│   ├── llm_dispatcher/      # LLM routing and dispatch
│   ├── knowledge_graph/     # Neo4j knowledge graph
│   ├── crawler/             # Paper crawlers
│   ├── pdf_parser/          # PDF parsing integration
│   ├── paper_cli/           # Paper writing CLI
│   ├── paper_writer/        # Paper writer agents
│   ├── idea_agents/         # Idea generation/evaluation
│   ├── experiment_*/        # Experiment design/execution
│   ├── db/                  # Database layer
│   └── ...                  # Other agent packages
├── skills/                  # OpenCode/Claude skills (see below)
├── pyproject.toml           # Python project definition
└── .env.example             # Environment template
```

## Skills

PARNESS ships with several AI coding skills that enhance OpenCode or Claude Code workflows:

| Skill | Description |
|-------|-------------|
| `design-adapter` | Design new adapters with auto-generated input/output contracts |
| `design-new-agent` | End-to-end agent design workflow |
| `generate-pipeline-yaml` | Generate pipeline YAML from natural language descriptions |
| `validate-pipeline` | Validate pipeline YAML integrity |
| `parse-pdf` | PDF parsing with layout detection, OCR, and formula recognition |
| `multi-agent-update` | Parallel multi-agent modification workflow |

To use these skills, copy the desired skill folder to your `.opencode/skills/` or `.claude/skills/` directory:

```bash
# For OpenCode users
cp -r skills/design-adapter ~/.opencode/skills/

# For Claude Code users
cp -r skills/design-adapter ~/.claude/skills/
```

## Pipeline Examples

PARNESS includes 38 pipeline configurations:

- **Paper Search**: `paper_search_multi_source.yaml` — Search S2, OpenAlex, and arXiv simultaneously
- **PDF Processing**: `pdf_parse_persist_layer.yaml` → `title_persist_layer.yaml` → `db_persist_layer.yaml` (3-layer architecture)
- **Idea Generation**: `idea_generation_loop.yaml` — Iterative idea generation with quality gates
- **Full Automation**: `auto_idea_to_paper.yaml` — End-to-end from idea to paper
- **Knowledge Graph**: `kg_ingest.yaml`, `kg_query.yaml`, `kg_maintenance.yaml`
- **Algorithm Testing**: `bfs_vs_dfs.yaml`, `merge_vs_quick_sort.yaml`, `two_sum_comparison.yaml`

## PDF-Extract-Kit

PARNESS integrates [PDF-Extract-Kit](https://github.com/opendatalab/PDF-Extract-Kit) for high-quality PDF parsing. The submodule is included without pretrained model weights.

To download model weights:
```bash
cd src/PDF-Extract-Kit
# Download from HuggingFace
python -c "from huggingface_hub import snapshot_download; snapshot_download('opendatalab/pdf-extract-kit-1.0', local_dir='.')"
```

## License

[Your License Here]

## Acknowledgments

- [PDF-Extract-Kit](https://github.com/opendatalab/PDF-Extract-Kit) — PDF parsing toolkit
