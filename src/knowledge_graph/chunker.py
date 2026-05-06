"""Knowledge unit extraction via multi-round LLM prompting (Phase 1).

Implements the three-round extraction pipeline from the knowledge graph
design doc §5.1: coarse extraction → refinement → multi-granularity
abstraction.  Also handles length-adaptation for content that exceeds
token budgets.
"""

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field, asdict
from typing import List

logger = logging.getLogger(__name__)

_ROUND1_PROMPT = """\
你是一个知识提取器。从以下原文中提取独立的知识单元。

规则：
1. 每个知识单元必须包含一个完整的、可独立理解的事实/观点/方法/结论
2. 不要把不相关的信息塞进同一个单元
3. 不要把一个完整论证拆成碎片（因果链要完整）
4. 每个 unit 标注 type: claim / method / result / definition / \
observation / limitation / comparison / hypothesis
5. 每个 unit 给出 evidence：原文中支撑这个提取的具体原文片段（逐字引用）

注意：不需要标注 unit 之间的关系，关系会在后续独立评估。

输出格式（JSON）:
{{
  "units": [
    {{
      "id": "u1",
      "text": "...",
      "type": "method",
      "evidence": "原文第X行的完整引用"
    }}
  ]
}}

原文:
---
{content}
---"""

_ROUND2_PROMPT = """\
你是一个知识精炼器。将以下知识单元精炼为一段自洽的文本。

要求：
1. 保留所有原始信息，不遗漏
2. 补充必要的上下文使这段文本可以独立理解（不依赖原文也能看懂）
3. 控制在 300 字以内
4. 如果原文有具体数字/公式/术语，必须保留

原始 unit:
---
{text}
---

原文上下文（供参考，不要照搬）:
---
{surrounding_text}
---"""

_ROUND3_PROMPT = """\
你是一个知识抽象器。将以下知识单元抽象为一段跨领域可理解的概括描述。

要求：
1. 去掉具体领域术语，替换为通用的学术概念
2. 保留核心方法思路和逻辑结构
3. 控制在 100 字以内
4. 使得不同领域但方法本质相同的知识单元，抽象后的文本应该高度相似

示例：
  原文: "基于马尔可夫链的状态转移模型改进蛋白质交互网络中的功能模块识别"
  抽象: "图结构上的随机游走方法用于模块/社区发现"

知识单元:
---
{chunk_text}
---"""

_SUMMARY_PROMPT = """\
请对以下长文本生成结构化摘要。要求：
1. 保留所有关键方法、实验结果、结论
2. 保留具体数字和术语
3. 输出不超过 4000 字

原文:
---
{content}
---"""

_THIN_TOKEN_ESTIMATE = 1.5

_SHORT_THRESHOLD = 2000
_LONG_THRESHOLD = 8000
_MAX_REFINED_CHARS = 300
_MAX_ABSTRACT_CHARS = 100


@dataclass
class KnowledgeUnit:
    id: str
    text: str
    unit_type: str
    evidence: str
    abstract_summary: str
    content_hash: str
    source_type: str
    source_id: str

    def to_dict(self) -> dict:
        return asdict(self)


def _estimate_tokens(text: str) -> int:
    return int(len(text) / _THIN_TOKEN_ESTIMATE)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _parse_json_from_response(response: str) -> dict:
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", response, re.DOTALL)
    if fence_match:
        body = fence_match.group(1).strip()
    else:
        brace_match = re.search(r"\{.*\}", response, re.DOTALL)
        body = brace_match.group(0) if brace_match else response.strip()
    return json.loads(body)


async def _llm_chat(llm_client, prompt: str) -> str:
    return await llm_client.chat(prompt)


async def _round1_extract(llm_client, content: str) -> List[dict]:
    prompt = _ROUND1_PROMPT.format(content=content)
    raw = await _llm_chat(llm_client, prompt)
    parsed = _parse_json_from_response(raw)
    return parsed.get("units", [])


