"""Domain and content type taxonomy definitions."""

import re
from urllib.parse import urlparse
from typing import Optional


# ============================================
# Domain Taxonomy (Axis 1)
# ============================================

DOMAIN_DEFINITIONS = {
    "ai-ml": {
        "name": "AI & Machine Learning",
        "keywords": [
            "llm", "gpt", "transformer", "diffusion", "embedding", "reinforcement learning",
            "neural network", "deep learning", "machine learning", "nlp", "computer vision",
            "multimodal", "alignment", "rlhf", "quantization", "fine-tuning", "finetuning",
            "prompt engineering", "agent", "rag", "retrieval augmented", "langchain",
            "huggingface", "openai", "anthropic", "claude", "gemini", "mistral", "llama",
            "stable diffusion", "midjourney", "attention mechanism", "tokenizer", "lora",
            "inference", "training", "model", "ai safety", "benchmark",
        ],
        "url_patterns": ["huggingface.co", "openai.com", "arxiv.org"],
    },
    "software-eng": {
        "name": "Software Engineering",
        "keywords": [
            "code", "framework", "docker", "react", "kubernetes", "devops", "compiler",
            "microservice", "graphql", "serverless", "api", "sdk", "database", "sql",
            "postgresql", "redis", "rust", "python", "typescript", "javascript", "golang",
            "architecture", "design pattern", "testing", "ci/cd", "deployment", "git",
            "open source", "cli", "terminal", "vim", "neovim", "linux",
        ],
        "url_patterns": ["github.com", "gitlab.com", "stackoverflow.com"],
    },
    "finance-quant": {
        "name": "Finance & Quant",
        "keywords": [
            "trading", "portfolio", "options", "backtest", "volatility", "sharpe",
            "momentum", "hedge fund", "s&p 500", "stock", "equity", "market",
            "risk management", "alpha", "beta", "derivatives", "fixed income",
            "stochastic", "monte carlo", "black-scholes", "market making",
            "quantitative", "factor model", "arbitrage", "yield", "bond",
            "hft", "high frequency", "order book", "latency", "exchange",
        ],
        "url_patterns": ["ssrn.com", "bloomberg.com", "ft.com"],
    },
    "research-academic": {
        "name": "Research & Academic",
        "keywords": [
            "paper", "methodology", "peer review", "abstract", "arxiv", "preprint",
            "sota", "state of the art", "experiment", "hypothesis", "dataset",
            "evaluation", "citation", "journal", "conference", "survey", "thesis",
        ],
        "url_patterns": ["arxiv.org", "ssrn.com", "doi.org", "nature.com", "scholar.google.com"],
    },
    "math-stats": {
        "name": "Math & Statistics",
        "keywords": [
            "bayesian", "probability", "optimization", "stochastic", "linear algebra",
            "entropy", "estimator", "covariance", "regression", "statistical",
            "distribution", "theorem", "proof", "calculus", "topology",
            "combinatorics", "graph theory", "markov", "sampling",
        ],
        "url_patterns": [],
    },
    "career": {
        "name": "Career & Professional",
        "keywords": [
            "interview", "hiring", "leetcode", "system design", "compensation",
            "remote work", "resume", "job search", "salary", "negotiation",
            "career advice", "promotion", "leadership", "management",
        ],
        "url_patterns": ["linkedin.com", "levels.fyi", "glassdoor.com"],
    },
    "sports-football": {
        "name": "Sports & Football",
        "keywords": [
            "premier league", "champions league", "chelsea", "arsenal", "liverpool",
            "manchester united", "manchester city", "tottenham", "spurs", "transfer",
            "goal", "striker", "midfielder", "defender", "goalkeeper", "pitch invasion",
            "fpl", "fantasy premier league", "gameweek", "clean sheet", "assist",
            "la liga", "serie a", "bundesliga", "ligue 1", "world cup", "euros",
            "stamford bridge", "anfield", "old trafford", "etihad", "emirates",
            "football", "soccer", "match", "fixture", "penalty", "offside", "var",
            "manager", "coach", "formation", "tactics", "championship", "promotion",
            "relegation", "playoff", "league cup", "fa cup", "europa league",
            "ballon d'or", "golden boot", "hat trick", "free kick", "corner",
            "nba", "nfl", "ufc", "boxing", "tennis", "f1", "formula 1",
            "cricket", "rugby", "mma", "athlete", "sports",
        ],
        "url_patterns": ["espn.com", "bbc.co.uk/sport", "skysports.com", "theathletic.com"],
    },
    "memes-entertainment": {
        "name": "Memes & Entertainment",
        "keywords": [
            "meme", "shitpost", "lmao", "lol", "bruh", "no context", "viral",
            "crying", "dead", "hilarious", "comedy", "skit", "prank",
            "wholesome", "cursed", "based", "ratio", "cope", "seethe",
            "movie", "film", "tv show", "series", "anime", "manga",
            "music", "album", "song", "concert", "boiler room", "dj",
            "netflix", "hbo", "disney", "streaming", "trailer",
            "celebrity", "pop culture", "nostalgia", "throwback",
        ],
        "url_patterns": ["imdb.com", "rottentomatoes.com", "letterboxd.com"],
    },
    "health-biohacking": {
        "name": "Health & Biohacking",
        "keywords": [
            "supplement", "creatine", "modafinil", "armodafinil", "bromantane",
            "nootropic", "sleep", "circadian", "melatonin", "caffeine",
            "testosterone", "hormone", "cortisol", "dopamine", "serotonin",
            "longevity", "anti-aging", "biohacking", "blueprint", "bryan johnson",
            "fasting", "intermittent fasting", "autophagy", "ketosis", "keto",
            "protein", "collagen", "vitamin", "magnesium", "zinc", "thiamine",
            "exercise", "workout", "strength training", "hypertrophy", "cardio",
            "recovery", "hrv", "heart rate", "vo2 max", "zone 2",
            "skincare", "retinol", "sunscreen", "hair loss", "minoxidil",
            "gut health", "microbiome", "probiotic", "fiber",
            "posture", "mobility", "stretching", "foam rolling",
            "meditation", "breathwork", "cold plunge", "sauna", "red light",
            "blood work", "biomarker", "glucose", "insulin", "cholesterol",
        ],
        "url_patterns": ["pubmed.ncbi.nlm.nih.gov", "examine.com", "hubermanlab.com"],
    },
    "self-improvement": {
        "name": "Self-Improvement & Wisdom",
        "keywords": [
            "motivation", "discipline", "mindset", "stoic", "stoicism",
            "philosophy", "nietzsche", "marcus aurelius", "seneca", "epictetus",
            "productivity", "habits", "routine", "morning routine", "journaling",
            "focus", "deep work", "flow state", "attention span", "doomscrolling",
            "reading", "books", "book recommendation", "must read", "reading list",
            "wisdom", "life advice", "regret", "purpose", "meaning",
            "confidence", "self-awareness", "emotional intelligence",
            "communication", "public speaking", "writing", "storytelling",
            "networking", "relationships", "social skills", "charisma",
            "mental health", "anxiety", "depression", "therapy", "adhd",
            "addiction", "dopamine detox", "brain rot", "screen time",
        ],
        "url_patterns": [],
    },
    "lifestyle-design": {
        "name": "Lifestyle & Design",
        "keywords": [
            "interior design", "architecture", "furniture", "minimalist",
            "aesthetic", "decor", "home office", "desk setup", "cable management",
            "photography", "camera", "film", "35mm", "lens", "portrait",
            "fashion", "streetwear", "outfit", "wardrobe", "carhartt",
            "travel", "destination", "hotel", "airbnb", "flight", "backpacking",
            "food", "recipe", "cooking", "restaurant", "coffee", "cocktail",
            "art", "painting", "sculpture", "gallery", "museum",
            "wallpaper", "typography", "font", "graphic design", "ui design",
        ],
        "url_patterns": ["pinterest.com", "dribbble.com", "behance.net", "unsplash.com"],
    },
    "crypto-web3": {
        "name": "Crypto & Web3",
        "keywords": [
            "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
            "memecoin", "airdrop", "whale", "on-chain", "onchain",
            "defi", "dex", "nft", "dao", "web3", "blockchain",
            "polymarket", "prediction market", "betting",
            "binance", "coinbase", "mexc", "uniswap", "jupiter",
            "wallet", "metamask", "phantom", "ledger",
            "token", "staking", "yield farming", "liquidity",
            "rug pull", "insider trading", "pump", "dump",
            "pelosi", "congress trading", "insider",
        ],
        "url_patterns": ["coingecko.com", "dexscreener.com", "polymarket.com", "etherscan.io"],
    },
    "politics-news": {
        "name": "Politics & News",
        "keywords": [
            "trump", "biden", "congress", "senate", "white house",
            "election", "vote", "democrat", "republican", "policy",
            "geopolitics", "sanctions", "war", "military", "nato",
            "china", "russia", "ukraine", "middle east", "iran",
            "regulation", "law", "legislation", "supreme court", "fda",
            "immigration", "border", "tariff", "trade war",
            "protest", "activism", "civil rights", "free speech",
            "epstein", "scandal", "corruption", "whistleblower",
            "breaking news", "bbc", "cnn", "reuters", "associated press",
            "economy", "inflation", "recession", "unemployment", "gdp",
        ],
        "url_patterns": ["bbc.com", "reuters.com", "apnews.com", "politico.com", "nytimes.com"],
    },
    "gaming": {
        "name": "Gaming",
        "keywords": [
            "league of legends", "lol", "valorant", "fortnite", "minecraft",
            "call of duty", "cod", "apex legends", "overwatch", "dota",
            "elo", "ranked", "build", "item build", "runes", "champion",
            "steam", "epic games", "playstation", "xbox", "nintendo", "switch",
            "fps", "mmo", "rpg", "moba", "battle royale",
            "esports", "tournament", "pro player", "streamer",
            "gaming setup", "gpu", "rtx", "fps counter", "latency",
            "speedrun", "glitch", "mod", "emulator", "rom",
            "gta", "elden ring", "zelda", "pokemon", "fifa",
        ],
        "url_patterns": ["store.steampowered.com", "op.gg", "u.gg", "twitch.tv"],
    },
    "tech-hardware": {
        "name": "Tech & Hardware",
        "keywords": [
            "self-hosting", "self hosted", "homelab", "home server",
            "vps", "hetzner", "digitalocean", "ovh", "linode", "vultr",
            "raspberry pi", "arduino", "esp32", "iot",
            "nas", "hard drive", "ssd", "nvme", "optane", "storage",
            "kvm switch", "monitor", "keyboard", "mechanical keyboard",
            "usb-c", "thunderbolt", "hdmi", "displayport",
            "router", "networking", "dns", "nextdns", "pihole", "wireguard",
            "vpn", "tailscale", "cloudflare", "nginx", "caddy",
            "3d printing", "cnc", "laser cutter", "maker",
            "mac mini", "macbook", "thinkpad", "framework laptop",
            "home automation", "smart home", "zigbee", "matter",
        ],
        "url_patterns": ["hetzner.com", "selfhosted.show", "servethehome.com"],
    },
    "courses-learning": {
        "name": "Courses & Learning",
        "keywords": [
            "coursera", "udemy", "edx", "khan academy", "udacity",
            "codecademy", "brilliant", "mit ocw", "stanford online",
            "freecodecamp", "skillshare", "pluralsight",
            "linkedin learning", "masterclass", "datacamp", "fast.ai",
            "full course", "crash course", "bootcamp", "mooc", "online course",
            "free course", "paid course", "certification", "certificate",
            "tutorial", "walkthrough", "lecture", "lecture series",
            "complete guide", "full guide", "beginner to advanced",
            "step by step guide", "roadmap", "learning path", "curriculum",
            "syllabus", "textbook", "study guide", "cheat sheet",
            "university", "uni course", "degree", "phd", "masters",
            "undergrad", "semester", "professor", "class notes",
            "youtube course", "youtube tutorial", "youtube lecture",
            "playlist", "series",
        ],
        "url_patterns": [
            "coursera.org", "udemy.com", "edx.org", "khanacademy.org",
            "brilliant.org", "freecodecamp.org", "codecademy.com",
            "skillshare.com", "pluralsight.com", "datacamp.com",
            "fast.ai", "kaggle.com/learn",
        ],
    },
}


