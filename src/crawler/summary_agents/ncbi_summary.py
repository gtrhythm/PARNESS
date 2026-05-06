import asyncio
import logging
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

import httpx

from ..base import BaseSummaryAgent
from ..models import PaperContent, SearchIntent
from ..tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

DOMAIN_MESH_MAP: Dict[str, str] = {
    "bio": "Biology[MeSH]",
    "neuroscience": "Brain[MeSH] OR Neuroscience[MeSH]",
    "medicine": "Medicine[MeSH]",
    "psychology": "Psychology[MeSH]",
    "chemistry": "Chemistry[MeSH]",
}


class NCBISummaryAgent(BaseSummaryAgent):
    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._rate_limiter = RateLimiter(min_interval=0.35 if api_key else 1.0)

    async def fetch(self, intent: SearchIntent) -> List[PaperContent]:
        term = self._build_term(intent)
        if not term:
            return []

        pmids = await self._search(term, intent)
        if not pmids:
            return []

        papers = await self._fetch_summaries(pmids)
        return papers[:intent.max_papers]

    def _build_term(self, intent: SearchIntent) -> str:
        parts = []
        if intent.keywords:
            kw_term = " AND ".join(f'"{kw}"[Title/Abstract]' for kw in intent.keywords)
            parts.append(f"({kw_term})")
        elif intent.domain:
            mesh = DOMAIN_MESH_MAP.get(intent.domain, intent.domain)
            parts.append(mesh)
        else:
            return ""

        if intent.year_from or intent.year_to:
            y_from = str(intent.year_from) if intent.year_from else "1900"
            y_to = str(intent.year_to) if intent.year_to else "2099"
            parts.append(f"{y_from}:{y_to}[dp]")

        return " AND ".join(parts)

    async def _search(self, term: str, intent: SearchIntent) -> List[str]:
        await self._rate_limiter.wait()
        params = {
            "db": "pubmed",
            "term": term,
            "retmax": intent.max_papers,
            "retmode": "json",
            "sort": "date" if intent.sort_by == "date" else "relevance",
        }
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{NCBI_EUTILS}/esearch.fcgi", params=params)
                resp.raise_for_status()
                data = resp.json()
                return data.get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            logger.warning("NCBI esearch failed: %s", e)
            return []

    async def _fetch_summaries(self, pmids: List[str]) -> List[PaperContent]:
        await self._rate_limiter.wait()
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{NCBI_EUTILS}/efetch.fcgi", params=params)
                resp.raise_for_status()
                return self._parse_pubmed_xml(resp.text, pmids)
        except Exception as e:
            logger.warning("NCBI efetch failed: %s", e)
            return []

    def _parse_pubmed_xml(self, xml_text: str, pmids: List[str]) -> List[PaperContent]:
        papers = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return papers

        for article in root.findall(".//PubmedArticle"):
            try:
                medline = article.find(".//MedlineCitation")
                pmid_el = medline.find("PMID") if medline is not None else None
                pmid = pmid_el.text if pmid_el is not None else ""

                art = medline.find("Article") if medline is not None else None
                if art is None:
                    continue

                title_el = art.find(".//ArticleTitle")
                title = title_el.text if title_el is not None and title_el.text else ""

                abstract_parts = []
                for abs_el in art.findall(".//AbstractText"):
                    text = "".join(abs_el.itertext())
                    if text:
                        abstract_parts.append(text)
                abstract = " ".join(abstract_parts)

                authors = []
                for author in art.findall(".//Author"):
                    last = author.find("LastName")
                    fore = author.find("ForeName")
                    name = ""
                    if last is not None and last.text:
                        name = last.text
                    if fore is not None and fore.text:
                        name = f"{fore.text} {name}" if name else fore.text
                    if name:
                        authors.append(name)

                year = None
                pub_date = art.find(".//PubDate")
                if pub_date is not None:
                    year_el = pub_date.find("Year")
                    if year_el is not None and year_el.text:
                        year = int(year_el.text)

                doi = None
                for aid in article.findall(".//ArticleId"):
                    if aid.get("IdType") == "doi":
                        doi = aid.text
                        break

                keywords = []
                for mesh in article.findall(".//MeshHeading/DescriptorName"):
                    if mesh.text:
                        keywords.append(mesh.text)

                papers.append(PaperContent(
                    paper_id=f"pmid:{pmid}",
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    year=year,
                    doi=doi,
                    venue="",
                    source="ncbi",
                    pdf_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/pmid/{pmid}/pdf" if doi else None,
                    is_open_access=False,
                    keywords=keywords,
                    extra={"pmid": pmid},
                ))
            except Exception as e:
                logger.warning("Failed to parse PubMed article: %s", e)

        return papers

    def supported_domains(self) -> List[str]:
        return ["bio", "neuroscience", "medicine", "psychology", "chemistry"]

    def rate_limit(self) -> float:
        return 0.35 if self._api_key else 1.0
