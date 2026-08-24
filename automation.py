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
from bs4 import BeautifulSoup
from groq import Groq, RateLimitError
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

NEWS_FEED_FILE = Path("gamerquest-news-feed.json")
MAX_NEWS_FEED_ARTICLES = 50
NEWS_IMAGES_FOLDER = Path("generated_news_images")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

TAVILY_MONTHLY_SAFETY_LIMIT = 900
MAX_TAVILY_SEARCHES_PER_RUN = 1

SEARCH_QUERY = (
    "latest video game news release date gameplay platforms price "
    "PlayStation Xbox Nintendo Switch 2 PC Steam Game Pass "
    "major game announcement update DLC hardware gaming"
)

MAX_RESULTS = 15

MIN_SOURCE_TEXT_LENGTH = 250

# We deliberately avoid sending huge pages repeatedly to Groq.
MAX_SOURCE_TEXT_LENGTH = 22000
MAX_GENERATION_SOURCE_LENGTH = 16000
MAX_VERIFICATION_SOURCE_LENGTH = 9000
MAX_OFFICIAL_SOURCE_LENGTH = 5000

GROQ_MODEL = "openai/gpt-oss-120b"

# Retry settings for 429 errors.
GROQ_MAX_RETRIES = 4
GROQ_DEFAULT_WAIT_SECONDS = 10


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

def groq_chat(
    messages,
    temperature=0.1,
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
                    model=GROQ_MODEL,
                    messages=messages,
                    temperature=temperature,
                )
            )

            return (
                response
                .choices[0]
                .message
                .content
            )

        except RateLimitError as error:
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

            # Give Groq a small extra buffer.
            wait_seconds += 2

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
                raise

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


def extract_source_image_url(story):
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
            story
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