# ============================================
# Content Type Detection (Axis 2)
# ============================================

CONTENT_TYPE_URL_RULES = {
    "paper": ["arxiv.org", "ssrn.com", "doi.org", "semanticscholar.org", "biorxiv.org", "medrxiv.org"],
    "repo": ["github.com", "gitlab.com", "bitbucket.org"],
    "video": ["youtube.com", "youtu.be", "vimeo.com", "m.youtube.com"],
    "article": [
        "medium.com", "substack.com", "dev.to", "techcrunch.com",
        "hackernews.com", "blog.", "news.", "towardsdatascience.com",
    ],
    "tool": ["producthunt.com", "alternativeto.net"],
}

CONTENT_TYPE_TEXT_RULES = {
    "thread": {"min_length": 800},
    "insight": {"max_length": 280, "no_urls": True},
    "tweet": {"fallback": True},
}


# ============================================
# Universal Quality Dimensions (0-5 scale)
# ============================================
# Reusable across vault — ideas, notes, research, any content.
# ICC=0.853 on 0-5 scale (arxiv 2601.03444, Jan 2026).

QUALITY_DIMENSIONS = {
    "originality": {
        "weight": 0.25,
        "scale": "0-5",
        "description": "How new is this? Novel combination, genuine gap, or incremental?",
    },
    "quality": {
        "weight": 0.25,
        "scale": "0-5",
        "description": "How well-executed? Rigorous, clear, evidence-backed?",
    },
    "utility": {
        "weight": 0.20,
        "scale": "0-5",
        "description": "How useful? Actionable, solves a real problem?",
    },
    "reach": {
        "weight": 0.15,
        "scale": "0-5",
        "description": "Could this be shared? Publication, open-source, blog post?",
    },
    "strategic_value": {
        "weight": 0.15,
        "scale": "0-5",
        "description": "Does this advance goals? Career, research agenda, portfolio?",
    },
}

