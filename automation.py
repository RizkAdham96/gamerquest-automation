import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, NavigableString
from groq import Groq, RateLimitError
from groq_budget import GroqBudgetExhausted, consume_run_budget
from news_image_generator import generate_news_image


# =========================================================
# CONFIGURATION
# =========================================================

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]

# WordPress connection (stored as GitHub Actions secrets)
WP_URL = os.environ.get("WP_URL", "").rstrip("/")
WP_USERNAME = os.environ.get("WP_USERNAME", "")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")

DRAFTS_FOLDER = Path("drafts")
REJECTED_FOLDER = Path("rejected")
STATE_FOLDER = Path("state")

TAVILY_STATE_FILE = STATE_FOLDER / "tavily_usage.json"
NEWS_TOPIC_HISTORY_FILE = STATE_FOLDER / "news_topic_history.json"
MAX_NEWS_TOPIC_HISTORY = 1000

NEWS_FEED_FILE = Path("gamerquest-news-feed.json")
MAX_NEWS_FEED_ARTICLES = 50
NEWS_IMAGES_FOLDER = Path("generated_news_images")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

TAVILY_MONTHLY_SAFETY_LIMIT = 900

# The production workflow runs every 4 hours.
# Maximum theoretical usage:
# 6 runs/day × 30 days × 2 searches = ~360 searches/month.
# This stays safely below the 900/month limit and leaves retry headroom.
MAX_TAVILY_SEARCHES_PER_RUN = 2

SEARCH_QUERIES = [
    (
        "latest gaming official announcement release date patch guide "
        "comment résoudre problème performance crossplay sauvegarde "
        "DLC gratuit PlayStation Xbox Nintendo Switch 2 PC"
    ),
    (
        "latest game guide comment débloquer trouver obtenir problème "
        "erreur patch performance PS5 Xbox Switch 2 PC Steam Game Pass"
    ),
]

MAX_RESULTS = 20

# Do not let one bad SEO pick kill an entire scheduled run.
# The editor can retry a handful of different candidates while keeping
# Groq/Tavily usage bounded and predictable.
MAX_NEWS_CANDIDATE_ATTEMPTS = 12

# Publish several independent, quality-approved stories from the same
# discovery pool. This increases output without increasing Tavily searches.
MAX_NEWS_ARTICLES_PER_RUN = 3

MIN_SOURCE_TEXT_LENGTH = 250

# Keep Groq requests compact enough for the free-tier TPM budget.
# These are character caps, not token counts. They preserve the useful
# source facts while avoiding repeated full-page payloads.
MAX_SOURCE_TEXT_LENGTH = 10000
MAX_GENERATION_SOURCE_LENGTH = 6500
MAX_VERIFICATION_SOURCE_LENGTH = 3200
MAX_OFFICIAL_SOURCE_LENGTH = 2600

GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_GENERATION_MODEL = "openai/gpt-oss-120b"
GROQ_VERIFICATION_MODEL = "openai/gpt-oss-20b"

# Keep each request small enough that the two production AI calls
# (draft + factual correction) can fit inside Groq's free-tier TPM window.
GROQ_DEFAULT_MAX_TOKENS = 1600
GROQ_GENERATION_MAX_TOKENS = 1700
GROQ_VERIFICATION_MAX_TOKENS = 1300
GROQ_BETWEEN_ARTICLES_WAIT_SECONDS = 25

# Retry settings for 429 errors.
GROQ_MAX_RETRIES = 3
GROQ_DEFAULT_WAIT_SECONDS = 10
GROQ_MAX_WAIT_SECONDS = 60

# Leave enough time for state persistence and the WordPress wake step before
# the GitHub job's hard 30-minute timeout.
MAX_NEWS_RUN_SECONDS = 22 * 60
MIN_SECONDS_TO_START_AI_CANDIDATE = 180


# =========================================================
# GROQ CLIENT
# =========================================================

# Disable SDK-level retries here because we handle
# rate-limit waiting ourselves below.
GROQ_CLIENT = Groq(
    api_key=GROQ_API_KEY,
    max_retries=0,
)


# =========================================================
# SAFE GROQ CALL
# =========================================================

class GroqRunDeferred(RuntimeError):
    """Stop this scheduled run when the provider itself cannot recover soon."""


class GroqBudgetDeferred(RuntimeError):
    """Planned stop before GamerQuest's own shared Groq ceiling is reached."""


def groq_chat(
    messages,
    temperature=0.1,
    max_tokens=GROQ_DEFAULT_MAX_TOKENS,
    model=GROQ_MODEL,
):
    """
    Make a Groq request.

    If Groq returns HTTP 429:
    - read retry-after when available
    - wait
    - retry automatically

    This prevents GitHub Actions from failing
    just because the token-per-minute limit
    was temporarily reached.
    """

    try:
        consume_run_budget(
            messages,
            max_tokens,
            lane="news",
            operation=f"news:{model}",
        )
    except GroqBudgetExhausted as error:
        raise GroqBudgetDeferred(str(error)) from error

    for attempt in range(
        1,
        GROQ_MAX_RETRIES + 1
    ):
        try:
            response = (
                GROQ_CLIENT
                .chat
                .completions
                .create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )

            return (
                response
                .choices[0]
                .message
                .content
            )

        except RateLimitError as error:
            error_text = str(error).lower()

            # A daily token cap cannot recover within this scheduled run.
            # Do not sleep for tens of minutes and let GitHub kill the job.
            if "tokens per day" in error_text or "tpd" in error_text:
                raise GroqRunDeferred(
                    "Groq daily token budget is exhausted; defer News generation to the next run."
                ) from error

            retry_after = None

            try:
                retry_after = (
                    error
                    .response
                    .headers
                    .get("retry-after")
                )
            except Exception:
                retry_after = None

            try:
                wait_seconds = float(
                    retry_after
                )
            except Exception:
                wait_seconds = (
                    GROQ_DEFAULT_WAIT_SECONDS
                    * attempt
                )

            # Give Groq a small extra buffer, but never let one 429 consume
            # several minutes of the scheduled run.
            wait_seconds = min(
                wait_seconds + 2,
                GROQ_MAX_WAIT_SECONDS,
            )

            print("")
            print(
                "==================================="
            )
            print(
                "GROQ RATE LIMIT REACHED"
            )
            print(
                "==================================="
            )

            print(
                f"Attempt "
                f"{attempt}/{GROQ_MAX_RETRIES}"
            )

            print(
                f"Waiting "
                f"{wait_seconds:.1f} seconds..."
            )

            if attempt >= GROQ_MAX_RETRIES:
                raise GroqRunDeferred(
                    "Groq remained rate-limited after bounded retries."
                ) from error

            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        "Groq request failed after retries."
    )


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


def discovery_story_is_duplicate(story, existing_articles=None):
    """Reject known News topics before spending any Groq tokens."""
    if not isinstance(story, dict):
        return False

    title = str(story.get("title", "")).strip()
    if not title:
        return False

    candidate = {
        "title": title,
        "slug": slugify(title),
        "tags": [],
        "seo": {
            "primary_keyword": title,
        },
    }

    if existing_articles is None:
        existing_articles = combined_news_quality_history()

    return is_duplicate_news_topic(
        candidate,
        existing_articles,
    )


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




# =========================================================
# NEWS FEATURED IMAGES
# =========================================================

def get_absolute_image_url(base_url, image_url):
    """
    Convert relative image URLs found in page metadata to absolute URLs.
    """

    if not image_url:
        return ""

    image_url = str(image_url).strip()

    if image_url.startswith("http://") or image_url.startswith("https://"):
        return image_url

    try:
        from urllib.parse import urljoin
        return urljoin(base_url, image_url)
    except Exception:
        return ""


def image_url_looks_bad(image_url):
    """
    Reject common logos/icons/avatars/sprites before using
    an image as the article artwork.
    """

    if not image_url:
        return True

    lowered = str(
        image_url
    ).lower()

    bad_terms = [
        "logo",
        "favicon",
        "icon",
        "avatar",
        "sprite",
        "badge",
        "emoji",
        "author",
        "profile",
        "placeholder",
        "default-image",
        "default_image",
        "site-logo",
        "site_logo",
        "brandmark",
        "branding",
    ]

    return any(
        term in lowered
        for term in bad_terms
    )


def validate_remote_image_candidate(
    image_url,
):
    """
    Reject obvious non-images and extremely tiny assets.
    """

    if (
        not image_url
        or image_url_looks_bad(
            image_url
        )
    ):
        return False

    try:
        response = requests.get(
            image_url,
            timeout=15,
            stream=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; GamerQuestFR/1.0)"
                ),
                "Accept": "image/*",
            },
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        if (
            content_type
            and "image" not in content_type
        ):
            return False

        content_length = (
            response.headers.get(
                "Content-Length"
            )
        )

        if content_length:
            try:
                if int(
                    content_length
                ) < 15000:
                    return False
            except Exception:
                pass

        return True

    except Exception:
        return False


