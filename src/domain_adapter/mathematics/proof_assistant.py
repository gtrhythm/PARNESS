from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PROOF_ASSIST_PROMPT = """You are a mathematical proof assistant. Help construct a proof for the following conjecture.

## Conjecture
{conjecture}

## Context
{context}

## Approach
{approach}

## Your Task
Break this conjecture down into a proof strategy:
1. Identify key lemmas needed
2. Suggest proof technique (contradiction, induction, direct, etc.)
3. Outline the proof steps
4. Identify potential gaps or difficulties

Return JSON:
{{
  "proof_strategy": "<technique>",
  "key_lemmas": ["<lemma1>", "<lemma2>"],
  "proof_steps": [
    {{
      "step": 1,
      "description": "<what to prove>",
      "technique": "<how>",
      "difficulty": "<easy|medium|hard>"
    }}
  ],
  "potential_gaps": ["<gap1>"],
  "confidence": <0.0-1.0>
}}
"""


class ProofAssistant:
    """Assist with mathematical proof construction and verification."""

    def __init__(self, llm_client=None, symbolic_engine=None):
        self.llm = llm_client
        self.symbolic_engine = symbolic_engine

    async def analyze_conjecture(
        self,
        conjecture: str,
        context: str = "",
        approach: str = "auto",
    ) -> Dict[str, Any]:
        if self.llm is None:
            return self._rule_based_analysis(conjecture)

        try:
            from src.idea_agents.llm_utils import call_llm, parse_json_response

            prompt = _PROOF_ASSIST_PROMPT.format(
                conjecture=conjecture,
                context=context[:1000],
                approach=approach,
            )

            resp = await call_llm(self.llm, prompt)
            return parse_json_response(resp)
        except Exception as e:
            logger.warning("LLM proof analysis failed: %s", e)
            return self._rule_based_analysis(conjecture)

    async def verify_step(
        self,
        step_description: str,
        symbolic_expression: str = "",
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "step": step_description,
            "verified": False,
            "method": "none",
        }

        if self.symbolic_engine and symbolic_expression:
            if "=" in symbolic_expression:
                parts = symbolic_expression.split("=", 1)
                if len(parts) == 2:
                    identity_check = self.symbolic_engine.verify_identity(
                        parts[0].strip(), parts[1].strip()
                    )
                    result["symbolic_verification"] = identity_check
                    result["verified"] = identity_check.get("is_identity", False)
                    result["method"] = "symbolic"

        return result

    async def decompose_theorem(
        self,
        theorem: str,
        max_depth: int = 3,
    ) -> List[Dict[str, Any]]:
        if self.llm is None:
            return [{"lemma": theorem, "difficulty": "unknown", "depth": 0}]

        try:
            from src.idea_agents.llm_utils import call_llm, parse_json_response

            prompt = f"""Decompose the following theorem into simpler lemmas that can be proved independently.

Theorem: {theorem}

Return JSON:
{{
  "lemmas": [
    {{
      "id": "L1",
      "statement": "<lemma statement>",
      "difficulty": "<easy|medium|hard>",
      "depends_on": [],
      "proof_hint": "<brief hint>"
    }}
  ],
  "assembly": "<how lemmas combine to prove the theorem>"
}}"""
            resp = await call_llm(self.llm, prompt)
            data = parse_json_response(resp)
            return data.get("lemmas", [])
        except Exception as e:
            logger.warning("Theorem decomposition failed: %s", e)
            return [{"lemma": theorem, "difficulty": "unknown", "depth": 0}]

    def _rule_based_analysis(self, conjecture: str) -> Dict[str, Any]:
        conjecture_lower = conjecture.lower()
        strategy = "direct"
        if "for all" in conjecture_lower or "forall" in conjecture_lower or "every" in conjecture_lower:
            strategy = "induction"
        elif "not" in conjecture_lower or "no " in conjecture_lower:
            strategy = "contradiction"
        elif "there exists" in conjecture_lower or "exists" in conjecture_lower:
            strategy = "constructive"
        elif "if and only if" in conjecture_lower or "iff" in conjecture_lower:
            strategy = "biconditional"

        return {
            "proof_strategy": strategy,
            "key_lemmas": [],
            "proof_steps": [
                {"step": 1, "description": "Parse and formalize the conjecture",
                 "technique": strategy, "difficulty": "medium"},
                {"step": 2, "description": "Identify and prove key lemmas",
                 "technique": "varies", "difficulty": "hard"},
                {"step": 3, "description": "Assemble lemmas into full proof",
                 "technique": strategy, "difficulty": "medium"},
            ],
            "potential_gaps": ["Formal verification needed", "Edge cases to check"],
            "confidence": 0.3,
        }
