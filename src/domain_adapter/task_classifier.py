from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .models import TaskAssignment, TaskClassification

logger = logging.getLogger(__name__)

_CLASSIFIER_PROMPT = """You are a research task classification expert. Analyze the following research idea and classify each major task as human-suitable, machine-suitable, or collaborative.

## Research Idea
Title: {title}
Description: {description}
Category: {category}
Methodology: {methodology}
Domain: {domain}

## Classification Framework

For each task in the research pipeline, decide the assignment:

1. **HUMAN_ONLY** - Requires human creativity, intuition, or physical action
   - Core creative insight / novel direction
   - Physical experiments (lab work)
   - Strategic decisions about research direction
   - Peer review / ethical judgment

2. **HUMAN_LEAD** - Human drives, machine assists
   - Designing novel architectures or methods
   - Interpreting unexpected results
   - Writing key arguments / narrative
   - Making judgment calls on tradeoffs

3. **MACHINE_LEAD** - Machine drives, human reviews
   - Literature search and summarization
   - Code implementation from specs
   - Numerical computations / training
   - Data preprocessing

4. **MACHINE_ONLY** - Fully automated
   - Hyperparameter tuning
   - Training runs
   - Metric computation
   - Formatting / typesetting
   - Reference management

5. **COLLABORATIVE** - Tight human-machine iteration
   - Debugging complex failures
   - Exploring parameter spaces
   - Iterative refinement

## Task
List all major tasks for this research project and classify each.

Return JSON:
{{
  "tasks": [
    {{
      "task_name": "<short name>",
      "description": "<what needs to be done>",
      "assignment": "<human_only|human_lead|machine_lead|machine_only|collaborative>",
      "reason": "<why this assignment>",
      "tools": "<what tools/resources needed>",
      "estimated_effort": "<low|medium|high>"
    }}
  ],
  "summary": "<1-2 sentence overview of the human-machine split>"
}}
"""


class HumanMachineTaskClassifier:
    """Classify research tasks into human vs machine assignments."""

    def __init__(self, llm_client=None):
        self.llm = llm_client

    async def classify(self, idea: Any, domain: str = "") -> TaskClassification:
        if self.llm is None:
            return self._rule_based_classify(idea, domain)

        prompt = _CLASSIFIER_PROMPT.format(
            title=getattr(idea, "title", ""),
            description=getattr(idea, "description", "")[:1000],
            category=getattr(idea, "category", ""),
            methodology=getattr(idea, "methodology", ""),
            domain=domain,
        )

        try:
            from ..idea_agents.llm_utils import call_llm, parse_json_response
            resp = await call_llm(self.llm, prompt)
            data = parse_json_response(resp)
            tasks = data.get("tasks", [])
            return TaskClassification(tasks=tasks)
        except Exception as e:
            logger.warning("LLM-based classification failed, falling back to rules: %s", e)
            return self._rule_based_classify(idea, domain)

    def _rule_based_classify(self, idea: Any, domain: str) -> TaskClassification:
        title = getattr(idea, "title", "").lower()
        desc = getattr(idea, "description", "").lower()
        combined = f"{title} {desc}"

        tasks = [
            {
                "task_name": "literature_review",
                "description": "Search and summarize related work",
                "assignment": TaskAssignment.MACHINE_LEAD.value,
                "reason": "Automated search and summarization",
                "tools": "Semantic Scholar API, vector search",
                "estimated_effort": "medium",
            },
            {
                "task_name": "idea_generation",
                "description": "Generate and evaluate research ideas",
                "assignment": TaskAssignment.COLLABORATIVE.value,
                "reason": "Machine generates candidates, human selects/refines",
                "tools": "LLM, idea_agents",
                "estimated_effort": "high",
            },
            {
                "task_name": "experiment_design",
                "description": "Design experimental methodology",
                "assignment": TaskAssignment.HUMAN_LEAD.value,
                "reason": "Needs human insight on what to test",
                "tools": "LLM, domain knowledge",
                "estimated_effort": "high",
            },
            {
                "task_name": "implementation",
                "description": "Implement code / models",
                "assignment": TaskAssignment.MACHINE_ONLY.value,
                "reason": "Code generation and execution is automatable",
                "tools": "opencode, PyTorch",
                "estimated_effort": "high",
            },
        ]

        if domain == "mathematics":
            tasks.extend([
                {
                    "task_name": "proof_attempt",
                    "description": "Attempt formal or informal proofs",
                    "assignment": TaskAssignment.COLLABORATIVE.value,
                    "reason": "Machine generates proof steps, human verifies logic",
                    "tools": "Lean/Coq, SymPy",
                    "estimated_effort": "high",
                },
                {
                    "task_name": "counterexample_search",
                    "description": "Search for counterexamples",
                    "assignment": TaskAssignment.MACHINE_ONLY.value,
                    "reason": "Exhaustive/random search is automatable",
                    "tools": "Z3, random testing",
                    "estimated_effort": "medium",
                },
            ])
        elif domain == "physics":
            tasks.extend([
                {
                    "task_name": "simulation_setup",
                    "description": "Configure and run numerical simulations",
                    "assignment": TaskAssignment.MACHINE_LEAD.value,
                    "reason": "Machine sets up and runs, human validates physics",
                    "tools": "scipy, NumPy, COMSOL",
                    "estimated_effort": "high",
                },
                {
                    "task_name": "physical_validation",
                    "description": "Validate results against physical laws",
                    "assignment": TaskAssignment.HUMAN_LEAD.value,
                    "reason": "Requires physical intuition",
                    "tools": "Domain knowledge",
                    "estimated_effort": "medium",
                },
            ])
        else:
            tasks.extend([
                {
                    "task_name": "training",
                    "description": "Train models with hyperparameters",
                    "assignment": TaskAssignment.MACHINE_ONLY.value,
                    "reason": "Automated training and monitoring",
                    "tools": "GPU, PyTorch",
                    "estimated_effort": "high",
                },
                {
                    "task_name": "auto_tuning",
                    "description": "Tune hyperparameters automatically",
                    "assignment": TaskAssignment.MACHINE_ONLY.value,
                    "reason": "Bayesian/grid search is fully automated",
                    "tools": "Optuna, Ray Tune",
                    "estimated_effort": "medium",
                },
            ])

        tasks.extend([
            {
                "task_name": "result_interpretation",
                "description": "Interpret and explain results",
                "assignment": TaskAssignment.HUMAN_LEAD.value,
                "reason": "Requires deep understanding",
                "tools": "Visualization tools",
                "estimated_effort": "high",
            },
            {
                "task_name": "paper_writing",
                "description": "Write the research paper",
                "assignment": TaskAssignment.COLLABORATIVE.value,
                "reason": "Machine drafts, human refines",
                "tools": "LLM, LaTeX",
                "estimated_effort": "high",
            },
            {
                "task_name": "quality_review",
                "description": "Review paper for quality and correctness",
                "assignment": TaskAssignment.HUMAN_LEAD.value,
                "reason": "Final quality check needs human judgment",
                "tools": "Review system",
                "estimated_effort": "medium",
            },
        ])

        return TaskClassification(tasks=tasks)