def extract_source_image_url(story, article_title=""):
    """
    Find the best contextual image for the selected story.

    Priority:
    1. OpenGraph image
    2. Twitter image
    3. Tavily/story image metadata
    4. Large page image
    5. None -> branded fallback
    """

    source_url = (
        story.get("url", "")
        .strip()
    )

    # First inspect page metadata because it normally describes
    # the article's actual social/featured image.
    if source_url:
        try:
            print("")
            print(
                "Looking for contextual article artwork..."
            )

            response = requests.get(
                source_url,
                timeout=25,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(compatible; GamerQuestFR/1.0)"
                    ),
                    "Accept": (
                        "text/html,"
                        "application/xhtml+xml"
                    ),
                },
                allow_redirects=True,
            )

            response.raise_for_status()

            soup = BeautifulSoup(
                response.text,
                "html.parser",
            )

            meta_candidates = [
                (
                    "property",
                    "og:image",
                ),
                (
                    "property",
                    "og:image:secure_url",
                ),
                (
                    "name",
                    "twitter:image",
                ),
                (
                    "name",
                    "twitter:image:src",
                ),
            ]

            for attribute, value in meta_candidates:
                tag = soup.find(
                    "meta",
                    attrs={
                        attribute: value
                    },
                )

                if not tag:
                    continue

                candidate = (
                    tag.get(
                        "content",
                        "",
                    )
                    .strip()
                )

                candidate = get_absolute_image_url(
                    source_url,
                    candidate,
                )

                if (
                    candidate
                    and validate_remote_image_candidate(
                        candidate
                    )
                    and source_image_matches_article(
                        article_title,
                        story,
                        candidate,
                    )
                ):
                    print(
                        f"Contextual image found from "
                        f"{value}: {candidate}"
                    )
                    return candidate

        except Exception as error:
            print(
                f"Could not inspect page metadata: "
                f"{error}"
            )

    # Then try image metadata already present on the story object.
    direct_candidates = [
        story.get("image"),
        story.get("image_url"),
        story.get("thumbnail"),
        story.get("og_image"),
    ]

    images_field = story.get(
        "images"
    )

    if isinstance(
        images_field,
        list,
    ):
        direct_candidates.extend(
            images_field
        )

    for candidate in direct_candidates:
        if isinstance(
            candidate,
            dict,
        ):
            candidate = (
                candidate.get("url")
                or candidate.get("src")
                or ""
            )

        candidate = get_absolute_image_url(
            source_url,
            candidate,
        )

        if (
            candidate
            and validate_remote_image_candidate(
                candidate
            )
            and source_image_matches_article(
                article_title,
                story,
                candidate,
            )
        ):
            print(
                "Contextual image found in "
                f"story metadata: {candidate}"
            )
            return candidate

    # Last-resort scan through page images.
    if source_url:
        try:
            response = requests.get(
                source_url,
                timeout=25,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(compatible; GamerQuestFR/1.0)"
                    ),
                    "Accept": (
                        "text/html,"
                        "application/xhtml+xml"
                    ),
                },
                allow_redirects=True,
            )

            response.raise_for_status()

            soup = BeautifulSoup(
                response.text,
                "html.parser",
            )

            for image in soup.find_all(
                "img",
                limit=60,
            ):
                candidate = (
                    image.get("src")
                    or image.get("data-src")
                    or image.get("data-lazy-src")
                    or image.get("data-original")
                    or ""
                )

                candidate = get_absolute_image_url(
                    source_url,
                    candidate,
                )

                if (
                    not candidate
                    or image_url_looks_bad(
                        candidate
                    )
                ):
                    continue

                alt_text = (
                    image.get(
                        "alt",
                        "",
                    )
                    .lower()
                )

                if any(
                    bad in alt_text
                    for bad in [
                        "logo",
                        "icon",
                        "avatar",
                        "author",
                    ]
                ):
                    continue

                width_raw = (
                    image.get("width")
                    or "0"
                )

                height_raw = (
                    image.get("height")
                    or "0"
                )

                try:
                    width = int(
                        re.sub(
                            r"[^0-9]",
                            "",
                            str(width_raw),
                        )
                        or 0
                    )
                except Exception:
                    width = 0

                try:
                    height = int(
                        re.sub(
                            r"[^0-9]",
                            "",
                            str(height_raw),
                        )
                        or 0
                    )
                except Exception:
                    height = 0

                if (
                    width
                    and height
                    and (
                        width < 600
                        or height < 300
                    )
                ):
                    continue

                if not validate_remote_image_candidate(
                    candidate
                ):
                    continue

                if not source_image_matches_article(
                    article_title,
                    story,
                    candidate,
                ):
                    continue

                print(
                    f"Contextual image found from page: "
                    f"{candidate}"
                )
                return candidate

        except Exception as error:
            print(
                f"Could not scan page images: "
                f"{error}"
            )

    print(
        "No usable contextual source artwork found. "
        "Using GamerQuest fallback."
    )

    return None


def build_news_featured_image(
    article_title,
    suggested_slug,
    story,
):
    """
    Generate and save one 1200x630 GamerQuest featured image.

    Returns the metadata that WordPress will use later.
    """

    NEWS_IMAGES_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_image_url = (
        extract_source_image_url(
            story,
            article_title,
        )
    )

    safe_slug = (
        slugify(
            suggested_slug
            or article_title
        )
        or "gamerquest-news"
    )

    filename = (
        f"{safe_slug}.jpg"
    )

    output_path = (
        NEWS_IMAGES_FOLDER
        / filename
    )

    generate_news_image(
        title=article_title,
        source_image_url=source_image_url,
        output_path=output_path,
    )

    repository = os.environ.get(
        "GITHUB_REPOSITORY",
        "RizkAdham96/gamerquest-automation",
    )

    branch = os.environ.get(
        "GITHUB_REF_NAME",
        "main",
    )

    public_url = (
        "https://raw.githubusercontent.com/"
        f"{repository}/"
        f"{branch}/"
        f"generated_news_images/"
        f"{filename}"
    )

    image_metadata = {
        "url": public_url,
        "filename": filename,
        "alt": (
            f"{article_title} - GamerQuest"
        ),
        "caption": (
            f"Illustration de l'article "
            f"« {article_title} »."
        ),
        "description": (
            "Image GamerQuest générée automatiquement "
            "à partir d'un visuel contextuel de la source "
            "lorsqu'il est disponible."
        ),
        "source_image_url":
            source_image_url,
    }

    print("")
    print(
        "==================================="
    )
    print(
        "NEWS IMAGE GENERATED"
    )
    print(
        "==================================="
    )
    print(
        f"Image file: {output_path}"
    )
    print(
        f"Public URL: {public_url}"
    )

    return image_metadata


# =========================================================
# NEWS FEED
# =========================================================

def get_news_source_id(source_url):
    normalized = str(source_url).strip().lower()
    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def parse_feed_tags(tags):
    if isinstance(tags, list):
        return [
            str(tag).strip()
            for tag in tags
            if str(tag).strip()
        ]

    return [
        tag.strip()
        for tag in str(tags).split(",")
        if tag.strip()
    ]


def load_existing_news_feed():
    if not NEWS_FEED_FILE.exists():
        return {
            "generated_at": None,
            "count": 0,
            "articles": [],
        }

    try:
        data = json.loads(
            NEWS_FEED_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, dict):
            raise ValueError(
                "News feed is not a JSON object."
            )

        if not isinstance(
            data.get("articles"),
            list,
        ):
            raise ValueError(
                "News feed articles is not a list."
            )

        return data

    except Exception as error:
        print("")
        print(
            "WARNING: Existing news feed "
            "could not be loaded."
        )
        print(
            f"Reason: {error}"
        )

        return {
            "generated_at": None,
            "count": 0,
            "articles": [],
        }




def load_news_topic_history():
    """Load compact topic history kept beyond the rolling 50-item feed."""
    if not NEWS_TOPIC_HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(NEWS_TOPIC_HISTORY_FILE.read_text(encoding="utf-8"))
        articles = data.get("articles", []) if isinstance(data, dict) else data
        if not isinstance(articles, list):
            return []
        return [item for item in articles if isinstance(item, dict)]
    except Exception as error:
        print(f"WARNING: News topic history could not be loaded: {error}")
        return []


