import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from .base import LLMAgentModule
from ..monitoring.reporter import AgentOutput

logger = logging.getLogger(__name__)

_TITLE_PROMPT = """You are a document metadata extractor. Given the beginning portion of an academic paper, extract its **exact title**.

Paper content:
---
{content}
---

Return your answer as a JSON object with exactly one field:
{{"title": "the exact paper title here"}}

Rules:
- Output ONLY the JSON object, nothing else.
- The title must be the **exact** title as it appears in the paper.
- Do NOT include authors, affiliations, dates, or any other metadata.
"""

_HEADINGS_PROMPT = """You are a document metadata extractor. The list below contains every Markdown heading (in document order) extracted from an academic paper.

Headings:
---
{content}
---

Pick the ONE heading that is the paper's main title. The title is normally the first non-trivial heading and is NOT a section name like "Abstract", "Introduction", "Conclusion", "References", "Appendix", an author name, an affiliation, or a numbered section ("1 …", "2 …").

If the title is split across two consecutive heading lines (e.g. it wraps), join them with a single space.

PDF extraction sometimes loses spaces between words (e.g. "HOLISTICADVERSARIALLYROBUSTPRUNING"). If the title looks like one long run-on uppercase word, restore the natural word boundaries (e.g. "HOLISTIC ADVERSARIALLY ROBUST PRUNING"). Use sensible English word segmentation; preserve the original casing of each segment.

Return your answer as a JSON object with exactly one field:
{{"title": "the exact paper title here"}}

Rules:
- Output ONLY the JSON object, nothing else.
- Trim leading "#" characters and surrounding whitespace.
- Do NOT include authors, affiliations, dates, or any other metadata.
"""

_HEADING_CHARS = 2000


