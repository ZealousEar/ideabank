"""URL canonicalization for deduplication."""

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

CANONICALIZER_VERSION = "1"

# Tracking params to strip (case-insensitive match)
STRIP_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "source",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "s",
    "si",
}

# Domain aliases
DOMAIN_ALIASES = {
    "twitter.com": "x.com",
    "www.twitter.com": "x.com",
    "mobile.twitter.com": "x.com",
    "www.x.com": "x.com",
    "m.youtube.com": "youtube.com",
    "www.youtube.com": "youtube.com",
    "youtu.be": "youtube.com",
    "www.youtu.be": "youtube.com",
}


def canonicalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.

    IMPORTANT: Only lowercase scheme + host, preserve path/query casing
    (case-sensitive URLs exist, e.g., GitHub paths, video IDs).
    """
    url = url.strip()
    p = urlparse(url)

    # Normalize scheme + host only (preserve path/query case)
    scheme = (p.scheme or "https").lower()
    original_host = (p.netloc or "").lower()

    # Handle youtu.be -> youtube.com/watch?v=X (before alias normalization)
    if original_host in ("youtu.be", "www.youtu.be"):
        video_id = p.path.strip("/")
        return f"https://youtube.com/watch?v={video_id}"

    # Apply domain aliases
    host = DOMAIN_ALIASES.get(original_host, original_host)

    # Handle youtube.com/shorts/X -> youtube.com/watch?v=X
    if host == "youtube.com" and p.path.startswith("/shorts/"):
        video_id = p.path.replace("/shorts/", "").strip("/")
        return f"https://youtube.com/watch?v={video_id}"

    # Strip tracking params (case-insensitive key match)
    query = parse_qs(p.query, keep_blank_values=True)
    query = {k: v for k, v in query.items() if k.lower() not in STRIP_PARAMS}
    new_query = urlencode(query, doseq=True) if query else ""

    # Normalize path (remove trailing slash except for root)
    path = p.path.rstrip("/") or "/"

    return urlunparse((scheme, host, path, "", new_query, ""))


def extract_twitter_status_id(url: str) -> str | None:
    """Extract the status ID from a Twitter/X URL."""
    p = urlparse(url)
    host = p.netloc.lower()

    if host not in ("twitter.com", "x.com", "www.twitter.com", "www.x.com", "mobile.twitter.com"):
        return None

    parts = p.path.strip("/").split("/")
    if len(parts) >= 3 and parts[1] == "status":
        return parts[2].split("?")[0]

    return None


def extract_youtube_video_id(url: str) -> str | None:
    """Extract the video ID from a YouTube URL."""
    p = urlparse(url)
    host = p.netloc.lower()

    # youtu.be/VIDEO_ID
    if host in ("youtu.be", "www.youtu.be"):
        return p.path.strip("/").split("?")[0]

    if host not in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        return None

    # youtube.com/watch?v=VIDEO_ID
    if p.path == "/watch":
        query = parse_qs(p.query)
        if "v" in query:
            return query["v"][0]

    # youtube.com/shorts/VIDEO_ID
    if p.path.startswith("/shorts/"):
        return p.path.replace("/shorts/", "").strip("/")

    # youtube.com/embed/VIDEO_ID
    if p.path.startswith("/embed/"):
        return p.path.replace("/embed/", "").strip("/")

    return None