def combined_news_quality_history():
    feed_articles = load_existing_news_feed().get("articles", [])
    history_articles = load_news_topic_history()
    merged = []
    seen = set()
    for item in [*feed_articles, *history_articles]:
        key = slugify(item.get("slug", "") or item.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def remember_news_topic(article):
    STATE_FOLDER.mkdir(exist_ok=True)
    history = load_news_topic_history()
    article_seo = article.get("seo", {})
    if not isinstance(article_seo, dict):
        article_seo = {}
    compact = {
        "title": str(article.get("title", "")).strip(),
        "slug": str(article.get("slug", "")).strip(),
        "content": str(article.get("content", ""))[:3000],
        "tags": article.get("tags", []) if isinstance(article.get("tags", []), list) else [],
        "seo": {"primary_keyword": str(article_seo.get("primary_keyword", "")).strip()},
    }
    compact_key = slugify(compact["slug"] or compact["title"])
    remaining = []
    for item in history:
        item_key = slugify(item.get("slug", "") or item.get("title", ""))
        if item_key and item_key == compact_key:
            continue
        remaining.append(item)
    NEWS_TOPIC_HISTORY_FILE.write_text(
        json.dumps({"articles": [compact, *remaining][:MAX_NEWS_TOPIC_HISTORY]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_news_feed_article(
    article_data,
    story,
    official_story=None,
):
    (
        seo_title,
        meta_description,
        primary_keyword,
        secondary_keywords,
        search_intent,
        suggested_slug,
        title,
        excerpt,
        category,
        tags,
        content,
    ) = article_data

    source_url = (
        story.get("url", "")
        .strip()
    )

    official_source = None

    if official_story:
        official_source = {
            "title": official_story.get(
                "title",
                "",
            ),
            "url": official_story.get(
                "url",
                "",
            ),
        }

    return {
        "source_id": get_news_source_id(
            source_url
        ),
        "title": title,
        "excerpt": excerpt,
        "content": content,
        "slug": suggested_slug,
        "category": category,
        "tags": parse_feed_tags(
            tags
        ),
        "seo": {
            "seo_title": seo_title,
            "meta_description":
                meta_description,
            "primary_keyword":
                primary_keyword,
            "secondary_keywords":
                parse_feed_tags(
                    secondary_keywords
                ),
            "search_intent":
                search_intent,
        },
        "source": {
            "url": source_url,
            "title": story.get(
                "title",
                "",
            ),
            "published_date":
                story.get(
                    "published_date",
                    "",
                ),
            "domain": get_domain(
                source_url
            ),
        },
        "official_source":
            official_source,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "featured_image": build_news_featured_image(
            article_title=title,
            suggested_slug=suggested_slug,
            story=story,
        ),
    }


def article_data_for_quality_guards(article_data):
    """Create the feed-shaped metadata needed before image generation."""
    return {
        "title": article_data[6],
        "slug": article_data[5],
        "content": article_data[10],
        "tags": parse_feed_tags(article_data[9]),
        "seo": {
            "primary_keyword": article_data[2],
        },
    }


def news_quality_rejection(article_data, existing_articles=None):
    candidate = article_data_for_quality_guards(article_data)
    if existing_articles is None:
        existing_articles = combined_news_quality_history()

    if has_conflicting_news_claims(candidate, existing_articles):
        return "Conflicting release-date or platform claims for an existing topic."
    if is_duplicate_news_topic(candidate, existing_articles):
        return "The same News story already exists in the feed."
    return ""


def source_grounding_rejection(
    article_data,
    source_text,
    official_text="",
):
    """Reject sensitive claims that do not appear in the supplied evidence."""
    candidate = article_data_for_quality_guards(article_data)
    article_text = " ".join(
        [
            str(candidate.get("title", "")),
            str(candidate.get("content", "")),
        ]
    ).lower()
    evidence_text = f"{source_text}\n{official_text}".lower()

    platform_groups = {
        "Xbox": ("xbox",),
        "PlayStation": ("playstation", "ps5", "ps4"),
        "Nintendo Switch": ("nintendo switch", "switch 2"),
        "Steam": ("steam",),
        "Epic Games Store": ("epic games store", "epic games"),
        "PC": (" pc ", "windows"),
    }

    padded_article = f" {article_text} "
    padded_evidence = f" {evidence_text} "

    for label, aliases in platform_groups.items():
        article_has = any(alias in padded_article for alias in aliases)
        evidence_has = any(alias in padded_evidence for alias in aliases)
        if article_has and not evidence_has:
            return f"Unsupported platform claim: {label}."

    article_years = set(
        re.findall(r"\b20(?:2[5-9]|3[0-5])\b", article_text)
    )
    evidence_years = set(
        re.findall(r"\b20(?:2[5-9]|3[0-5])\b", evidence_text)
    )
    unsupported_years = sorted(article_years - evidence_years)
    if unsupported_years:
        return (
            "Unsupported release/year claim: "
            + ", ".join(unsupported_years)
            + "."
        )

    multiplayer_terms = (
        "multijoueur", "multiplayer", "co-op", "coop",
        "coopération", "cooperation", "pvp", "horde",
    )
    if (
        any(term in article_text for term in multiplayer_terms)
        and not any(term in evidence_text for term in multiplayer_terms)
    ):
        return "Unsupported multiplayer/co-op claim."

    negative_sensitive_patterns = (
        r"ne\s+mentionne\s+(?:aucun|pas)",
        r"aucun\s+(?:mode\s+)?multijoueur",
        r"pas\s+de\s+(?:mode\s+)?multijoueur",
        r"sans\s+(?:mode\s+)?multijoueur",
    )
    if any(re.search(pattern, article_text) for pattern in negative_sensitive_patterns):
        return "Unsupported negative feature claim."

    return ""


def save_news_to_feed(
    article_data,
    story,
    official_story=None,
):
    feed = load_existing_news_feed()
    existing_articles = feed.get("articles", [])
    rejection_reason = news_quality_rejection(
        article_data,
        existing_articles,
    )

    if rejection_reason:
        print("")
        print(f"NEWS ARTICLE BLOCKED: {rejection_reason}")
        return None

    new_article = build_news_feed_article(
        article_data,
        story,
        official_story,
    )

    existing_articles = [
        article
        for article in existing_articles
        if article.get(
            "source_id"
        )
        != new_article[
            "source_id"
        ]
    ]

    articles = [
        new_article,
        *existing_articles,
    ][:MAX_NEWS_FEED_ARTICLES]

    updated_feed = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "count": len(
            articles
        ),
        "articles": articles,
    }

    NEWS_FEED_FILE.write_text(
        json.dumps(
            updated_feed,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    remember_news_topic(new_article)

    print("")
    print(
        "==================================="
    )
    print(
        "NEWS FEED UPDATED"
    )
    print(
        "==================================="
    )
    print(
        f"Feed articles: "
        f"{len(articles)}"
    )
    print(
        f"Added: "
        f"{new_article['title']}"
    )
    print(
        f"Feed file: "
        f"{NEWS_FEED_FILE}"
    )

    return new_article


# =========================================================
# MONTHLY TAVILY COUNTER
# =========================================================

def current_month():
    return datetime.now(
        timezone.utc
    ).strftime("%Y-%m")


def load_tavily_state():
    STATE_FOLDER.mkdir(
        exist_ok=True
    )

    month = current_month()

    default_state = {
        "month": month,
        "searches_used": 0,
    }

    if not TAVILY_STATE_FILE.exists():
        return default_state

    try:
        state = json.loads(
            TAVILY_STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return default_state

    if state.get("month") != month:
        return default_state

    try:
        searches_used = int(
            state.get(
                "searches_used",
                0
            )
        )
    except Exception:
        searches_used = 0

    return {
        "month": month,
        "searches_used": searches_used,
    }


def save_tavily_state(state):
    STATE_FOLDER.mkdir(
        exist_ok=True
    )

    TAVILY_STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
        ),
        encoding="utf-8",
    )


def check_monthly_credit_safety():
    state = load_tavily_state()

    used = state["searches_used"]

    print("")
    print(
        f"Tavily tracked searches: "
        f"{used} / "
        f"{TAVILY_MONTHLY_SAFETY_LIMIT}"
    )

    if used >= TAVILY_MONTHLY_SAFETY_LIMIT:
        print("")
        print(
            "TAVILY MONTHLY SAFETY STOP"
        )

        print(
            "No Tavily search will be "
            "performed this month."
        )

        sys.exit(0)

    return state


def record_tavily_search(state):
    state["searches_used"] += 1

    save_tavily_state(
        state
    )

    print(
        f"Tracked Tavily searches this month: "
        f"{state['searches_used']}"
    )


# =========================================================
# DUPLICATE CHECK
# =========================================================

def source_already_used(source_url):
    if not DRAFTS_FOLDER.exists():
        return False

    for draft_file in DRAFTS_FOLDER.glob(
        "*.md"
    ):
        try:
            text = draft_file.read_text(
                encoding="utf-8"
            )

            if source_url in text:
                return True

        except Exception:
            continue

    return False


def get_recent_source_domains():
    if not DRAFTS_FOLDER.exists():
        return []

    domains = []

    files = sorted(
        DRAFTS_FOLDER.glob("*.md"),
        reverse=True,
    )

    for draft_file in files[:12]:
        try:
            text = draft_file.read_text(
                encoding="utf-8"
            )

            urls = re.findall(
                r'https?://[^\s<>"\']+',
                text,
            )

            for url in urls:
                domain = get_domain(
                    url
                )

                if (
                    domain
                    and domain not in domains
                ):
                    domains.append(
                        domain
                    )

        except Exception:
            continue

    return domains[:10]


# =========================================================
# TAVILY SEARCH
# =========================================================

def search_gaming_news():
    state = check_monthly_credit_safety()

    print("")
    print("Searching gaming news...")

    print(
        "Maximum Tavily searches "
        f"this run: {MAX_TAVILY_SEARCHES_PER_RUN}"
    )

    print(
        f"Tavily candidate target "
        f"per search: {MAX_RESULTS}"
    )

    print(
        "Tavily freshness window: 7 days"
    )

    all_clean_results = []
    seen_urls = set()

    searches_completed = 0

    for search_number, query in enumerate(
        SEARCH_QUERIES[
            :MAX_TAVILY_SEARCHES_PER_RUN
        ],
        start=1,
    ):
        # ---------------------------------------------
        # MONTHLY SAFETY CHECK BEFORE EVERY SEARCH
        # ---------------------------------------------

        if (
            state["searches_used"]
            >= TAVILY_MONTHLY_SAFETY_LIMIT
        ):
            print("")
            print(
                "TAVILY MONTHLY SAFETY STOP"
            )

            print(
                "Monthly Tavily limit reached."
            )

            break

        print("")
        print(
            "==================================="
        )

        print(
            f"TAVILY SEARCH "
            f"{search_number}/"
            f"{MAX_TAVILY_SEARCHES_PER_RUN}"
        )

        print(
            "==================================="
        )

        print(
            f"Query: {query}"
        )

        try:
            response = requests.post(
                TAVILY_SEARCH_URL,
                headers={
                    "Authorization":
                        f"Bearer {TAVILY_API_KEY}",
                    "Content-Type":
                        "application/json",
                },
                json={
                    "query": query,
                    "search_depth": "basic",
                    "topic": "news",
                    "time_range": "week",
                    "max_results": MAX_RESULTS,
                    "include_answer": False,
                    "include_raw_content":
                        "text",
                    "auto_parameters": False,
                },
                timeout=60,
            )

            response.raise_for_status()

        except requests.exceptions.RequestException as error:
            print(
                f"Tavily search "
                f"{search_number} failed: "
                f"{error}"
            )

            continue

        # Count the search ONLY after Tavily
        # successfully accepted the request.
        record_tavily_search(
            state
        )

        searches_completed += 1

        data = response.json()

        results = data.get(
            "results",
            []
        )

        print(
            f"Tavily returned "
            f"{len(results)} candidates."
        )

        clean_results = []

        for result in results:
            title = (
                result
                .get("title", "")
                .strip()
            )

            url = (
                result
                .get("url", "")
                .strip()
            )

            if (
                not title
                or not url
            ):
                continue

            # -----------------------------------------
            # DUPLICATE WITHIN CURRENT SEARCHES
            # -----------------------------------------

            normalized_url = (
                url
                .lower()
                .rstrip("/")
            )

            if normalized_url in seen_urls:
                print(
                    "Duplicate Tavily result "
                    f"skipped: {title}"
                )

                continue

            seen_urls.add(
                normalized_url
            )

            # -----------------------------------------
            # DUPLICATE WITH PREVIOUS ARTICLES
            # -----------------------------------------

            if source_already_used(
                url
            ):
                print(
                    f"Duplicate skipped: "
                    f"{title}"
                )

                continue

            tier = source_tier(
                url
            )

            content_len = (
                result_content_length(
                    result
                )
            )

            # Unknown domains need substantial
            # source content before being accepted.
            if (
                tier == 3
                and content_len < 1200
            ):
                print(
                    "Weak source skipped "
                    "before selection: "
                    f"{get_domain(url)} | "
                    f"{title}"
                )

                continue

            clean_results.append(
                result
            )

        print(
            f"Usable candidates from "
            f"search {search_number}: "
            f"{len(clean_results)}"
        )

        all_clean_results.extend(
            clean_results
        )

        # ---------------------------------------------
        # KEEP SEARCHING FOR A DIVERSIFIED CANDIDATE POOL
        # ---------------------------------------------
        #
        # A URL can look usable here and still fail later source validation
        # or the topic-level quality guard. Collecting both configured
        # searches gives the retry loop below somewhere useful to go instead
        # of letting one stale/invalid story kill the scheduled run.
        # ---------------------------------------------

        if (
            search_number
            < MAX_TAVILY_SEARCHES_PER_RUN
        ):
            print("")

            if clean_results:
                print(
                    "Fresh candidates found; "
                    "collecting diversified fallback candidates too..."
                )
            else:
                print(
                    "No usable fresh source "
                    "from this search."
                )
                print(
                    "Trying diversified "
                    "fallback search..."
                )

    # =====================================================
    # NOTHING FOUND
    # =====================================================

    if not all_clean_results:
        print("")
        print(
            "==================================="
        )

        print(
            "NO USABLE GAMING NEWS FOUND"
        )

        print(
            "==================================="
        )

        print(
            f"Tavily searches performed "
            f"this run: "
            f"{searches_completed}"
        )

        print(
            "All returned stories were "
            "duplicates, weak sources, "
            "or unusable."
        )

        print(
            "Automation will stop safely "
            "without creating an article."
        )

        sys.exit(0)

    # =====================================================
    # REMOVE ANY FINAL DUPLICATES
    # =====================================================

    unique_results = []

    final_seen_urls = set()

    for result in all_clean_results:
        url = (
            result
            .get("url", "")
            .strip()
        )

        normalized_url = (
            url
            .lower()
            .rstrip("/")
        )

        if normalized_url in final_seen_urls:
            continue

        final_seen_urls.add(
            normalized_url
        )

        unique_results.append(
            result
        )

    print("")
    print(
        f"Total usable unique candidates: "
        f"{len(unique_results)}"
    )

    # =====================================================
    # PRIORITIZE OFFICIAL + TRUSTED SOURCES
    # =====================================================

    preferred_results = [
        result
        for result in unique_results
        if source_tier(
            result.get(
                "url",
                ""
            )
        ) <= 2
    ]

    if preferred_results:
        print(
            f"Using "
            f"{len(preferred_results)} "
            "official/trusted candidates "
            "for editorial selection."
        )

        return preferred_results

    # =====================================================
    # FALLBACK TO VETTED UNKNOWN SOURCES
    # =====================================================

    print(
        "No official/trusted candidate "
        "found; using vetted "
        "fallback sources."
    )

    return unique_results


# =========================================================
# SEO-FIRST STORY SELECTION
# =========================================================

def story_priority_score(result, recent_domains=None):
    """Deterministically rank a vetted news candidate without spending AI tokens."""
    recent_domains = set(recent_domains or [])
    title = str(result.get("title", "") or "")
    url = str(result.get("url", "") or "")
    domain = get_domain(url)
    normalized = slugify(title).replace("-", " ")

    score = {1: 55, 2: 38, 3: 12}.get(source_tier(url), 0)

    high_intent = (
        "date de sortie", "release date", "plateforme", "platform",
        "patch", "performance", "erreur", "error", "comment ",
        "how to", "dlc", "gratuit", "free", "game pass",
        "crossplay", "sauvegarde", "save",
    )
    score += min(
        30,
        sum(8 for marker in high_intent if marker in normalized),
    )

    specific_terms = normalized_news_terms(title) - NEWS_TOPIC_GENERIC_TERMS
    score += min(12, len(specific_terms) * 2)

    content_length = result_content_length(result)
    if content_length >= 2500:
        score += 8
    elif content_length >= 1200:
        score += 4

    if domain in recent_domains:
        score -= 10

    return score


def select_best_story(results):
    """Choose the strongest remaining opportunity locally."""
    if not results:
        raise RuntimeError("No news candidates available for selection.")

    recent_domains = get_recent_source_domains()
    ranked = sorted(
        enumerate(results),
        key=lambda item: (
            story_priority_score(item[1], recent_domains),
            -item[0],
        ),
        reverse=True,
    )
    _, story = ranked[0]

    print("")
    print("SEO story selected (deterministic ranking):")
    print(story.get("title", ""))
    print(story.get("url", ""))
    print("Priority score:", story_priority_score(story, recent_domains))
    return story


# =========================================================
# PAGE EXTRACTION
# =========================================================

def extract_page(story):
    raw_content = (
        story.get(
            "raw_content",
            ""
        )
        or ""
    )

    if (
        len(raw_content)
        >= MIN_SOURCE_TEXT_LENGTH
    ):
        print(
            "Using article content "
            "returned by Tavily."
        )

        return raw_content[
            :MAX_SOURCE_TEXT_LENGTH
        ]

    print(
        "Fetching selected page directly..."
    )

    response = requests.get(
        story["url"],
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; "
                "GamerQuestFR/1.0)"
            )
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    for element in soup([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "form",
        "noscript",
    ]):
        element.decompose()

    article = soup.find(
        "article"
    )

    if article:
        text = article.get_text(
            separator="\n",
            strip=True,
        )
    else:
        text = soup.get_text(
            separator="\n",
            strip=True,
        )

    return text[
        :MAX_SOURCE_TEXT_LENGTH
    ]


# =========================================================
# SOURCE VALIDATION
# =========================================================

def validate_source(
    story,
    source_text,
):
    """Validate source structure and title/body coherence without an AI call."""
    url = story.get("url", "").strip()
    title = story.get("title", "").strip()
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if not path:
        return (False, "Homepage URL detected.")

    generic_paths = {
        "news", "gaming", "games", "articles",
        "latest", "home", "category",
    }
    if path.lower() in generic_paths:
        return (False, "Generic landing page.")

    tier = source_tier(url)
    required_length = 250 if tier == 1 else 500 if tier == 2 else 1200
    if len(source_text) < required_length:
        return (
            False,
            f"Source content too short for source tier {tier}: "
            f"{len(source_text)} chars, requires {required_length}.",
        )

    title_words = normalize_words(title)
    unique_words = set(title_words)
    if not unique_words:
        return (False, "Could not analyse title.")

    body_lower = source_text.lower()
    matched = sum(1 for word in unique_words if word in body_lower)
    ratio = matched / max(len(unique_words), 1)
    print(f"Title/body match ratio: {ratio:.2f}")

    minimum_ratio = 0.30 if tier == 1 else 0.35 if tier == 2 else 0.45
    if ratio < minimum_ratio:
        return (False, "Source/title mismatch.")

    return (True, "Source validation passed.")


# =========================================================
# OFFICIAL SOURCE MATCHING
# =========================================================

def find_matching_official_source(
    selected_story,
    all_results,
):
    """Match an official source by specific title/content term overlap."""
    selected_terms = (
        normalized_news_terms(selected_story.get("title", ""))
        - NEWS_TOPIC_GENERIC_TERMS
    )
    if not selected_terms:
        return None

    best = None
    best_score = 0

    for candidate in all_results:
        if not looks_official(candidate.get("url", "")):
            continue

        content = (
            candidate.get("content", "")
            or candidate.get("raw_content", "")
            or ""
        )
        candidate_text = f"{candidate.get('title', '')} {content[:1400]}"
        candidate_terms = (
            normalized_news_terms(candidate_text)
            - NEWS_TOPIC_GENERIC_TERMS
        )
        overlap = selected_terms & candidate_terms
        ratio = len(overlap) / max(len(selected_terms), 1)

        if len(overlap) < 2 or ratio < 0.35:
            continue

        score = len(overlap) * 10 + int(ratio * 20)
        if score > best_score:
            best = candidate
            best_score = score

    return best


def compact_ai_source(text, max_chars):
    """Remove formatting noise while preserving factual wording."""
    text = str(text or "")
    text = re.sub(r"[\t\r ]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return "\n".join(line.strip() for line in text.split("\n") if line.strip())[:max_chars]


# =========================================================
# SEO ARTICLE GENERATION
# =========================================================

def generate_article(
    story,
    source_text,
    official_story=None,
    official_text="",
):
    print("")
    print(
        "Generating SEO article..."
    )

    discovery_source = compact_ai_source(source_text, MAX_GENERATION_SOURCE_LENGTH)
    official_source = compact_ai_source(official_text, MAX_OFFICIAL_SOURCE_LENGTH)

    official_section = ""

    if (
        official_story
        and official_source
    ):
        official_section = f"""

OFFICIAL VERIFICATION SOURCE:

TITLE:
{official_story.get('title', '')}

URL:
{official_story.get('url', '')}

CONTENT:
{official_source}

"""

    prompt = f"""
You are the SEO editor and gaming journalist
for GamerQuest FR.

Create an ORIGINAL French article designed
to capture organic search demand.

DISCOVERY SOURCE:

TITLE:
{story.get('title', '')}

URL:
{story.get('url', '')}

CONTENT:
{discovery_source}

{official_section}


SEO GOAL:

Choose a realistic primary keyword based on
likely user search intent.

Examples:

- game date de sortie
- game plateformes
- game prix
- game gameplay
- game PS5
- game Switch 2
- game multijoueur
- game DLC

Never invent keyword volume,
CPC or difficulty.


FACTUAL RULES:

- Never invent facts.
- Never add information from memory.
- Never invent dates.
- Never invent platforms.
- Never invent pricing.
- Never invent multiplayer details.
- Never invent availability.
- Never invent trailer links.
- Never create placeholder iframe URLs.
- If source gives a date without year,
  do not add a year.
- If online/local co-op is unclear,
  simply say cooperative play.


SEO STRUCTURE:

The introduction must answer
the main search intent directly.

Use useful H2 headings such as:

- Quelle est la date de sortie de [GAME] ?
- Sur quelles plateformes sortira [GAME] ?
- Quel sera le prix de [GAME] ?
- Que sait-on du gameplay ?
- [GAME] proposera-t-il du multijoueur ?

Only use headings the source can answer.

Do not keyword-stuff.

No filler.

No generic conclusion.


RETURN EXACTLY:

SEO_TITLE: [SEO title]

META_DESCRIPTION: [130-160 character description]

PRIMARY_KEYWORD: [main keyword]

SECONDARY_KEYWORDS: [4-8 comma-separated keywords]

SEARCH_INTENT: [Informational / News / Commercial investigation]

SUGGESTED_SLUG: [SEO slug]

TITLE: [article title]

EXCERPT: [20-35 word excerpt]

CATEGORY: [Actualités, Guides, Sélections, Tests & Avis]

TAGS: [3-6 tags]

CONTENT:
[HTML only]
"""

    return groq_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SEO strategist "
                    "and conservative French "
                    "gaming journalist."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.15,
        max_tokens=GROQ_GENERATION_MAX_TOKENS,
        model=GROQ_GENERATION_MODEL,
    )


# =========================================================
# PARSE ARTICLE
# =========================================================

def extract_labeled_field(
    text,
    label,
    next_label=None,
):
    """
    Extract a top-level AI field using labels anchored to the
    beginning of a line.

    This prevents TITLE: from matching the TITLE: substring
    inside SEO_TITLE:.
    """

    start_pattern = (
        rf"(?mi)^[ \t]*{re.escape(label)}[ \t]*:[ \t]*"
    )

    start_match = re.search(
        start_pattern,
        text,
    )

    if not start_match:
        raise RuntimeError(
            f"Missing required field: {label}"
        )

    value_start = start_match.end()

    if next_label is None:
        return text[
            value_start:
        ].strip()

    end_pattern = (
        rf"(?mi)^[ \t]*{re.escape(next_label)}[ \t]*:"
    )

    end_match = re.search(
        end_pattern,
        text[value_start:],
    )

    if not end_match:
        raise RuntimeError(
            f"Missing required field after "
            f"{label}: {next_label}"
        )

    value_end = (
        value_start
        + end_match.start()
    )

    return text[
        value_start:value_end
    ].strip()


def parse_article(text):
    text = strip_code_fences(
        text
    )

    try:
        seo_title = extract_labeled_field(
            text,
            "SEO_TITLE",
            "META_DESCRIPTION",
        )

        meta_description = extract_labeled_field(
            text,
            "META_DESCRIPTION",
            "PRIMARY_KEYWORD",
        )

        primary_keyword = extract_labeled_field(
            text,
            "PRIMARY_KEYWORD",
            "SECONDARY_KEYWORDS",
        )

        secondary_keywords = extract_labeled_field(
            text,
            "SECONDARY_KEYWORDS",
            "SEARCH_INTENT",
        )

        search_intent = extract_labeled_field(
            text,
            "SEARCH_INTENT",
            "SUGGESTED_SLUG",
        )

        suggested_slug = extract_labeled_field(
            text,
            "SUGGESTED_SLUG",
            "TITLE",
        )

        title = extract_labeled_field(
            text,
            "TITLE",
            "EXCERPT",
        )

        excerpt = extract_labeled_field(
            text,
            "EXCERPT",
            "CATEGORY",
        )

        category = extract_labeled_field(
            text,
            "CATEGORY",
            "TAGS",
        )

        tags = extract_labeled_field(
            text,
            "TAGS",
            "CONTENT",
        )

        content = extract_labeled_field(
            text,
            "CONTENT",
            None,
        )

    except Exception as error:
        raise RuntimeError(
            "Generated SEO article "
            f"could not be parsed: {error}"
        )

    content = sanitize_article_html(
        content
    )

    suggested_slug = slugify(
        suggested_slug
        or seo_title
    )

    allowed_categories = {
        "Actualités",
        "Guides",
        "Sélections",
        "Tests & Avis",
    }

    if category not in allowed_categories:
        category = "Actualités"

    return (
        seo_title,
        meta_description,
        primary_keyword,
        secondary_keywords,
        search_intent,
        suggested_slug,
        title,
        excerpt,
        category,
        tags,
        content,
    )


# =========================================================
# FINAL SEO + FACTUAL CORRECTION
# =========================================================

def verify_and_correct_article(
    article_data,
    source_text,
    official_text="",
):
    (
        seo_title,
        meta_description,
        primary_keyword,
        secondary_keywords,
        search_intent,
        suggested_slug,
        title,
        excerpt,
        category,
        tags,
        content,
    ) = article_data

    print("")
    print(
        "Running SEO + factual correction..."
    )

    compact_source = compact_ai_source(source_text, MAX_VERIFICATION_SOURCE_LENGTH)
    compact_official = compact_ai_source(official_text, MAX_OFFICIAL_SOURCE_LENGTH)

    official_section = ""

    if compact_official:
        official_section = f"""

OFFICIAL SOURCE:

{compact_official}

"""

    prompt = f"""
You are the final SEO and factual editor
for GamerQuest FR.

Correct the article.
Do NOT reject it.

SOURCE:

{compact_source}

{official_section}

SEO TITLE:
{seo_title}

META:
{meta_description}

PRIMARY KEYWORD:
{primary_keyword}

SECONDARY KEYWORDS:
{secondary_keywords}

SEARCH INTENT:
{search_intent}

SLUG:
{suggested_slug}

TITLE:
{title}

EXCERPT:
{excerpt}

CATEGORY:
{category}

TAGS:
{tags}

ARTICLE:
{content}


CORRECTION RULES:

- Remove unsupported facts.
- Never invent replacement facts.
- Never use memory.
- Remove unsupported years.
- Remove unsupported local/online claims.
- Remove unsupported prices/platforms.
- Attribute secondary-source claims when needed.
- Remove fake media URLs or placeholder iframe embeds.

SEO RULES:

- Keep primary keyword natural.
- Make SEO title useful, not spammy.
- Keep meta description useful.
- Keep slug short.
- Introduction should directly answer main query.
- H2s should reflect useful related search intent.
- No keyword stuffing.
- No invented keyword metrics.


RETURN EXACTLY:

SEO_TITLE: [corrected SEO title]

META_DESCRIPTION: [corrected meta]

PRIMARY_KEYWORD: [keyword]

SECONDARY_KEYWORDS: [keywords]

SEARCH_INTENT: [intent]

SUGGESTED_SLUG: [slug]

TITLE: [title]

EXCERPT: [excerpt]

CATEGORY: [category]

TAGS: [tags]

CONTENT:
[corrected HTML]
"""

    corrected = groq_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a concise SEO editor "
                    "and conservative fact-checker."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.05,
        max_tokens=GROQ_VERIFICATION_MAX_TOKENS,
        model=GROQ_VERIFICATION_MODEL,
    )

    try:
        return parse_article(
            corrected
        )
    except RuntimeError as error:
        # The generation pass has already produced a complete article. The
        # editor is an additional correction pass; a malformed editor format
        # must not kill the News run. The unchanged article still goes through
        # source_grounding_rejection() and all normal News quality guards
        # before it can be saved or published.
        print("")
        print(
            "Final Groq editor returned an unusable formatted response; "
            "keeping the generated article for local safety validation."
        )
        print(f"Editor parse error: {error}")
        return article_data



# =========================================================
# CONTEXTUAL INTERNAL LINKING
# =========================================================

MAX_CONTEXTUAL_INTERNAL_LINKS = 3

# Generic gaming/search terms must never be enough by themselves
# to justify a contextual internal link.
INTERNAL_LINK_GENERIC_TERMS = {
    "date",
    "sortie",
    "release",
    "trailer",
    "gameplay",
    "steam",
    "pc",
    "ps5",
    "ps4",
    "xbox",
    "switch",
    "nintendo",
    "playstation",
    "plateforme",
    "plateformes",
    "console",
    "consoles",
    "jeu",
    "jeux",
    "gaming",
    "video",
    "vidéo",
    "annonce",
    "annonces",
    "nouveau",
    "nouveaux",
    "nouvelle",
    "nouvelles",
    "mise",
    "jour",
    "update",
    "dlc",
}


def specific_internal_link_terms(text):
    return {
        word
        for word in normalize_words(text)
        if word not in INTERNAL_LINK_GENERIC_TERMS
    }


def is_generic_anchor_phrase(phrase):
    normalized = normalize_internal_link_phrase(
        phrase
    ).lower()

    generic_phrases = {
        "date de sortie",
        "trailer",
        "gameplay",
        "steam",
        "pc",
        "ps5",
        "ps4",
        "xbox",
        "switch",
        "nintendo switch",
        "nintendo switch 2",
        "playstation",
        "plateformes",
        "plateforme",
        "dlc",
        "mise à jour",
        "mise a jour",
    }

    if normalized in generic_phrases:
        return True

    words = set(
        normalize_words(normalized)
    )

    return bool(words) and words.issubset(
        INTERNAL_LINK_GENERIC_TERMS
    )


def normalize_internal_link_phrase(text):
    return re.sub(
        r"\s+",
        " ",
        str(text or "").strip(),
    )


def existing_internal_link_candidates(article_data):
    (
        seo_title,
        meta_description,
        primary_keyword,
        secondary_keywords,
        search_intent,
        suggested_slug,
        title,
        excerpt,
        category,
        tags,
        content,
    ) = article_data

    feed = load_existing_news_feed()
    existing_articles = feed.get("articles", [])

    current_terms = set(
        normalize_words(
            " ".join([
                title,
                primary_keyword,
                secondary_keywords,
                tags,
            ])
        )
    )

    candidates = []

    for article in existing_articles:
        candidate_slug = str(article.get("slug", "")).strip()
        candidate_title = str(article.get("title", "")).strip()

        if (
            not candidate_slug
            or not candidate_title
            or candidate_slug == suggested_slug
        ):
            continue

        candidate_tags = article.get("tags", [])

        if not isinstance(candidate_tags, list):
            candidate_tags = []

        candidate_seo = article.get("seo", {})
        candidate_keyword = str(
            candidate_seo.get("primary_keyword", "")
        )

        candidate_terms = set(
            normalize_words(
                " ".join([
                    candidate_title,
                    candidate_keyword,
                    " ".join(candidate_tags),
                ])
            )
        )

        specific_current_terms = specific_internal_link_terms(
            " ".join([
                title,
                primary_keyword,
                secondary_keywords,
                tags,
            ])
        )

        specific_candidate_terms = specific_internal_link_terms(
            " ".join([
                candidate_title,
                candidate_keyword,
                " ".join(candidate_tags),
            ])
        )

        specific_overlap = (
            specific_current_terms
            & specific_candidate_terms
        )

        # Generic words like "Steam", "trailer", "PS5",
        # or "date de sortie" cannot create a match alone.
        if not specific_overlap:
            continue

        # Specific overlap is heavily weighted.
        score = (
            len(specific_overlap) * 10
            + len(current_terms & candidate_terms)
        )

        candidates.append({
            "score": score,
            "title": candidate_title,
            "slug": candidate_slug,
            "tags": candidate_tags,
            "primary_keyword": candidate_keyword,
        })

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return candidates


def candidate_anchor_phrases(candidate):
    phrases = []

    for tag in candidate.get("tags", []):
        phrase = normalize_internal_link_phrase(tag)

        if len(phrase) >= 5:
            phrases.append(phrase)

    keyword = normalize_internal_link_phrase(
        candidate.get("primary_keyword", "")
    )

    if len(keyword) >= 5:
        phrases.append(keyword)

    title = normalize_internal_link_phrase(
        candidate.get("title", "")
    )

    if len(title) >= 8:
        phrases.append(title)

    return sorted(
        set(phrases),
        key=len,
        reverse=True,
    )


def insert_link_into_soup(
    soup,
    phrase,
    url,
):
    pattern = re.compile(
        re.escape(phrase),
        flags=re.IGNORECASE,
    )

    forbidden_parents = {
        "a",
        "script",
        "style",
        "h1",
        "h2",
        "h3",
        "h4",
    }

    for text_node in soup.find_all(string=True):
        parent = text_node.parent

        if (
            not parent
            or parent.name in forbidden_parents
        ):
            continue

        text = str(text_node)
        match = pattern.search(text)

        if not match:
            continue

        before = text[:match.start()]
        matched = text[match.start():match.end()]
        after = text[match.end():]

        replacement = []

        if before:
            replacement.append(
                NavigableString(before)
            )

        link = soup.new_tag(
            "a",
            href=url,
        )
        link.string = matched
        replacement.append(link)

        if after:
            replacement.append(
                NavigableString(after)
            )

        text_node.replace_with(
            *replacement
        )

        return True

    return False


def add_contextual_internal_links(
    article_data,
):
    if not WP_URL:
        print(
            "Internal links skipped: "
            "WP_URL is missing."
        )
        return article_data

    (
        seo_title,
        meta_description,
        primary_keyword,
        secondary_keywords,
        search_intent,
        suggested_slug,
        title,
        excerpt,
        category,
        tags,
        content,
    ) = article_data

    candidates = existing_internal_link_candidates(
        article_data
    )

    if not candidates:
        print(
            "No relevant internal-link "
            "candidates found."
        )
        return article_data

    soup = BeautifulSoup(
        content,
        "html.parser",
    )

    links_added = 0
    used_urls = set()

    for candidate in candidates:
        if links_added >= MAX_CONTEXTUAL_INTERNAL_LINKS:
            break

        target_url = (
            f"{WP_URL}/"
            f"{candidate['slug'].strip('/')}/"
        )

        if target_url in used_urls:
            continue

        for phrase in candidate_anchor_phrases(
            candidate
        ):
            if is_generic_anchor_phrase(phrase):
                continue

            added = insert_link_into_soup(
                soup,
                phrase,
                target_url,
            )

            if not added:
                continue

            used_urls.add(target_url)
            links_added += 1

            print(
                "Internal link added: "
                f"{phrase} -> {target_url}"
            )
            break

    if links_added == 0:
        print(
            "No natural contextual "
            "internal-link opportunities found."
        )
        return article_data

    new_content = str(soup)

    print(
        f"Contextual internal links added: "
        f"{links_added}"
    )

    return (
        seo_title,
        meta_description,
        primary_keyword,
        secondary_keywords,
        search_intent,
        suggested_slug,
        title,
        excerpt,
        category,
        tags,
        new_content,
    )


# =========================================================
# SAVE DRAFT
# =========================================================

def save_draft(
    article_data,
    story,
    official_story=None,
):
    (
        seo_title,
        meta_description,
        primary_keyword,
        secondary_keywords,
        search_intent,
        suggested_slug,
        title,
        excerpt,
        category,
        tags,
        content,
    ) = article_data

    DRAFTS_FOLDER.mkdir(
        exist_ok=True
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d-%H%M"
    )

    filename = (
        DRAFTS_FOLDER
        / f"{timestamp}-"
        f"{suggested_slug}.md"
    )

    verification = (
        "No matching official source "
        "was found."
    )

    if official_story:
        verification = (
            f"{official_story.get('title', '')}\n\n"
            f"{official_story.get('url', '')}"
        )

    markdown = f"""# {title}

## SEO

### SEO Title

{seo_title}

### Meta Description

{meta_description}

### Primary Keyword

{primary_keyword}

### Secondary Keywords

{secondary_keywords}

### Search Intent

{search_intent}

### Suggested Slug

{suggested_slug}

## Excerpt

{excerpt}

## Category

{category}

## Tags

{tags}

## Article

{content}

## Discovery Source

{get_domain(story.get('url', ''))}

## Source Title

{story.get('title', '')}

## Source URL

{story.get('url', '')}

## Source Date

{story.get('published_date', '')}

## Verification Source

{verification}

## Validation

Source validation: PASSED

SEO optimization: PASSED

Editorial correction: PASSED

## Status

SEO DRAFT - HUMAN REVIEW REQUIRED BEFORE PUBLISHING
"""

    filename.write_text(
        markdown,
        encoding="utf-8",
    )

    print("")
    print(
        "==================================="
    )

    print(
        "SEO DRAFT CREATED"
    )

    print(
        "==================================="
    )

    print(
        filename
    )


# =========================================================
# WORDPRESS DRAFT PUBLISHING
# =========================================================

def send_to_wordpress_draft(
    article_data,
):
    """
    Send the final corrected article to WordPress as a DRAFT.

    IMPORTANT:
    - WordPress failure NEVER crashes the automation.
    - The GitHub Markdown draft is already saved before this runs.
    - This function prints diagnostics without exposing secrets.
    - It never publishes publicly.
    """
    (
        seo_title,
        meta_description,
        primary_keyword,
        secondary_keywords,
        search_intent,
        suggested_slug,
        title,
        excerpt,
        category,
        tags,
        content,
    ) = article_data

    print("")
    print("===================================")
    print("WORDPRESS DRAFT DELIVERY")
    print("===================================")

    if not WP_URL:
        print("WORDPRESS SKIPPED: WP_URL is missing.")
        print("GitHub draft remains safely saved.")
        return None

    if not WP_USERNAME:
        print("WORDPRESS SKIPPED: WP_USERNAME is missing.")
        print("GitHub draft remains safely saved.")
        return None

    if not WP_APP_PASSWORD:
        print("WORDPRESS SKIPPED: WP_APP_PASSWORD is missing.")
        print("GitHub draft remains safely saved.")
        return None

    endpoint = f"{WP_URL}/wp-json/wp/v2/posts"

    payload = {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "status": "draft",
        "slug": suggested_slug,
    }

    print(f"WordPress base URL: {WP_URL}")
    print(f"WordPress REST endpoint: {endpoint}")
    print(f"WordPress username configured: {'YES' if WP_USERNAME else 'NO'}")
    print(f"Application password configured: {'YES' if WP_APP_PASSWORD else 'NO'}")

    # -----------------------------------------------------
    # 1. REST API reachability test
    # -----------------------------------------------------

    try:
        test_url = f"{WP_URL}/wp-json/"

        print("")
        print(f"Testing WordPress REST API: {test_url}")

        test_response = requests.get(
            test_url,
            timeout=20,
            headers={
                "User-Agent": "GamerQuestAutomation/1.0",
                "Accept": "application/json",
            },
            allow_redirects=True,
        )

        print(
            f"WordPress REST API test HTTP status: "
            f"{test_response.status_code}"
        )

        print(
            f"REST API test final URL: "
            f"{test_response.url}"
        )

        print(
            "REST API test Content-Type: "
            f"{test_response.headers.get('Content-Type', 'UNKNOWN')}"
        )

        if test_response.history:
            print("REST API test redirect history:")

            for redirect in test_response.history:
                print(
                    f"{redirect.status_code} "
                    f"-> {redirect.headers.get('Location', '')}"
                )
        else:
            print("REST API test redirect history: NONE")

    except requests.exceptions.Timeout:
        print(
            "WARNING: WordPress REST API test timed out. "
            "Will still attempt draft creation."
        )

    except requests.exceptions.ConnectionError as error:
        print(
            "WARNING: Could not reach WordPress REST API."
        )
        print(f"Connection error: {error}")
        print("GitHub draft remains safely saved.")
        return None

    except requests.exceptions.RequestException as error:
        print(
            "WARNING: WordPress REST API test failed."
        )
        print(f"Request error: {error}")
        print("Will still attempt draft creation.")

    # -----------------------------------------------------
    # 2. Authenticated post creation
    # -----------------------------------------------------

    try:
        print("")
        print(
            "Attempting authenticated WordPress "
            "draft creation..."
        )

        response = requests.post(
            endpoint,
            auth=(
                WP_USERNAME,
                WP_APP_PASSWORD,
            ),
            json=payload,
            timeout=45,
            headers={
                "User-Agent": "GamerQuestAutomation/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            allow_redirects=True,
        )

        print("")
        print(
            f"WordPress POST HTTP status: "
            f"{response.status_code}"
        )

        print(
            f"WordPress POST final URL: "
            f"{response.url}"
        )

        content_type = response.headers.get(
            "Content-Type",
            "UNKNOWN",
        )

        print(
            f"WordPress POST Content-Type: "
            f"{content_type}"
        )

        if response.history:
            print(
                "WordPress POST redirect history:"
            )

            for redirect in response.history:
                print(
                    f"{redirect.status_code} "
                    f"-> {redirect.headers.get('Location', '')}"
                )
        else:
            print(
                "WordPress POST redirect history: NONE"
            )

        # -------------------------------------------------
        # 3. Try to parse WordPress response
        # -------------------------------------------------

        try:
            post = response.json()

        except Exception:
            print("")
            print(
                "WORDPRESS RETURNED NON-JSON CONTENT"
            )

            print(
                "First 800 characters of the response:"
            )

            print(
                "-----------------------------------"
            )

            body_preview = (
                response.text[:800]
                if response.text
                else "[EMPTY RESPONSE BODY]"
            )

            print(body_preview)

            print(
                "-----------------------------------"
            )

            if response.status_code in (200, 201):
                print(
                    "The server returned HTTP success, "
                    "but not a normal WordPress JSON response."
                )

            print(
                "GitHub draft remains safely saved."
            )

            return None

        # -------------------------------------------------
        # 4. Normal REST API errors
        # -------------------------------------------------

        if response.status_code not in (200, 201):
            print("")
            print(
                "WORDPRESS DRAFT CREATION FAILED"
            )

            print(
                f"HTTP status: "
                f"{response.status_code}"
            )

            print(
                f"Response JSON: {post}"
            )

            if response.status_code == 400:
                print(
                    "Possible cause: WordPress rejected "
                    "part of the post payload."
                )

            elif response.status_code == 401:
                print(
                    "Possible cause: wrong WP_USERNAME or "
                    "WP_APP_PASSWORD, or Application Password "
                    "authentication is blocked."
                )

            elif response.status_code == 403:
                print(
                    "Possible cause: security plugin, firewall, "
                    "hosting rule, or insufficient WordPress permissions."
                )

            elif response.status_code == 404:
                print(
                    "Possible cause: WP_URL is wrong or the "
                    "WordPress posts REST endpoint is unavailable."
                )

            elif response.status_code == 429:
                print(
                    "Possible cause: WordPress, Cloudflare, "
                    "or the host is rate-limiting the request."
                )

            elif response.status_code >= 500:
                print(
                    "Possible cause: WordPress or hosting server error."
                )

            print(
                "GitHub draft remains safely saved."
            )

            return None

        # -------------------------------------------------
        # 5. Successful WordPress draft
        # -------------------------------------------------

        post_id = post.get("id")
        post_status = post.get("status")
        post_link = post.get("link")

        print("")
        print(
            "WORDPRESS DRAFT CREATED SUCCESSFULLY"
        )

        print(
            f"Post ID: {post_id}"
        )

        print(
            f"Status: {post_status}"
        )

        if post_link:
            print(
                f"URL: {post_link}"
            )

        return post

    except requests.exceptions.Timeout:
        print("")
        print(
            "WORDPRESS CONNECTION TIMED OUT."
        )
        print(
            "The article is still preserved "
            "in GitHub drafts/."
        )
        return None

    except requests.exceptions.ConnectionError as error:
        print("")
        print(
            "WORDPRESS CONNECTION FAILED."
        )
        print(
            f"Connection error: {error}"
        )
        print(
            "The WordPress server closed or "
            "refused the connection."
        )
        print(
            "The article is still preserved "
            "in GitHub drafts/."
        )
        return None

    except requests.exceptions.RequestException as error:
        print("")
        print(
            "WORDPRESS REQUEST FAILED."
        )
        print(
            f"Request error: {error}"
        )
        print(
            "The article is still preserved "
            "in GitHub drafts/."
        )
        return None

    except Exception as error:
        print("")
        print(
            "UNEXPECTED WORDPRESS ERROR."
        )
        print(
            f"Error: {error}"
        )
        print(
            "The article is still preserved "
            "in GitHub drafts/."
        )
        return None
# =========================================================
# REJECTION REPORT
# =========================================================

def save_rejection_report(
    stage,
    reason,
    story=None,
):
    REJECTED_FOLDER.mkdir(
        exist_ok=True
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d-%H%M%S"
    )

    filename = (
        REJECTED_FOLDER
        / f"{timestamp}-rejected.md"
    )

    story_title = ""
    story_url = ""

    if story:
        story_title = story.get(
            "title",
            ""
        )

        story_url = story.get(
            "url",
            ""
        )

    report = f"""# GamerQuest Rejection Report

## Stage

{stage}

## Reason

{reason}

## Story

{story_title}

## URL

{story_url}

## Result

SOURCE REJECTED - NO ARTICLE CREATED.
"""

    filename.write_text(
        report,
        encoding="utf-8",
    )


# =========================================================
# MAIN
# =========================================================

def main():
    run_started = time.monotonic()

    print("")
    print(
        "==================================="
    )

    print(
        "GamerQuest SEO Automation"
    )

    print(
        "==================================="
    )

    # One discovery pass can support several independent stories.
    # We keep Tavily usage bounded while allowing more publishing volume.
    results = search_gaming_news()

    remaining_results = list(results)
    attempts = 0
    published_count = 0

    while (
        remaining_results
        and attempts < MAX_NEWS_CANDIDATE_ATTEMPTS
        and published_count < MAX_NEWS_ARTICLES_PER_RUN
    ):
        elapsed = time.monotonic() - run_started
        remaining_budget = MAX_NEWS_RUN_SECONDS - elapsed

        if remaining_budget < MIN_SECONDS_TO_START_AI_CANDIDATE:
            print("")
            print("===================================")
            print("NEWS RUNTIME BUDGET REACHED")
            print("===================================")
            print(
                f"Only {remaining_budget:.0f}s remain in the safe News budget; "
                "stopping before another expensive AI candidate."
            )
            break

        attempts += 1

        print("")
        print(
            "==================================="
        )
        print(
            f"NEWS CANDIDATE ATTEMPT "
            f"{attempts}/{MAX_NEWS_CANDIDATE_ATTEMPTS}"
        )
        print(
            f"PUBLISHED THIS RUN: "
            f"{published_count}/{MAX_NEWS_ARTICLES_PER_RUN}"
        )
        print(
            "==================================="
        )

        # Pick the strongest remaining SEO opportunity.
        selected_story = select_best_story(
            remaining_results
        )

        selected_url = (
            selected_story
            .get("url", "")
            .strip()
            .lower()
            .rstrip("/")
        )

        # Remove the selected discovery result immediately. Any rejection
        # or success below continues with a different story.
        remaining_results = [
            result
            for result in remaining_results
            if (
                result
                .get("url", "")
                .strip()
                .lower()
                .rstrip("/")
                != selected_url
            )
        ]

        # Reject the same story/topic before any expensive AI call. URL-level
        # duplicate filtering happens during discovery; this topic-level pass
        # catches reworded/alternate-source duplicates using the same semantic
        # guard that protects the final feed.
        if discovery_story_is_duplicate(selected_story):
            print(
                "Topic duplicate skipped before Groq: "
                f"{selected_story.get('title', '')}"
            )
            continue

        # Prefer a matching official source when it is actually usable.
        official_story = find_matching_official_source(
            selected_story,
            results,
        )

        story = selected_story
        source_text = ""
        valid = False
        reason = ""

        if (
            official_story
            and official_story.get("url")
            != selected_story.get("url")
        ):
            print("")
            print(
                "Trying matching official source first:"
            )
            print(
                official_story.get("url", "")
            )

            official_source_text = extract_page(
                official_story
            )

            official_valid, official_reason = validate_source(
                official_story,
                official_source_text,
            )

            if official_valid:
                story = official_story
                source_text = official_source_text
                valid = True
                reason = ""
            else:
                print("")
                print(
                    "Official source was not usable; "
                    "falling back to the selected story."
                )
                print(
                    f"Reason: {official_reason}"
                )

                official_story = None

        if not valid:
            story = selected_story
            source_text = extract_page(
                story
            )

            valid, reason = validate_source(
                story,
                source_text,
            )

        if not valid:
            save_rejection_report(
                "SOURCE VALIDATION",
                reason,
                story,
            )

            print("")
            print(
                "Source rejected; trying the next candidate."
            )

            continue

        official_text = ""

        if official_story:
            print("")
            print(
                "Official source available:"
            )
            print(
                official_story.get(
                    "url",
                    ""
                )
            )

            if (
                official_story.get("url")
                == story.get("url")
            ):
                official_text = source_text
            else:
                official_text = extract_page(
                    official_story
                )
        else:
            print("")
            print(
                "No usable matching official source found. "
                "Using established secondary source only."
            )

        elapsed = time.monotonic() - run_started
        remaining_budget = MAX_NEWS_RUN_SECONDS - elapsed
        if remaining_budget < MIN_SECONDS_TO_START_AI_CANDIDATE:
            print("")
            print("Skipping AI generation because the safe News runtime budget is nearly exhausted.")
            break

        try:
            generated = generate_article(
                story,
                source_text,
                official_story,
                official_text,
            )

            article_data = parse_article(
                generated
            )

            article_data = (
                verify_and_correct_article(
                    article_data,
                    source_text,
                    official_text,
                )
            )
        except GroqRunDeferred:
            raise

        rejection_reason = source_grounding_rejection(
            article_data,
            source_text,
            official_text,
        )
        if not rejection_reason:
            rejection_reason = news_quality_rejection(
                article_data
            )

        if rejection_reason:
            save_rejection_report(
                "NEWS QUALITY GUARD",
                rejection_reason,
                story,
            )

            print("")
            print(
                "News candidate blocked: "
                f"{rejection_reason}"
            )
            print(
                "Trying the next candidate."
            )

            continue

        article_data = add_contextual_internal_links(
            article_data
        )

        save_draft(
            article_data,
            story,
            official_story,
        )

        saved_article = save_news_to_feed(
            article_data,
            story,
            official_story,
        )

        if saved_article is None:
            print("")
            print(
                "Feed rejected the candidate at final save; "
                "trying the next candidate."
            )
            continue

        published_count += 1

        print("")
        print(
            "GamerQuest article accepted."
        )
        print(
            f"Published this run: "
            f"{published_count}/{MAX_NEWS_ARTICLES_PER_RUN}"
        )

        if (
            remaining_results
            and published_count < MAX_NEWS_ARTICLES_PER_RUN
        ):
            print(
                f"Pacing Groq models for "
                f"{GROQ_BETWEEN_ARTICLES_WAIT_SECONDS}s "
                "before the next article."
            )
            time.sleep(GROQ_BETWEEN_ARTICLES_WAIT_SECONDS)

    print("")
    print(
        "==================================="
    )

    if published_count:
        print(
            "GAMERQUEST NEWS RUN COMPLETE"
        )
        print(
            "==================================="
        )
        print(
            f"Published {published_count} article(s) "
            f"after {attempts} candidate attempt(s)."
        )
    else:
        print(
            "NO PUBLISHABLE NEWS CANDIDATE"
        )
        print(
            "==================================="
        )
        print(
            f"Tried {attempts} different candidate(s)."
        )
        print(
            "All were invalid, duplicate, contradictory, "
            "or otherwise rejected safely."
        )


if __name__ == "__main__":
    try:
        main()
    except GroqBudgetDeferred as error:
        print("")
        print("===================================")
        print("NEWS STOPPED AT SHARED GROQ CEILING")
        print("===================================")
        print(str(error))
        print(
            "Quality settings were not reduced. The remaining AI work is "
            "deferred until a future run has a fresh shared budget allocation."
        )
        sys.exit(0)
    except GroqRunDeferred as error:
        print("")
        print("===================================")
        print("NEWS RUN DEFERRED CLEANLY")
        print("===================================")
        print(str(error))
        print(
            "No quality rule was bypassed. State already produced by this run "
            "can still be saved, and the next scheduled run can try again."
        )
        # A provider-side rate-limit outage remains visible as a real failure.
        sys.exit(75)
