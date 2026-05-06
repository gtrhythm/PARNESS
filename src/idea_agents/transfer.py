import asyncio
import logging
from typing import Dict, List

from .llm_utils import call_llm, parse_json_response
from .models import CompressedInsight, TransferIdea

logger = logging.getLogger(__name__)

_PROMPT = """You are an expert researcher skilled at identifying cross-domain method transfers.

You are given insights from papers. Identify methods or techniques that could be transferred from one domain to another.

Source domain: {source_domain}
Target domain: {target_domain}

Insights:
{insights_text}

For each viable transfer, return JSON:
{{
  "transfers": [
    {{
      "method_name": "Name of the method/technique",
      "method_description": "What it does and how it works",
      "transfer_rationale": "Why this transfer makes sense",
      "adaptation_needed": "What modifications are needed for the target domain",
      "feasibility_score": 0.0-1.0,
      "source_papers": ["paper titles where this method originates"]
    }}
  ]
}}

Rules:
- Only suggest transfers that have genuine structural analogy, not surface-level similarity
- Explain WHY the transfer would work (shared mathematical structure, similar problem framing)
- Be specific about what needs to change in the target domain
- Feasibility should consider computational/technical barriers
"""


class TransferAgent:
    def __init__(self, llm_client, max_concurrent: int = 4):
        self.llm = llm_client
        self.max_concurrent = max_concurrent

    async def find_transfers(
        self,
        insights: List[CompressedInsight],
        source_domain: str = "",
        target_domain: str = "",
    ) -> List[TransferIdea]:
        if not insights:
            return []

        batch_size = 8
        all_transfers = []

        for i in range(0, len(insights), batch_size):
            batch = insights[i:i + batch_size]
            insights_text = "\n".join(
                f"- [{ins.year}] {ins.title}: {ins.core_insight} "
                f"(key_trick: {ins.key_trick}, reusable: {ins.reusable_components})"
                for ins in batch
            )
            prompt = _PROMPT.format(
                source_domain=source_domain or "unspecified",
                target_domain=target_domain or "unspecified",
                insights_text=insights_text,
            )
            resp = await call_llm(self.llm, prompt)
            data = parse_json_response(resp)

            for t in data.get("transfers", []):
                all_transfers.append(TransferIdea(
                    source_domain=source_domain,
                    target_domain=target_domain,
                    method_name=t.get("method_name", ""),
                    method_description=t.get("method_description", ""),
                    transfer_rationale=t.get("transfer_rationale", ""),
                    adaptation_needed=t.get("adaptation_needed", ""),
                    feasibility_score=t.get("feasibility_score", 0.0),
                    source_papers=t.get("source_papers", []),
                ))

        logger.info("TransferAgent: found %d transfer ideas", len(all_transfers))
        return all_transfers
