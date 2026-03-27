"""ArXiv paper abstract extraction."""

import re
import httpx

from .base import BaseExtractor, ExtractionResult


class ArxivExtractor(BaseExtractor):
    """Extract ArXiv paper abstracts via Atom API."""

    name = "arxiv_api"

    _ARXIV_ID_PATTERN = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)")

    def can_handle(self, url: str, domain: str) -> bool:
        return domain == "arxiv.org" and self._ARXIV_ID_PATTERN.search(url) is not None

    def _extract_paper_id(self, url: str) -> str | None:
        m = self._ARXIV_ID_PATTERN.search(url)
        return m.group(1) if m else None

    async def extract(self, url: str) -> ExtractionResult:
        result = ExtractionResult(url=url, canonical_url=url, extractor=self.name, content_type="abstract")

        paper_id = self._extract_paper_id(url)
        if not paper_id:
            result.error = "Could not extract ArXiv paper ID"
            return result

        result.canonical_url = f"https://arxiv.org/abs/{paper_id}"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                # Use Atom API
                api_url = f"http://export.arxiv.org/api/query?id_list={paper_id}"
                resp = await client.get(api_url)
                resp.raise_for_status()
                xml = resp.text

            # Parse title
            title_match = re.search(r"<title>(.*?)</title>", xml, re.DOTALL)
            if title_match:
                title = title_match.group(1).strip()
                # Skip the feed title "ArXiv Query..."
                all_titles = re.findall(r"<title>(.*?)</title>", xml, re.DOTALL)
                if len(all_titles) > 1:
                    result.title = re.sub(r"\s+", " ", all_titles[1]).strip()

            # Parse abstract/summary
            summary_match = re.search(r"<summary>(.*?)</summary>", xml, re.DOTALL)
            if summary_match:
                abstract = re.sub(r"\s+", " ", summary_match.group(1)).strip()
            else:
                result.error = "No abstract found"
                return result

            # Parse authors
            authors = re.findall(r"<name>(.*?)</name>", xml)

            # Build combined text
            parts = []
            if result.title:
                parts.append(f"Title: {result.title}")
            if authors:
                parts.append(f"Authors: {', '.join(authors)}")
            parts.append("")
            parts.append("Abstract:")
            parts.append(abstract)

            # Try to get categories
            categories = re.findall(r'<category[^>]*term="([^"]+)"', xml)
            if categories:
                parts.append("")
                parts.append(f"Categories: {', '.join(categories)}")

            text = "\n".join(parts)
            result.text = text
            result.word_count = len(text.split())

        except httpx.TimeoutException:
            result.error = "Request timed out"
        except Exception as e:
            result.error = str(e)[:500]

        return result