_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_title(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    Used only for the consensus equality check so cosmetic differences
    (case, spacing, hyphens, trailing punctuation) don't reset the
    "3 in a row" counter. The original LLM string is still what we
    return and persist.
    """
    if not s:
        return ""
    return _NORMALIZE_RE.sub(" ", s.lower()).strip()


def _extract_markdown_headings(markdown: str, max_chars: int = 4000) -> str:
    if not markdown:
        return ""
    headings: List[str] = []
    for line in markdown.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            headings.append(stripped.rstrip())
    joined = "\n".join(headings)
    return joined[:max_chars]


def _extract_front_text(full_text: str, max_chars: int = 3000) -> str:
    if not full_text:
        return ""
    return full_text[:max_chars]


def _parse_json_title(raw: str) -> Optional[str]:
    text = raw.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1:]
        text = text.split("```")[0]
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "title" in obj:
            return obj["title"].strip()
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        chunk = text[start:end]
        try:
            obj = json.loads(chunk)
            if isinstance(obj, dict) and "title" in obj:
                return obj["title"].strip()
        except json.JSONDecodeError:
            chunk = re.sub(r',\s*([}\]])', r'\1', chunk)
            try:
                obj = json.loads(chunk)
                if isinstance(obj, dict) and "title" in obj:
                    return obj["title"].strip()
            except json.JSONDecodeError:
                pass
    logger.warning("Failed to parse title JSON: %s", raw[:200])
    return None


async def _call_llm_with_retry(llm_client, prompt: str, max_retries: int = 2) -> str:
    for attempt in range(max_retries + 1):
        try:
            return await llm_client.chat(prompt)
        except Exception as e:
            err_str = str(e)
            if "529" in err_str or "overloaded" in err_str or "500" in err_str:
                wait = 10 * (attempt + 1)
                logger.warning("LLM overloaded (attempt %d), waiting %ds", attempt + 1, wait)
                await asyncio.sleep(wait)
                continue
            if attempt < max_retries:
                await asyncio.sleep(3 * (attempt + 1))
                continue
            raise
    return await llm_client.chat(prompt)


class TitleExtractorModule(LLMAgentModule):
    module_name = "title_extractor"

    INPUT_SPEC = {
        "papers": {"type": "list", "required": False, "default": []},
    }
    OUTPUT_SPEC = {
        "titles": {"type": "list"},
        "paper_count": {"type": "int"},
        "success_count": {"type": "int"},
        "fail_count": {"type": "int"},
    }

    async def run_agent(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        papers = inputs.get("papers", [])

        if not papers:
            return {
                "titles": [],
                "paper_count": 0,
                "success_count": 0,
                "fail_count": 0,
            }

        llm_client = self._get_llm_client()
        max_concurrent = self.config.get("max_concurrent", 4)
        sem = asyncio.Semaphore(max_concurrent)
        results: List[Dict[str, Any]] = []

        async def _extract_title(paper: Dict):
            async with sem:
                paper_id = paper.get("paper_id", "")
                try:
                    title = await self._extract_title_consensus(llm_client, paper)
                    if title is not None:
                        results.append({
                            "paper_id": paper_id,
                            "title": title,
                            "status": "success",
                        })
                    else:
                        results.append({
                            "paper_id": paper_id,
                            "title": None,
                            "status": "fail",
                        })
                except Exception as e:
                    logger.warning("Title extraction failed for %s: %s", paper_id, e)
                    results.append({
                        "paper_id": paper_id,
                        "title": None,
                        "status": "fail",
                        "error": str(e),
                    })

        await asyncio.gather(*[_extract_title(p) for p in papers])

        success = [r for r in results if r.get("status") == "success"]
        failed = [r for r in results if r.get("status") == "fail"]

        logger.info(
            "TitleExtractor: %d papers, %d success, %d fail",
            len(results), len(success), len(failed),
        )

        return {
            "titles": results,
            "paper_count": len(results),
            "success_count": len(success),
            "fail_count": len(failed),
        }

    async def _extract_title_consensus(self, llm_client, paper: Dict) -> Optional[str]:
        max_retries = self.config.get("max_retries", 12)
        consensus_n = self.config.get("consensus_n", 3)
        batch_size = self.config.get("consensus_batch_size", consensus_n)
        headings_only = bool(self.config.get("headings_only", False))

        full_text = paper.get("full_text", "") or paper.get("markdown", "")
        if not full_text:
            abstract = paper.get("abstract", "")
            if abstract:
                full_text = abstract
        if not full_text or len(full_text) < 20:
            return None

        if headings_only:
            content = _extract_markdown_headings(full_text)
            if not content.strip():
                logger.warning(
                    "headings_only mode: no markdown headings found, "
                    "falling back to front-text extraction",
                )
                content = _extract_front_text(full_text)
                prompt = _TITLE_PROMPT.format(content=content)
            else:
                prompt = _HEADINGS_PROMPT.format(content=content)
        else:
            content = _extract_front_text(full_text)
            prompt = _TITLE_PROMPT.format(content=content)

        # Global tally across all batches: normalized -> (count, first-seen original)
        tally: Dict[str, List[Any]] = {}
        total_calls = 0

        async def _one_call() -> Optional[str]:
            try:
                raw = await _call_llm_with_retry(llm_client, prompt)
            except Exception as e:
                logger.warning("LLM call failed: %s", e)
                return None
            return _parse_json_title(raw)

        while total_calls < max_retries:
            this_batch = min(batch_size, max_retries - total_calls)
            results = await asyncio.gather(
                *[_one_call() for _ in range(this_batch)],
                return_exceptions=False,
            )
            total_calls += this_batch

            for title in results:
                if title is None:
                    continue
                norm = _normalize_title(title)
                if not norm:
                    continue
                if norm in tally:
                    tally[norm][0] += 1
                else:
                    tally[norm] = [1, title]

            # Pick the current leader; if it has >= consensus_n, return it.
            if tally:
                leader_norm, (count, original) = max(
                    tally.items(), key=lambda kv: kv[1][0]
                )
                if count >= consensus_n:
                    logger.info(
                        "Title consensus reached after %d calls (concurrent batches): '%s' (count=%d)",
                        total_calls, original, count,
                    )
                    return original

        # Exhausted budget; return best-effort if any title was seen.
        if tally:
            leader_norm, (count, original) = max(
                tally.items(), key=lambda kv: kv[1][0]
            )
            logger.warning(
                "Title extraction failed: max_retries=%d exhausted, "
                "consensus_n=%d not reached (best leader: '%s' count=%d)",
                max_retries, consensus_n, original, count,
            )
        else:
            logger.warning(
                "Title extraction failed: max_retries=%d exhausted, "
                "no parsable titles", max_retries,
            )
        return None

    def emit_output(self, result: Dict[str, Any]) -> Optional[AgentOutput]:
        titles = result.get("titles", [])
        if not titles:
            return None
        rows = []
        for t in titles:
            rows.append([
                t.get("paper_id", "")[:40],
                (t.get("title") or "fail")[:60],
                t.get("status", "fail"),
            ])
        return AgentOutput(
            display_type="table",
            title="Title Extraction Results",
            data={
                "headers": ["Paper ID", "Title", "Status"],
                "rows": rows,
            },
            render_hints={"max_col_width": [30, 50, 8]},
        )
