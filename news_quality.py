"""Pure source and News-quality helpers for GamerQuest.

This module deliberately contains no API clients, environment-secret access,
filesystem state, or publishing side effects.  Keeping these rules separate
makes the News pipeline easier to test and safer to maintain.
"""

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# =========================================================
# OFFICIAL SOURCE DOMAINS
# =========================================================

OFFICIAL_DOMAIN_KEYWORDS = [
    "playstation.com",
    "xbox.com",
    "nintendo.com",
    "steampowered.com",
    "steamcommunity.com",
    "ea.com",
    "ubisoft.com",
    "rockstargames.com",
    "2k.com",
    "epicgames.com",
    "activision.com",
    "blizzard.com",
    "bethesda.net",
    "square-enix.com",
    "bandainamcoent.com",
    "capcom.com",
    "sega.com",
    "konami.com",
    "riotgames.com",
    "playvalorant.com",
    "leagueoflegends.com",
    "jagex.com",
    "warframe.com",
    "digitalextremes.com",
    "cdprojektred.com",
    "cyberpunk.net",
    "thewitcher.com",
]

# Established gaming publications. These are acceptable secondary
# sources when an official source for the same story is not available.
TRUSTED_MEDIA_DOMAINS = [
    "ign.com",
    "gamespot.com",
    "eurogamer.net",
    "polygon.com",
    "pcgamer.com",
    "gamesradar.com",
    "videogameschronicle.com",
    "vgc.com",
    "gematsu.com",
    "rockpapershotgun.com",
    "gameinformer.com",
    "pushsquare.com",
    "nintendolife.com",
    "purexbox.com",
    "destructoid.com",
    "theverge.com",
    "arstechnica.com",
]


# =========================================================
# HELPERS
# =========================================================

def get_domain(url):
    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .replace("www.", "")
        )
    except Exception:
        return ""


def looks_official(url):
    domain = get_domain(url)

    return any(
        keyword in domain
        for keyword in OFFICIAL_DOMAIN_KEYWORDS
    )


def looks_trusted_media(url):
    domain = get_domain(url)

    return any(
        trusted in domain
        for trusted in TRUSTED_MEDIA_DOMAINS
    )


def source_tier(url):
    """
    1 = official / primary source
    2 = established gaming or technology publication
    3 = other web source
    """
    if looks_official(url):
        return 1
    if looks_trusted_media(url):
        return 2
    return 3


def result_content_length(result):
    content = (
        result.get("raw_content", "")
        or result.get("content", "")
        or ""
    )
    return len(content.strip())


def slugify(text):
    text = text.lower()

    replacements = {
        "à": "a",
        "â": "a",
        "ä": "a",
        "á": "a",
        "ç": "c",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ÿ": "y",
        "œ": "oe",
    }

    for original, replacement in replacements.items():
        text = text.replace(
            original,
            replacement
        )

    text = re.sub(
        r"[^a-z0-9\s-]",
        "",
        text
    )

    text = re.sub(
        r"[\s_-]+",
        "-",
        text
    )

    return text.strip("-")[:90]


def strip_code_fences(text):
    text = text.strip()

    text = re.sub(
        r"^```(?:html|markdown|md)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    return text.strip()


def sanitize_article_html(content):
    """Normalize AI-generated article HTML before any publication path.

    The model is instructed to return HTML, but can occasionally leak Markdown
    bold markers or malformed nesting. Removing Markdown delimiters and
    reparsing the fragment with BeautifulSoup prevents those artifacts from
    reaching WordPress while preserving the article's text and links.
    """
    content = strip_code_fences(content)
    content = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        content,
        flags=re.DOTALL,
    )
    content = content.replace("**", "")
    soup = BeautifulSoup(content, "html.parser")
    return "".join(str(node) for node in soup.contents).strip()


def normalize_words(text):
    words = re.findall(
        r"[a-zA-Z0-9À-ÿ]+",
        text.lower(),
    )

    stopwords = {
        "the",
        "and",
        "for",
        "from",
        "with",
        "this",
        "that",
        "into",
        "new",
        "news",
        "game",
        "games",
        "gaming",
        "video",
        "update",
        "reveals",
        "revealed",
        "announces",
        "announced",
    }

    return [
        word
        for word in words
        if len(word) >= 3
        and word not in stopwords
    ]


NEWS_TOPIC_GENERIC_TERMS = {
    "annonce", "annoncee", "annoncees", "annonces", "confirme",
    "confirmee", "confirmation", "date", "dates", "sortie", "sortira",
    "plateforme", "plateformes", "prix", "dlc", "trailer", "gameplay",
    "mise", "jour", "disponible", "edition", "complete", "remastered",
    "pour", "avec", "dans", "sur", "une", "des", "les", "aux", "son",
    "ses", "2025", "2026", "2027", "2028", "2029", "2030",
}

