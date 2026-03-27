"""YouTube transcript extraction."""

import re
from typing import Optional

from .base import BaseExtractor, ExtractionResult

# youtube-transcript-api import with graceful fallback
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_YT_API = True
except ImportError:
    HAS_YT_API = False


class YouTubeExtractor(BaseExtractor):
    """Extract YouTube video transcripts."""

    name = "youtube_transcript"

    _YOUTUBE_PATTERNS = [
        re.compile(r"(?:youtube\.com/watch\?.*v=|youtu\.be/)([\w-]{11})"),
        re.compile(r"youtube\.com/embed/([\w-]{11})"),
    ]

    def can_handle(self, url: str, domain: str) -> bool:
        return domain in {"youtube.com", "youtu.be", "m.youtube.com"}

    def _extract_video_id(self, url: str) -> Optional[str]:
        for pattern in self._YOUTUBE_PATTERNS:
            m = pattern.search(url)
            if m:
                return m.group(1)
        return None

    async def extract(self, url: str) -> ExtractionResult:
        result = ExtractionResult(url=url, canonical_url=url, extractor=self.name, content_type="transcript")

        video_id = self._extract_video_id(url)
        if not video_id:
            result.error = "Could not extract video ID"
            return result

        result.canonical_url = f"https://www.youtube.com/watch?v={video_id}"

        if not HAS_YT_API:
            result.error = "youtube-transcript-api not installed"
            return result

        try:
            ytt_api = YouTubeTranscriptApi()
            transcript = ytt_api.fetch(video_id)

            # Combine transcript snippets
            text_parts = []
            for snippet in transcript.snippets:
                text_parts.append(snippet.text)

            text = " ".join(text_parts)
            if not text.strip():
                result.error = "Empty transcript"
                return result

            # Clean up repeated whitespace
            text = re.sub(r"\s+", " ", text).strip()

            if len(text) > 50000:
                text = text[:50000] + "\n\n[Truncated]"

            result.text = text
            result.word_count = len(text.split())

            # Try to get title via oEmbed
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    oembed_resp = await client.get(
                        f"https://www.youtube.com/oembed?url={result.canonical_url}&format=json"
                    )
                    if oembed_resp.status_code == 200:
                        data = oembed_resp.json()
                        result.title = data.get("title")
            except Exception:
                pass

        except Exception as e:
            result.error = str(e)[:500]

        return result
