import asyncio
import json
import logging
from typing import Any, Dict, List

from .base import BaseLLMClient
from .mock_data_core import MOCK_RESPONSES_CORE
from .mock_data_analysis import MOCK_RESPONSES_ANALYSIS

logger = logging.getLogger(__name__)

_DETECTION_RULES = [
    ("idea_generator", ["expert ML researcher", "Generate novel research ideas", "Innovations extracted from papers"]),
    ("idea_evaluator", ["ICLR Area Chair", "Strictly evaluate these research ideas", "Scoring criteria"]),
    ("idea_reviewer", ["审阅以下研究Idea", "评估维度"]),
    ("ablation_analyzer", ["分析以下消融实验结果", "贡献度"]),
    ("synthesizer", ["research synthesizer", "Expand idea seeds"]),
    ("critic", ["senior ICLR Area Chair", "evaluations", "already_done_by"]),
    ("analyst", ["research analyst examining", "thematic clusters", "cross_cluster_gaps"]),
    ("connector", ["non-obvious connections", "structural analogy", "transfer_direction"]),
    ("contrarian", ["contrarian researcher", "contrarian_seeds"]),
    ("reader", ["Compress it into structured insights", "core_insight", "key_trick"]),
    ("hypothesis", ["testable hypotheses from literature", "Hypotheses must be FALSIFIABLE"]),
    ("evidence", ["collecting evidence for or against specific hypotheses", "evidence_items", "stance"]),
    ("meta_analysis", ["meta-researcher analyzing", "macro-level trends"]),
    ("replication", ["reproducibility issues and hidden problems", "reproduction_issues"]),
    ("transfer", ["cross-domain method transfers", "structural analogy, not surface-level"]),
    ("critique", ["rigorous academic reviewer performing deep critique", "methodology, assumptions"]),
    ("theory", ["theoretical researcher skilled at finding mathematical", "mathematical rigor"]),
    ("follow_up", ["tracking cutting-edge work and identifying fast follow-up"]),
    ("adversarial", ["adversarial researcher", "failure_cases"]),
    ("limitation", ["stated limitations and turning them into concrete research"]),
    ("surveyor", ["research surveyor producing a literature survey"]),
    ("scout_query", ["research literature scout", "search queries"]),
    ("scout_analysis", ["research novelty analyst", "innovation_gaps"]),
    ("refiner", ["research idea refiner", "Preserve the core insight"]),
    ("merger_group_synth", ["Synthesize these ideas into a SINGLE concise summary"]),
    ("merger_meta", ["group syntheses into ONE meta-synthesis"]),
    ("merger_merge", ["research director reviewing", "group syntheses"]),
    ("keyword_expander", ["research keyword expansion agent", "arxiv_queries"]),
    ("direction_filter", ["research relevance evaluator", "Score each paper"]),
    ("idea_extractor_innovations", ["novel contributions and innovations"]),
    ("idea_extractor_methods", ["technical methods and algorithms"]),
    ("idea_extractor_scenarios", ["application scenarios and domains"]),
    ("idea_extractor_techniques", ["technical components and mechanisms"]),
]


class MockLLMClient(BaseLLMClient):
    def __init__(self, delay: float = 10.0, **kwargs):
        super().__init__(**kwargs)
        self._responses = {**MOCK_RESPONSES_CORE, **MOCK_RESPONSES_ANALYSIS}
        self.call_log: List[Dict[str, Any]] = []
        self._default_response = json.dumps({"result": "mock response"})
        self._delay = delay if delay is not None else 10.0

    async def chat(self, messages: List[Dict], **kwargs) -> str:
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        prompt = self._extract_user_content(messages)
        agent_type = self._detect_agent(prompt)
        response = self._responses.get(agent_type, self._default_response)
        self.call_log.append({
            "agent": agent_type,
            "prompt_length": len(prompt),
            "prompt_preview": prompt[:300],
        })
        logger.debug("MockLLM: detected agent=%s, response_length=%d", agent_type, len(response))
        return response

    async def chat_with_image(self, messages: List[Dict], image_path: str, **kwargs) -> str:
        return json.dumps({"description": "mock image analysis result"})

    async def embed(self, text: str, **kwargs) -> List[float]:
        return [0.01] * 768

    def _extract_user_content(self, messages: List[Dict]) -> str:
        if isinstance(messages, str):
            return messages
        user_content = ""
        system_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user" and not user_content:
                user_content = msg.get("content", "")
            elif msg.get("role") == "system" and not system_content:
                system_content = msg.get("content", "")
        if not user_content and messages:
            user_content = messages[-1].get("content", "")
        return system_content + "\n" + user_content if system_content else user_content

    def _detect_agent(self, prompt: str) -> str:
        for agent_type, keywords in _DETECTION_RULES:
            if all(kw in prompt for kw in keywords):
                return agent_type
        return "unknown"

    def reset_log(self):
        self.call_log.clear()

    def get_calls_for_agent(self, agent_type: str) -> List[Dict]:
        return [c for c in self.call_log if c["agent"] == agent_type]

    @property
    def total_calls(self) -> int:
        return len(self.call_log)
