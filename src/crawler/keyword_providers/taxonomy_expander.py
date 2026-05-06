import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from ..base import BaseKeywordProvider
from ..models import KeywordResult

logger = logging.getLogger(__name__)

DOMAIN_KEYWORD_MAP: Dict[str, List[str]] = {
    "cs": [
        "deep learning", "machine learning", "neural network", "reinforcement learning",
        "natural language processing", "computer vision", "transformer", "attention mechanism",
        "generative model", "representation learning", "graph neural network", "contrastive learning",
    ],
    "physics": [
        "quantum computing", "statistical mechanics", "condensed matter",
        "particle physics", "quantum field theory", "many-body physics",
        "topological insulator", "superconductor",
    ],
    "math": [
        "algebraic geometry", "number theory", "topology", "differential equation",
        "probability theory", "optimization", "functional analysis", "combinatorics",
    ],
    "stat": [
        "Bayesian inference", "causal inference", "hypothesis testing",
        "time series analysis", "survival analysis", "nonparametric statistics",
    ],
    "bio": [
        "CRISPR gene editing", "single-cell RNA sequencing", "protein structure prediction",
        "genome-wide association study", "epigenetics", "microbiome", "gene expression",
        "synthetic biology", "molecular dynamics", "bioinformatics",
    ],
    "neuroscience": [
        "fMRI functional connectivity", "prefrontal cortex decision making",
        "hippocampus memory encoding", "dopamine reward prediction",
        "neural plasticity synaptic", "optogenetics", "connectomics",
        "neural coding", "spike sorting", "brain-computer interface",
    ],
    "medicine": [
        "clinical trial", "drug discovery", "biomarker", "precision medicine",
        "immunotherapy", "vaccine development", "epidemiology",
    ],
    "chemistry": [
        "catalysis", "organic synthesis", "computational chemistry",
        "drug design", "materials chemistry", "spectroscopy",
    ],
    "economics": [
        "causal effect estimation", "game theory", "market mechanism design",
        "behavioral economics", "development economics", "macroeconomic policy",
    ],
    "nlp": [
        "large language model", "machine translation", "sentiment analysis",
        "named entity recognition", "question answering", "text generation",
        "dialogue system", "information extraction",
    ],
    "cv": [
        "object detection", "image segmentation", "3D reconstruction",
        "video understanding", "visual reasoning", "generative adversarial network",
    ],
}

ARXIV_CATEGORY_MAP: Dict[str, List[str]] = {
    "cs": ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE", "cs.RO"],
    "physics": ["hep-lat", "hep-ph", "cond-mat", "quant-ph", "astro-ph"],
    "math": ["math.CO", "math.NT", "math.AG", "math.AP", "math.PR"],
    "stat": ["stat.ML", "stat.ME", "stat.TH", "stat.AP"],
    "bio": ["q-bio.BM", "q-bio.GN", "q-bio.MN", "q-bio.NC", "q-bio.QM"],
    "neuroscience": ["q-bio.NC"],
    "economics": ["econ.GN", "q-fin.CP", "q-fin.EC"],
    "eess": ["eess.SP", "eess.IV", "eess.AS"],
}


class TaxonomyExpander(BaseKeywordProvider):
    def __init__(self, db_path: str = ""):
        self._db_path = db_path

    async def generate(self, **kwargs) -> List[KeywordResult]:
        domain = kwargs.get("domain", "")
        category = kwargs.get("category", "")
        max_keywords = kwargs.get("max_keywords", 20)

        results: List[KeywordResult] = []

        if domain:
            results.extend(self._from_domain(domain))
        if category:
            results.extend(self._from_category(category))

        if self._db_path:
            results.extend(self._from_db(domain, max_keywords))

        seen = set()
        unique = []
        for r in results:
            if r.keyword not in seen:
                seen.add(r.keyword)
                unique.append(r)

        return unique[:max_keywords]

    def _from_domain(self, domain: str) -> List[KeywordResult]:
        keywords = DOMAIN_KEYWORD_MAP.get(domain, [])
        return [
            KeywordResult(keyword=kw, confidence=0.7, source="taxonomy", domain=domain)
            for kw in keywords
        ]

    def _from_category(self, category: str) -> List[KeywordResult]:
        for domain, cats in ARXIV_CATEGORY_MAP.items():
            if category in cats:
                return self._from_domain(domain)
        return []

    def _from_db(self, domain: str, max_keywords: int) -> List[KeywordResult]:
        if not self._db_path or not Path(self._db_path).exists():
            return []
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT tag, COUNT(*) as cnt FROM paper_tags GROUP BY tag ORDER BY cnt DESC LIMIT ?",
                (max_keywords,),
            )
            results = [
                KeywordResult(keyword=row["tag"], confidence=0.5, source="db_taxonomy", domain=domain)
                for row in cursor.fetchall()
            ]
            conn.close()
            return results
        except Exception as e:
            logger.warning("TaxonomyExpander DB query failed: %s", e)
            return []

    def provider_name(self) -> str:
        return "taxonomy_expander"
