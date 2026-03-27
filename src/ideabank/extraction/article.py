"""Article content extraction using trafilatura."""

import httpx
import trafilatura

from .base import BaseExtractor, ExtractionResult


class ArticleExtractor(BaseExtractor):
    """Extract article content using trafilatura with httpx fallback."""

    name = "trafilatura"

    # Domains to skip (social media, images, etc.)
    SKIP_DOMAINS = {
        "twitter.com", "x.com", "t.co", "pic.twitter.com",
        "instagram.com", "facebook.com", "tiktok.com",
    }

    def can_handle(self, url: str, domain: str) -> bool:
        """Handle any HTTP URL not handled by specialized extractors."""
        if domain in self.SKIP_DOMAINS:
            return False
        return url.startswith("http://") or url.startswith("https://")

    async def extract(self, url: str) -> ExtractionResult:
        """Extract article content."""
        result = ExtractionResult(url=url, canonical_url=url, extractor=self.name, content_type="article")

        try:
            # Fetch with httpx (async, with timeout)
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(15.0),
                headers={"User-Agent": "Mozilla/5.0 (compatible; IdeaBank/1.0)"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text

            # Update canonical URL from final redirect
            result.canonical_url = str(resp.url)

            # Extract with trafilatura
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                favor_recall=True,
            )

            if not text or len(text.strip()) < 50:
                result.error = "Extraction returned insufficient text"
                return result

            # Truncate if too long
            if len(text) > 50000:
                text = text[:50000] + "\n\n[Truncated]"

            # Extract title
            metadata = trafilatura.extract(html, output_format="json", include_comments=False)
            if metadata:
                import json
                try:
                    meta_dict = json.loads(metadata) if isinstance(metadata, str) else metadata
                    result.title = meta_dict.get("title")
                except (json.JSONDecodeError, TypeError):
                    pass

            # Fallback title from HTML
            if not result.title and "<title>" in html.lower():
                import re
                title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
                if title_match:
                    result.title = title_match.group(1).strip()[:200]

            result.text = text
            result.word_count = len(text.split())

        except httpx.TimeoutException:
            result.error = "Request timed out"
        except httpx.HTTPStatusError as e:
            result.error = f"HTTP {e.response.status_code}"
        except Exception as e:
            result.error = str(e)[:500]

        return result
