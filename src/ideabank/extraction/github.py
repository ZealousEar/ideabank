"""GitHub repository content extraction."""

import re
import httpx

from .base import BaseExtractor, ExtractionResult


class GitHubExtractor(BaseExtractor):
    """Extract GitHub repository README and metadata."""

    name = "github_api"

    _REPO_PATTERN = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)")

    def can_handle(self, url: str, domain: str) -> bool:
        return domain == "github.com" and self._REPO_PATTERN.search(url) is not None

    def _parse_repo(self, url: str) -> tuple[str, str] | None:
        m = self._REPO_PATTERN.search(url)
        if not m:
            return None
        owner, repo = m.group(1), m.group(2)
        # Strip .git suffix
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo

    async def extract(self, url: str) -> ExtractionResult:
        result = ExtractionResult(url=url, canonical_url=url, extractor=self.name, content_type="readme")

        parsed = self._parse_repo(url)
        if not parsed:
            result.error = "Could not parse GitHub repo URL"
            return result

        owner, repo = parsed
        result.canonical_url = f"https://github.com/{owner}/{repo}"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0),
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "IdeaBank/1.0",
                },
            ) as client:
                # Get repo metadata
                repo_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}")
                repo_data = {}
                if repo_resp.status_code == 200:
                    repo_data = repo_resp.json()
                    result.title = repo_data.get("full_name", f"{owner}/{repo}")

                # Get README
                readme_resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/readme",
                    headers={"Accept": "application/vnd.github.v3.raw"},
                )

                if readme_resp.status_code == 200:
                    readme_text = readme_resp.text

                    if len(readme_text) > 50000:
                        readme_text = readme_text[:50000] + "\n\n[Truncated]"

                    # Build combined text: description + README
                    parts = []
                    desc = repo_data.get("description")
                    if desc:
                        parts.append(f"Description: {desc}")
                    stars = repo_data.get("stargazers_count")
                    lang = repo_data.get("language")
                    if stars is not None:
                        parts.append(f"Stars: {stars:,}")
                    if lang:
                        parts.append(f"Language: {lang}")
                    if parts:
                        parts.append("")
                    parts.append(readme_text)

                    text = "\n".join(parts)
                    result.text = text
                    result.word_count = len(text.split())
                elif repo_data.get("description"):
                    # No README but have description
                    result.text = f"Description: {repo_data['description']}"
                    result.word_count = len(result.text.split())
                else:
                    result.error = f"README fetch failed: HTTP {readme_resp.status_code}"

        except httpx.TimeoutException:
            result.error = "Request timed out"
        except Exception as e:
            result.error = str(e)[:500]

        return result