def save_news_to_feed(
    article_data,
    story,
    official_story=None,
):
    new_article = build_news_feed_article(
        article_data,
        story,
        official_story,
    )

    feed = load_existing_news_feed()

    existing_articles = (
        feed.get(
            "articles",
            [],
        )
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
    print(
        "Searching gaming news..."
    )

    print(
        "Maximum Tavily searches "
        "this run: 1"
    )

    response = requests.post(
        TAVILY_SEARCH_URL,
        headers={
            "Authorization":
                f"Bearer {TAVILY_API_KEY}",
            "Content-Type":
                "application/json",
        },
        json={
            "query": SEARCH_QUERY,
            "search_depth": "basic",
            "topic": "news",
            "time_range": "day",
            "max_results": MAX_RESULTS,
            "include_answer": False,
            "include_raw_content": "text",
            "auto_parameters": False,
        },
        timeout=60,
    )

    response.raise_for_status()

    record_tavily_search(
        state
    )

    data = response.json()

    results = data.get(
        "results",
        []
    )

    if not results:
        print(
            "No gaming-news results found."
        )
        sys.exit(0)

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

        if not title or not url:
            continue

        if source_already_used(url):
            print(
                f"Duplicate skipped: "
                f"{title}"
            )
            continue

        tier = source_tier(url)
        content_len = result_content_length(result)

        # Unknown sources must provide substantial article text before
        # we even allow them into editorial selection. This prevents thin
        # SEO/aggregation sites from beating official or established media.
        if tier == 3 and content_len < 1200:
            print(
                f"Weak source skipped before selection: "
                f"{get_domain(url)} | {title}"
            )
            continue

        clean_results.append(result)

    if not clean_results:
        print(
            "No usable non-duplicate sources were returned."
        )
        sys.exit(0)

    preferred_results = [
        result
        for result in clean_results
        if source_tier(result.get("url", "")) <= 2
    ]

    # If the single search returned official/trusted sources, only let
    # those compete. Unknown sites are a last-resort fallback.
    if preferred_results:
        print(
            f"Using {len(preferred_results)} official/trusted "
            "candidates for editorial selection."
        )
        return preferred_results

    print(
        "No official/trusted candidate found; using vetted fallback sources."
    )
    return clean_results


# =========================================================
# SEO-FIRST STORY SELECTION
# =========================================================

def select_best_story(results):
    recent_domains = (
        get_recent_source_domains()
    )

    candidates = ""

    for index, result in enumerate(
        results,
        start=1,
    ):
        content = (
            result.get(
                "content",
                ""
            )
            or result.get(
                "raw_content",
                ""
            )
            or ""
        )

        candidates += f"""

CANDIDATE {index}

TITLE:
{result.get('title', '')}

DOMAIN:
{get_domain(result.get('url', ''))}

URL:
{result.get('url', '')}

DATE:
{result.get('published_date', '')}

SOURCE_TIER:
{source_tier(result.get('url', ''))} (1=official, 2=trusted media, 3=other)

CONTENT:
{content[:1100]}

---------------------------------
"""

    prompt = f"""
You are the SEO editor of GamerQuest FR.

Choose ONE gaming story with the strongest
organic-search opportunity.

RECENTLY USED DOMAINS:

{recent_domains}

CANDIDATES:

{candidates}

Prioritize topics where users may search:

- game + date de sortie
- game + plateformes
- game + prix
- game + gameplay
- game + PS5
- game + Xbox
- game + Switch 2
- game + PC
- game + Game Pass
- game + multijoueur
- game + nouveautés
- game + DLC

Prefer:

- release announcements
- gameplay reveals
- major DLC
- large franchises
- platform announcements
- price information
- hardware
- significant updates

Source-quality rules:

- Prefer tier 1 official/primary sources when they cover the same story.
- Tier 2 established gaming publications are acceptable when no official
  source for that exact story is available.
- Tier 3 sources are last-resort only.
- Never choose a thin, generic, scraped or aggregation page merely because
  its headline looks SEO-friendly.

Avoid:

- homepages
- thin stories
- opinion pieces
- rumors
- leaks
- SEO spam

Do NOT invent search volume,
keyword difficulty or CPC.

Return ONLY the candidate number.
"""

    answer = groq_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SEO strategist "
                    "specialized in gaming."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.1,
    )

    match = re.search(
        r"\d+",
        answer
    )

    if not match:
        raise RuntimeError(
            f"Could not parse selection: "
            f"{answer}"
        )

    number = int(
        match.group()
    )

    if (
        number < 1
        or number > len(results)
    ):
        raise RuntimeError(
            "Groq selected invalid candidate."
        )

    story = results[
        number - 1
    ]

    print("")
    print(
        "SEO story selected:"
    )

    print(
        story.get(
            "title",
            ""
        )
    )

    print(
        story.get(
            "url",
            ""
        )
    )

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
    url = story.get(
        "url",
        ""
    ).strip()

    title = story.get(
        "title",
        ""
    ).strip()

    parsed = urlparse(
        url
    )

    path = (
        parsed
        .path
        .strip("/")
    )

    if not path:
        return (
            False,
            "Homepage URL detected."
        )

    generic_paths = {
        "news",
        "gaming",
        "games",
        "articles",
        "latest",
        "home",
        "category",
    }

    if path.lower() in generic_paths:
        return (
            False,
            "Generic landing page."
        )

    tier = source_tier(url)

    # Short official announcements can be legitimate. Unknown sites need
    # considerably more substance before we trust them.
    if tier == 1:
        required_length = 250
    elif tier == 2:
        required_length = 500
    else:
        required_length = 1200

    if len(source_text) < required_length:
        return (
            False,
            f"Source content too short for source tier {tier}: "
            f"{len(source_text)} chars, requires {required_length}."
        )

    title_words = normalize_words(
        title
    )

    unique_words = set(
        title_words
    )

    if not unique_words:
        return (
            False,
            "Could not analyse title."
        )

    body_lower = (
        source_text
        .lower()
    )

    matched = sum(
        1
        for word in unique_words
        if word in body_lower
    )

    ratio = (
        matched
        / max(
            len(unique_words),
            1,
        )
    )

    print(
        f"Title/body match ratio: "
        f"{ratio:.2f}"
    )

    if ratio < 0.35:
        return (
            False,
            "Source/title mismatch."
        )

    prompt = f"""
Validate this gaming-news page.

TITLE:
{title}

URL:
{url}

CONTENT:
{source_text[:6000]}

Return VALID only if the page clearly
represents the same specific story.

Return INVALID for:

- homepage
- category page
- unrelated page
- contaminated extraction
- title/body mismatch

Return exactly:

VALID

or

INVALID
"""

    verdict = groq_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "Validate gaming-news "
                    "sources conservatively."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
    )

    verdict = (
        verdict
        .strip()
        .upper()
    )

    if verdict != "VALID":
        return (
            False,
            f"AI validator: {verdict}"
        )

    return (
        True,
        "Source validation passed."
    )


