# Idea: Compositional DAG-based scheduling for autonomous research agents

## Motivation

Existing autonomous research systems (AI-Scientist v1/v2, OpenAGS, InternAgent)
hard-code their pipeline shape: a fixed sequence of stages or a fixed
state machine, with domain logic baked into the orchestrator. Adding a new
review stage or swapping an LLM call requires modifying Python control flow.

## Hypothesis

A thin DAG runtime with a **four-field agent contract** (`_route`, `_routes`,
`_score`, `_metadata`) can express linear, branching, fan-out, and iterative
research pipelines as pure data, with no domain knowledge in the runner.

## Contribution

We present *parness*, an open-source framework that:
1. Decomposes the research life-cycle into 116 modules, 20 YAML pipelines.
2. Lets all routing decisions live in agents, not the runner.
3. Persists cross-run knowledge in 5 SQLite stores + Neo4j.

## Target paper structure

Short paper (4–8 pages, arxiv style). Sections: Intro / Related / Method /
Experiments / Conclusion.