async def _round2_refine(
    llm_client, unit_text: str, surrounding_context: str
) -> str:
    prompt = _ROUND2_PROMPT.format(
        text=unit_text, surrounding_text=surrounding_context or "(无额外上下文)"
    )
    refined = await _llm_chat(llm_client, prompt)
    if len(refined) > _MAX_REFINED_CHARS:
        refined = refined[:_MAX_REFINED_CHARS]
    return refined.strip()


async def _round3_abstract(llm_client, chunk_text: str) -> str:
    prompt = _ROUND3_PROMPT.format(chunk_text=chunk_text)
    abstract = await _llm_chat(llm_client, prompt)
    if len(abstract) > _MAX_ABSTRACT_CHARS:
        abstract = abstract[:_MAX_ABSTRACT_CHARS]
    return abstract.strip()


async def _summarize_long_content(llm_client, content: str) -> str:
    prompt = _SUMMARY_PROMPT.format(content=content)
    return await _llm_chat(llm_client, prompt)


def _split_by_paragraphs(content: str, max_tokens: int = 4000) -> List[str]:
    paragraphs = re.split(r"\n{2,}", content)
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)
        if current and current_len + para_tokens > max_tokens:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_tokens
        else:
            current.append(para)
            current_len += para_tokens

    if current:
        chunks.append("\n\n".join(current))

    return chunks if chunks else [content]


class KGChunker:
    """Two-round (plus abstraction) LLM extraction pipeline (Phase 1)."""

    def __init__(self, llm_client=None, config=None):
        self._llm_client = llm_client
        self._config = config or {}

    async def extract_units(
        self,
        llm_client,
        content: str,
        source_type: str,
        source_id: str,
        surrounding_context: str = "",
    ) -> List[KnowledgeUnit]:
        token_estimate = _estimate_tokens(content)

        if token_estimate < _SHORT_THRESHOLD:
            raw_units = await _round1_extract(llm_client, content)
        elif token_estimate <= _LONG_THRESHOLD:
            chunks = _split_by_paragraphs(content)
            raw_units = []
            for chunk in chunks:
                chunk_units = await _round1_extract(llm_client, chunk)
                raw_units.extend(chunk_units)
        else:
            summary = await _summarize_long_content(llm_client, content)
            paragraphs = _split_by_paragraphs(content, max_tokens=2000)
            key_paragraphs = paragraphs[:3]
            combined = (
                "【结构化摘要】\n"
                + summary
                + "\n\n【关键段落】\n"
                + "\n\n".join(key_paragraphs)
            )
            raw_units = await _round1_extract(llm_client, combined)

        if not raw_units:
            return []

        units: List[KnowledgeUnit] = []
        for raw in raw_units:
            raw_text = raw.get("text", "")
            raw_evidence = raw.get("evidence", "")
            raw_type = raw.get("type", "claim")

            refined_text = await _round2_refine(
                llm_client, raw_text, surrounding_context
            )

            abstract = await _round3_abstract(llm_client, refined_text)

            unit_id = raw.get("id") or str(uuid.uuid4())
            units.append(
                KnowledgeUnit(
                    id=unit_id,
                    text=refined_text,
                    unit_type=raw_type,
                    evidence=raw_evidence,
                    abstract_summary=abstract,
                    content_hash=_content_hash(refined_text),
                    source_type=source_type,
                    source_id=source_id,
                )
            )

        return units


async def extract_units(
    llm_client,
    content: str,
    source_type: str,
    source_id: str,
    surrounding_context: str = "",
) -> List[KnowledgeUnit]:
    """Convenience wrapper around :class:`KGChunker`."""
    chunker = KGChunker()
    return await chunker.extract_units(
        llm_client=llm_client,
        content=content,
        source_type=source_type,
        source_id=source_id,
        surrounding_context=surrounding_context,
    )
