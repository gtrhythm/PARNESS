from __future__ import annotations

import logging
from typing import Optional

from .registry import DomainRegistry

logger = logging.getLogger(__name__)


class DomainDetector:
    """High-level domain detection service.

    Wraps DomainRegistry.detect_domain with caching and confidence scoring.
    """

    def __init__(self, registry: DomainRegistry):
        self.registry = registry
        self._cache: dict = {}

    def detect(self, idea, use_cache: bool = True) -> str:
        idea_id = getattr(idea, "idea_id", None) or getattr(idea, "title", "")
        if use_cache and idea_id in self._cache:
            return self._cache[idea_id]

        domain = self.registry.detect_domain(idea)
        logger.info("Detected domain '%s' for idea: %s", domain, idea_id[:80])

        if use_cache and idea_id:
            self._cache[idea_id] = domain

        return domain

    def detect_with_confidence(self, idea) -> dict:
        domain = self.detect(idea, use_cache=False)
        confidence = self._compute_confidence(idea, domain)

        return {
            "domain": domain,
            "confidence": confidence,
            "available_domains": self.registry.list_domains(),
        }

    def _compute_confidence(self, idea, domain: str) -> float:
        category = getattr(idea, "category", "") or ""
        if category:
            category_lower = category.lower()
            if domain.replace("_", " ") in category_lower or domain in category_lower:
                return 0.95

        title = getattr(idea, "title", "") or ""
        description = getattr(idea, "description", "") or ""
        combined = f"{title} {description}".lower()

        _STRONG_SIGNALS = {
            "cs_dl": [
                "neural network", "deep learning", "training", "transformer",
                "cnn", "gan", "reinforcement learning", "bert", "gpt",
            ],
            "mathematics": [
                "theorem", "proof of", "lemma", "conjecture",
                "we prove", "we show that", "proposition",
            ],
            "physics": [
                "simulation", "numerical solution", "ode", "pde",
                "monte carlo", "hamiltonian", "physical system",
            ],
        }

        signals = _STRONG_SIGNALS.get(domain, [])
        matches = sum(1 for s in signals if s in combined)

        if matches >= 3:
            return 0.9
        elif matches >= 2:
            return 0.75
        elif matches >= 1:
            return 0.6
        return 0.4

    def clear_cache(self):
        self._cache.clear()
