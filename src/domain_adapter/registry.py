from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from .base import DomainAdapter

logger = logging.getLogger(__name__)


class DomainRegistry:
    """Central registry for research domain adapters.

    Usage:
        registry = DomainRegistry()
        registry.register(cs_adapter)
        registry.register(math_adapter)

        adapter = registry.get("cs_dl")
        domain = registry.detect_domain(idea)
    """

    def __init__(self):
        self._adapters: Dict[str, DomainAdapter] = {}

    def register(self, adapter: DomainAdapter) -> None:
        name = adapter.domain_name()
        if name in self._adapters:
            logger.warning("Overwriting existing adapter for domain: %s", name)
        self._adapters[name] = adapter
        logger.info("Registered domain adapter: %s (paradigm=%s)", name, adapter.experiment_paradigm())

    def get(self, domain: str) -> Optional[DomainAdapter]:
        return self._adapters.get(domain)

    def get_or_raise(self, domain: str) -> DomainAdapter:
        adapter = self._adapters.get(domain)
        if adapter is None:
            raise ValueError(
                f"No adapter registered for domain '{domain}'. "
                f"Available: {list(self._adapters.keys())}"
            )
        return adapter

    def list_domains(self) -> List[str]:
        return list(self._adapters.keys())

    def detect_domain(self, idea) -> str:
        """Auto-detect the research domain from an idea's category/metadata.

        Heuristic-based detection using keywords in the idea category,
        description, and methodology fields.
        """
        if hasattr(idea, "category"):
            category = (idea.category or "").lower()
            detected = self._match_category(category)
            if detected:
                return detected

        text_parts = []
        for attr in ("title", "description", "methodology", "expected_results"):
            val = getattr(idea, attr, "")
            if val:
                text_parts.append(val.lower())
        combined_text = " ".join(text_parts)

        return self._match_text(combined_text)

    def _match_category(self, category: str) -> Optional[str]:
        _CATEGORY_MAP = {
            "cs_dl": [
                "deep learning", "machine learning", "neural network",
                "computer vision", "nlp", "reinforcement learning",
                "transformer", "cnn", "gan", "diffusion", "llm",
                "dl", "ml", "ai", "cv", "classification",
            ],
            "mathematics": [
                "mathematics", "pure math", "applied math",
                "algebra", "topology", "analysis", "number theory",
                "combinatorics", "geometry", "proof", "theorem",
            ],
            "physics": [
                "physics", "quantum", "condensed matter",
                "particle physics", "astrophysics", "thermodynamics",
                "electromagnetism", "mechanics", "fluid dynamics",
                "plasma", "optics",
            ],
        }

        for domain, keywords in _CATEGORY_MAP.items():
            if domain not in self._adapters:
                continue
            for kw in keywords:
                if kw in category:
                    return domain
        return None

    def _match_text(self, text: str) -> str:
        _DOMAIN_KEYWORDS = {
            "cs_dl": [
                "neural", "training", "gpu", "model", "dataset",
                "accuracy", "loss function", "gradient", "backpropagation",
                "batch", "epoch", "learning rate", "transformer",
                "attention mechanism", "fine-tuning", "pre-training",
            ],
            "mathematics": [
                "theorem", "proof", "lemma", "conjecture", "corollary",
                "proposition", "axiom", "derivation", "formal verification",
                "symbolic", "algebraic", "topological", "inequality",
                "convergence", "existence", "uniqueness",
            ],
            "physics": [
                "simulation", "numerical", "ode", "pde", "differential equation",
                "monte carlo", "hamiltonian", "lagrangian", "energy",
                "momentum", "field", "wave", "particle", "quantum",
                "spectral", "eigenvalue", "boundary condition",
            ],
        }

        best_domain = "cs_dl"
        best_score = 0

        for domain, keywords in _DOMAIN_KEYWORDS.items():
            if domain not in self._adapters:
                continue
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_domain = domain

        return best_domain

    def all_required_tools(self) -> Dict[str, List[dict]]:
        result = {}
        for name, adapter in self._adapters.items():
            result[name] = [t.to_dict() for t in adapter.required_tools()]
        return result