# =========================================================
# OFFICIAL SOURCE MATCHING
# =========================================================

def find_matching_official_source(
    selected_story,
    all_results,
):
    official_candidates = [
        result
        for result in all_results
        if looks_official(
            result.get(
                "url",
                ""
            )
        )
    ]

    if not official_candidates:
        return None

    candidates = ""

    for index, result in enumerate(
        official_candidates,
        start=1,
    ):
        content = (
            result.get(
                "content",
                ""
            )
            or result.get(
                "raw_content",
                ""
            )
            or ""
        )

        candidates += f"""

CANDIDATE {index}

TITLE:
{result.get('title', '')}

URL:
{result.get('url', '')}

CONTENT:
{content[:700]}

"""

    prompt = f"""
Selected story:

{selected_story.get('title', '')}

Possible official sources:

{candidates}

Return candidate number ONLY if one clearly
covers the same announcement.

Otherwise return:

NONE
"""

    answer = groq_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "Match official gaming "
                    "sources conservatively."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
    )

    if "NONE" in answer.upper():
        return None

    match = re.search(
        r"\d+",
        answer
    )

    if not match:
        return None

    number = int(
        match.group()
    )

    if (
        number < 1
        or number > len(
            official_candidates
        )
    ):
        return None

    return official_candidates[
        number - 1
    ]


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

    discovery_source = (
        source_text[
            :MAX_GENERATION_SOURCE_LENGTH
        ]
    )

    official_source = (
        official_text[
            :MAX_OFFICIAL_SOURCE_LENGTH
        ]
        if official_text
        else ""
    )

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

    content = strip_code_fences(
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

    # Important:
    # give Groq a moment before another large request.
    time.sleep(8)

    compact_source = (
        source_text[
            :MAX_VERIFICATION_SOURCE_LENGTH
        ]
    )

    compact_official = (
        official_text[
            :MAX_OFFICIAL_SOURCE_LENGTH
        ]
        if official_text
        else ""
    )

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
    )

    return parse_article(
        corrected
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

    # 1. Search
    results = search_gaming_news()

    # 2. Select SEO opportunity
    selected_story = select_best_story(
        results
    )

    # 3. BEFORE validation, look for a matching official source returned
    # by the SAME Tavily search. If one exists, make it the primary writing
    # source instead of merely using it as a verification footnote.
    official_story = (
        find_matching_official_source(
            selected_story,
            results,
        )
    )

    if (
        official_story
        and official_story.get("url") != selected_story.get("url")
    ):
        print("")
        print("Switching primary source to matching official source:")
        print(official_story.get("url", ""))
        discovery_story = selected_story
        story = official_story
    else:
        discovery_story = selected_story
        story = selected_story

    # 4. Extract and validate the BEST available primary source.
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
            "Source rejected."
        )

        return

    # 5. Keep official verification text when the primary source is official.
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

        if official_story.get("url") == story.get("url"):
            official_text = source_text
        else:
            official_text = extract_page(
                official_story
            )

    else:
        print("")
        print(
            "No matching official source found. "
            "Using established secondary source only."
        )

    # Small pause between Groq calls.
    time.sleep(4)

    # 6. Generate article
    generated = generate_article(
        story,
        source_text,
        official_story,
        official_text,
    )

    article_data = parse_article(
        generated
    )

    # 7. Final correction
    article_data = (
        verify_and_correct_article(
            article_data,
            source_text,
            official_text,
        )
    )

    # 8. Save GitHub Markdown backup
    save_draft(
        article_data,
        story,
        official_story,
    )

    # 9. Save the corrected article into the GitHub news feed.
    #
    # WordPress will pull this feed internally.
    # We do not POST directly from GitHub Actions because
    # the free hosting layer blocks automated external requests.
    save_news_to_feed(
        article_data,
        story,
        official_story,
    )

    print("")
    print(
        "GamerQuest SEO automation "
        "completed successfully."
    )


if __name__ == "__main__":
    main()