NEWS_STORY_ANGLES = {
    "release": {"date", "dates", "sortie", "sortira", "disponible"},
    "dlc": {"dlc", "extension", "contenu", "pack"},
    "update": {"update", "patch", "version", "mise"},
    "gameplay": {"gameplay", "mecanique", "mecaniques"},
    "platform": {"plateforme", "plateformes", "ps5", "xbox", "switch", "pc"},
}


def normalized_news_terms(text):
    """Return stable, accent-free terms used by News quality guards."""
    normalized = slugify(str(text or "")).replace("-vii-", "-7-")
    normalized = normalized.replace("-viii-", "-8-").replace("-ix-", "-9-")
    return set(normalized.split("-")) - {"", "the", "de", "du", "et", "en", "a"}


def news_topic_terms(article):
    searchable = " ".join([
        str(article.get("title", "")),
        str(article.get("slug", "")),
        str(article.get("seo", {}).get("primary_keyword", "")),
        " ".join(str(tag) for tag in article.get("tags", []) if tag),
    ])
    return normalized_news_terms(searchable) - NEWS_TOPIC_GENERIC_TERMS


def news_story_angles(article):
    terms = normalized_news_terms(
        f"{article.get('title', '')} {article.get('slug', '')}"
    )
    return {
        angle
        for angle, markers in NEWS_STORY_ANGLES.items()
        if terms & markers
    }


def same_news_subject(first, second):
    first_terms = news_topic_terms(first)
    second_terms = news_topic_terms(second)
    overlap = first_terms & second_terms
    shortest = min(len(first_terms), len(second_terms))
    return bool(
        shortest
        and len(overlap) >= 3
        and len(overlap) / shortest >= 0.4
    )


def is_duplicate_news_topic(candidate, existing_articles):
    """Detect the same story even when it arrives from another URL."""
    candidate_slug = slugify(candidate.get("slug", ""))
    candidate_angles = news_story_angles(candidate)

    for existing in existing_articles:
        if candidate_slug and candidate_slug == slugify(existing.get("slug", "")):
            return True
        if not same_news_subject(candidate, existing):
            continue
        existing_angles = news_story_angles(existing)
        if candidate_angles and existing_angles and not (candidate_angles & existing_angles):
            continue
        return True

    return False


def source_image_matches_article(article_title, story, image_url):
    """Reject generic showcase artwork for a game-specific News article."""
    source_context = " ".join([
        str(story.get("title", "")),
        str(story.get("url", "")),
    ]).lower()
    roundup_markers = (
        "state of play", "showcase", "roundup", "toutes les annonces",
        "all announcements", "gamescom", "direct recap",
    )
    if not any(marker in source_context for marker in roundup_markers):
        return True

    article_terms = normalized_news_terms(article_title) - NEWS_TOPIC_GENERIC_TERMS
    image_terms = normalized_news_terms(image_url)
    return len(article_terms & image_terms) >= 2


def release_years(article):
    text = f"{article.get('title', '')} {article.get('content', '')}"
    return set(re.findall(r"\b20(?:2[5-9]|3[0-5])\b", text))


def claimed_platforms(article):
    text = slugify(f"{article.get('title', '')} {article.get('content', '')}")
    platforms = set()
    aliases = {
        "ps5": ("ps5", "playstation-5"),
        "xbox": ("xbox-series", "xbox"),
        "switch": ("switch-2", "nintendo-switch", "switch"),
        "pc": ("-pc-",),
    }
    padded = f"-{text}-"
    for platform, markers in aliases.items():
        if any(marker in padded for marker in markers):
            platforms.add(platform)
    return platforms


def is_exclusive_claim(article):
    text = slugify(article.get("content", ""))
    return "exclusivite" in text or "exclusif" in text or "exclusive" in text


def has_conflicting_news_claims(candidate, existing_articles):
    """Block incompatible release-year or exclusivity claims for one topic."""
    for existing in existing_articles:
        if not same_news_subject(candidate, existing):
            continue

        candidate_years = release_years(candidate)
        existing_years = release_years(existing)
        if candidate_years and existing_years and candidate_years.isdisjoint(existing_years):
            return True

        candidate_platforms = claimed_platforms(candidate)
        existing_platforms = claimed_platforms(existing)
        if (
            candidate_platforms
            and existing_platforms
            and candidate_platforms.isdisjoint(existing_platforms)
            and (is_exclusive_claim(candidate) or is_exclusive_claim(existing))
        ):
            return True

    return False
