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

def parse_article(text):
    text = strip_code_fences(
        text
    )

    try:
        seo_title = (
            text
            .split("SEO_TITLE:", 1)[1]
            .split("META_DESCRIPTION:", 1)[0]
            .strip()
        )

        meta_description = (
            text
            .split("META_DESCRIPTION:", 1)[1]
            .split("PRIMARY_KEYWORD:", 1)[0]
            .strip()
        )

        primary_keyword = (
            text
            .split("PRIMARY_KEYWORD:", 1)[1]
            .split("SECONDARY_KEYWORDS:", 1)[0]
            .strip()
        )

        secondary_keywords = (
            text
            .split("SECONDARY_KEYWORDS:", 1)[1]
            .split("SEARCH_INTENT:", 1)[0]
            .strip()
        )

        search_intent = (
            text
            .split("SEARCH_INTENT:", 1)[1]
            .split("SUGGESTED_SLUG:", 1)[0]
            .strip()
        )

        suggested_slug = (
            text
            .split("SUGGESTED_SLUG:", 1)[1]
            .split("TITLE:", 1)[0]
            .strip()
        )

        title = (
            text
            .split("TITLE:", 1)[1]
            .split("EXCERPT:", 1)[0]
            .strip()
        )

        excerpt = (
            text
            .split("EXCERPT:", 1)[1]
            .split("CATEGORY:", 1)[0]
            .strip()
        )

        category = (
            text
            .split("CATEGORY:", 1)[1]
            .split("TAGS:", 1)[0]
            .strip()
        )

        tags = (
            text
            .split("TAGS:", 1)[1]
            .split("CONTENT:", 1)[0]
            .strip()
        )

        content = (
            text
            .split("CONTENT:", 1)[1]
            .strip()
        )

    except Exception:
        raise RuntimeError(
            "Generated SEO article "
            "could not be parsed."
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
    Try to send the final corrected article to WordPress as a DRAFT.

    IMPORTANT:
    - WordPress failure NEVER crashes the automation.
    - The GitHub Markdown draft is already saved before this function runs.
    - This function prints detailed diagnostics without exposing secrets.
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

    # Never fail the whole workflow because a WordPress secret is missing.
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

    print(f"WordPress base URL: {WP_URL}")
    print(f"WordPress REST endpoint: {endpoint}")
    print(f"WordPress username configured: {'YES' if WP_USERNAME else 'NO'}")
    print(f"Application password configured: {'YES' if WP_APP_PASSWORD else 'NO'}")

    # First perform a lightweight REST API reachability check.
    # This is unauthenticated on purpose: we just want to know whether
    # the WordPress REST API responds at all.
    try:
        test_url = f"{WP_URL}/wp-json/"
        print(f"Testing WordPress REST API: {test_url}")

        test_response = requests.get(
            test_url,
            timeout=20,
            headers={
                "User-Agent": "GamerQuestAutomation/1.0"
            },
        )

        print(
            f"WordPress REST API test HTTP status: "
            f"{test_response.status_code}"
        )

        if test_response.status_code >= 500:
            print(
                "WARNING: WordPress server returned a 5xx error "
                "during REST API test."
            )

    except requests.exceptions.Timeout:
        print(
            "WARNING: WordPress REST API test timed out. "
            "Will still attempt draft creation."
        )

    except requests.exceptions.ConnectionError as error:
        print(
            "WARNING: Could not reach the WordPress REST API "
            "during the connection test."
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

    # WordPress post payload.
    # SEO metadata stays in the GitHub Markdown backup for now.
    payload = {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "status": "draft",
        "slug": suggested_slug,
    }

    try:
        print("")
        print("Attempting authenticated WordPress draft creation...")

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
            },
        )

        print(
            f"WordPress POST HTTP status: "
            f"{response.status_code}"
        )

        if response.status_code in (200, 201):
            try:
                post = response.json()
            except Exception:
                print(
                    "WordPress returned success but the response "
                    "could not be parsed as JSON."
                )
                print("GitHub draft remains safely saved.")
                return None

            post_id = post.get("id")
            post_status = post.get("status")
            post_link = post.get("link")

            print(
                f"WordPress draft created successfully. "
                f"ID: {post_id}"
            )
            print(
                f"WordPress status: {post_status}"
            )

            if post_link:
                print(
                    f"WordPress URL: {post_link}"
                )

            return post

        # Helpful diagnostics for common WordPress failures.
        try:
            error_body = response.json()
        except Exception:
            error_body = response.text[:1200]

        print("")
        print("WORDPRESS DRAFT CREATION FAILED")
        print(f"HTTP status: {response.status_code}")
        print(f"Response: {error_body}")

        if response.status_code == 400:
            print(
                "Possible cause: WordPress rejected part of the post payload."
            )

        elif response.status_code == 401:
            print(
                "Possible cause: incorrect WP_USERNAME or WP_APP_PASSWORD, "
                "or Application Password authentication is blocked."
            )

        elif response.status_code == 403:
            print(
                "Possible cause: security plugin, firewall, hosting rule, "
                "or this WordPress user does not have permission to create posts."
            )

        elif response.status_code == 404:
            print(
                "Possible cause: WP_URL is wrong or /wp-json/wp/v2/posts "
                "is unavailable."
            )

        elif response.status_code == 429:
            print(
                "Possible cause: WordPress, Cloudflare, or the host "
                "is rate-limiting the automation."
            )

        elif response.status_code >= 500:
            print(
                "Possible cause: WordPress/hosting server error."
            )

        print("GitHub draft remains safely saved.")
        return None

    except requests.exceptions.Timeout:
        print("")
        print("WORDPRESS CONNECTION TIMED OUT.")
        print(
            "The article is still preserved in GitHub drafts/."
        )
        return None

    except requests.exceptions.ConnectionError as error:
        print("")
        print("WORDPRESS CONNECTION FAILED.")
        print(f"Connection error: {error}")
        print(
            "The WordPress server closed or refused the connection."
        )
        print(
            "The article is still preserved in GitHub drafts/."
        )
        return None

    except requests.exceptions.RequestException as error:
        print("")
        print("WORDPRESS REQUEST FAILED.")
        print(f"Request error: {error}")
        print(
            "The article is still preserved in GitHub drafts/."
        )
        return None

    except Exception as error:
        # Final guardrail: WordPress must never kill the workflow.
        print("")
        print("UNEXPECTED WORDPRESS ERROR.")
        print(f"Error: {error}")
        print(
            "The article is still preserved in GitHub drafts/."
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

    # 9. Try to send the corrected article to WordPress as DRAFT only.
    # WordPress failure is NON-FATAL; the GitHub draft is already safe.
    wordpress_result = send_to_wordpress_draft(
        article_data,
    )

    if wordpress_result is None:
        print("")
        print("WordPress delivery did not complete, but the GitHub draft is safe.")

    print("")
    print(
        "GamerQuest SEO automation "
        "completed successfully."
    )


if __name__ == "__main__":
    main()