QUALITY_DISTRIBUTION_CHECK = {
    "mean_range": [2.0, 3.5],
    "min_std": 0.75,
    "description": "Scores must approximate normal distribution. Re-score if bunched.",
}


def compute_quality_composite(scores: dict[str, float]) -> float:
    """Compute weighted quality composite from dimension scores (0-5 scale)."""
    total = 0.0
    weight_sum = 0.0
    for dim, config in QUALITY_DIMENSIONS.items():
        if dim in scores and scores[dim] is not None:
            total += scores[dim] * config["weight"]
            weight_sum += config["weight"]
    return total / weight_sum if weight_sum > 0 else 0.0


def detect_domain_from_text(text: str, url: Optional[str] = None) -> Optional[str]:
    """Detect domain from text content using keyword matching.

    Returns the domain slug with highest match count, or None.
    """
    if not text:
        return None

    text_lower = text.lower()
    scores: dict[str, int] = {}

    for domain_slug, definition in DOMAIN_DEFINITIONS.items():
        score = 0
        for kw in definition["keywords"]:
            if kw.lower() in text_lower:
                score += 1
        if score > 0:
            scores[domain_slug] = score

    # Check URL patterns
    if url:
        try:
            parsed = urlparse(url)
            url_domain = parsed.netloc.lower().replace("www.", "")
            for domain_slug, definition in DOMAIN_DEFINITIONS.items():
                for pattern in definition.get("url_patterns", []):
                    if pattern in url_domain:
                        scores[domain_slug] = scores.get(domain_slug, 0) + 3
        except Exception:
            pass

    if not scores:
        return None

    return max(scores, key=scores.get)


def detect_content_type_from_url(url: str) -> Optional[str]:
    """Detect content type from URL domain."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
    except Exception:
        return None

    for content_type, domains in CONTENT_TYPE_URL_RULES.items():
        for pattern in domains:
            if pattern in domain:
                return content_type

    return None


def detect_content_type_from_text(text: str, has_urls: bool = True) -> str:
    """Detect content type from text characteristics."""
    text_len = len(text) if text else 0

    if text_len > 800:
        return "thread"
    if text_len <= 280 and not has_urls:
        return "insight"
    return "tweet"
