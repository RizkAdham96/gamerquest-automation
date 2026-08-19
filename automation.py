import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from groq import Groq


# =========================================================
# CONFIGURATION
# =========================================================

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]

DRAFTS_FOLDER = Path("drafts")
REJECTED_FOLDER = Path("rejected")
STATE_FOLDER = Path("state")

TAVILY_STATE_FILE = STATE_FOLDER / "tavily_usage.json"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Safety limits
TAVILY_MONTHLY_SAFETY_LIMIT = 900
MAX_TAVILY_SEARCHES_PER_RUN = 1

# One broad search only
SEARCH_QUERY = (
    "latest video game news release date gameplay platforms price "
    "PlayStation Xbox Nintendo Switch 2 PC Steam Game Pass "
    "major game announcement update DLC hardware gaming"
)

MAX_RESULTS = 15
MIN_SOURCE_TEXT_LENGTH = 800
MAX_SOURCE_TEXT_LENGTH = 30000


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


def slugify(text):
    text = text.lower()

    # French accents -> SEO-safe approximations
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

    text = text.strip("-")

    return text[:90]


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
            "No Tavily search will be performed "
            "this month."
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
# DUPLICATE CHECKING
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
        "Maximum Tavily searches this run: 1"
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

    # Exactly one Tavily search was consumed.
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

        clean_results.append(
            result
        )

    if not clean_results:
        print(
            "Every result was already used."
        )
        sys.exit(0)

    return clean_results


# =========================================================
# SEO-FIRST STORY SELECTION
# =========================================================

def select_best_story(results):
    client = Groq(
        api_key=GROQ_API_KEY
    )

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

OFFICIAL:
{"YES" if looks_official(result.get('url', '')) else "NO"}

CONTENT:
{content[:1800]}

---------------------------------
"""

    prompt = f"""
You are the SEO editor of GamerQuest FR.

Choose ONE gaming story with the strongest
organic-search opportunity for a French gaming website.

RECENTLY USED DOMAINS:

{recent_domains}

CANDIDATES:

{candidates}


================================================
SEO OPPORTUNITY PRIORITIES
================================================

Evaluate candidates conceptually using:

35% search-intent opportunity
20% freshness
15% relevance to gamers
10% ability to answer specific questions
10% reliability/source quality
5% source diversity
5% evergreen/search value


Prefer stories where people are likely to search:

- "[game] date de sortie"
- "[game] plateformes"
- "[game] prix"
- "[game] gameplay"
- "[game] PS5"
- "[game] Xbox"
- "[game] Switch 2"
- "[game] PC"
- "[game] Game Pass"
- "[game] PlayStation Plus"
- "[game] multijoueur"
- "[game] configuration PC"
- "[game] nouveautés"
- "[game] DLC"
- "[game] mise à jour"


Prefer:

- release-date announcements
- platform announcements
- price/edition information
- gameplay reveals
- major DLC
- hardware
- substantial updates
- large franchises
- highly searchable new games


Avoid:

- tiny patches
- weak opinion stories
- vague interviews
- celebrity gossip
- rumors
- leaks
- homepages
- category pages
- SEO spam
- affiliate spam
- stories with almost no factual information


IMPORTANT:

You do NOT have real keyword-volume data.

Never pretend that you know monthly search volume,
keyword difficulty or CPC.

Choose based on likely search intent only.

Prefer source diversity.

Return ONLY the candidate number.
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SEO strategist "
                    "specialized in gaming search intent."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.1,
    )

    answer = (
        response
        .choices[0]
        .message
        .content
        .strip()
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
            "Groq selected an invalid candidate."
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

    path = parsed.path.strip(
        "/"
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
            "Generic landing/category page detected."
        )

    if (
        len(source_text)
        < MIN_SOURCE_TEXT_LENGTH
    ):
        return (
            False,
            "Extracted article content is too short."
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
            "Could not analyse source title."
        )

    body_lower = source_text.lower()

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
            "Source title and article "
            "do not match strongly enough."
        )

    client = Groq(
        api_key=GROQ_API_KEY
    )

    prompt = f"""
Validate this gaming-news source.

TITLE:
{title}

URL:
{url}

CONTENT:
{source_text[:9000]}

Return VALID only if this page clearly represents
the specific article described by the title.

Return INVALID for:

- homepage
- category/index page
- unrelated content
- contaminated extraction
- title/body mismatch

Return exactly:

VALID

or

INVALID
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
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
        response
        .choices[0]
        .message
        .content
        .strip()
        .upper()
    )

    if verdict != "VALID":
        return (
            False,
            f"AI validator returned: {verdict}"
        )

    return (
        True,
        "Source validation passed."
    )


# =========================================================
# OFFICIAL MATCH
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

    client = Groq(
        api_key=GROQ_API_KEY
    )

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

OFFICIAL CANDIDATE {index}

TITLE:
{result.get('title', '')}

URL:
{result.get('url', '')}

CONTENT:
{content[:1400]}

---------------------------------
"""

    prompt = f"""
Selected story:

{selected_story.get('title', '')}

Possible official sources:

{candidates}

Return the candidate number ONLY if one clearly
covers the same announcement.

Otherwise return:

NONE
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
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

    answer = (
        response
        .choices[0]
        .message
        .content
        .strip()
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
    client = Groq(
        api_key=GROQ_API_KEY
    )

    official_section = ""

    if (
        official_story
        and official_text
    ):
        official_section = f"""

OFFICIAL VERIFICATION SOURCE:

TITLE:
{official_story.get('title', '')}

URL:
{official_story.get('url', '')}

CONTENT:
{official_text}

"""

    prompt = f"""
You are the SEO editor and gaming journalist
for GamerQuest FR.

Create an ORIGINAL French gaming article
designed primarily to capture organic-search demand
while remaining factually accurate.

DISCOVERY SOURCE:

TITLE:
{story.get('title', '')}

URL:
{story.get('url', '')}

CONTENT:
{source_text}

{official_section}


================================================
SEO OBJECTIVE
================================================

Identify the strongest realistic search intent.

Examples:

- "[game] date de sortie"
- "[game] plateformes"
- "[game] prix"
- "[game] gameplay"
- "[game] PS5"
- "[game] Xbox"
- "[game] Switch 2"
- "[game] PC"
- "[game] Game Pass"
- "[game] multijoueur"
- "[game] nouveautés"

You do NOT have real keyword-volume data.

Never invent:

- search volume
- keyword difficulty
- CPC
- traffic estimates


================================================
SEO TITLE
================================================

Create a natural SEO title.

Prefer structures such as:

"[GAME] : date de sortie, plateformes, prix et gameplay"

when those facts are actually available.

Target approximately 45-65 characters when practical.

Do NOT keyword-stuff.


================================================
META DESCRIPTION
================================================

Write approximately 130-160 characters.

Include the main keyword naturally.

Summarize the concrete value of the page.


================================================
ARTICLE STRUCTURE
================================================

The first paragraph should directly answer
the main search intent.

Use descriptive H2 headings aligned with
likely Google searches.

Examples:

<h2>Quelle est la date de sortie de [GAME] ?</h2>

<h2>Sur quelles plateformes sortira [GAME] ?</h2>

<h2>Quel sera le prix de [GAME] ?</h2>

<h2>Que sait-on du gameplay ?</h2>

<h2>[GAME] proposera-t-il du multijoueur ?</h2>

Only include questions that the source can actually answer.

Do not mechanically add every possible H2.


================================================
SEO CONTENT QUALITY
================================================

Use the primary keyword naturally in:

- SEO title
- introductory paragraph
- at least one relevant H2 when natural

Use secondary keywords naturally.

Do NOT repeat keywords unnaturally.

Do NOT create filler just to increase article length.

Do NOT produce generic conclusions.

Aim for roughly 400-800 words when the source
provides enough useful information.

A shorter accurate article is better than
a padded article.


================================================
FACTUAL SAFETY
================================================

Never add facts from memory.

Never invent:

- dates
- platforms
- pricing
- multiplayer
- local/online functionality
- availability
- editions
- Game Pass
- PlayStation Plus
- technical specs
- reviews
- quotes

If an official source exists, it wins when
sources conflict.

If no official source exists, sensitive claims
from a secondary source must be attributed
when necessary.


================================================
MEDIA SAFETY
================================================

Never create:

- placeholder YouTube URLs
- fake iframe embeds
- invented trailer links
- fake screenshots
- fake official links

Only include a media URL if it explicitly exists
in the supplied source material.

Otherwise include no embed.


================================================
OUTPUT EXACTLY
================================================

SEO_TITLE: [optimized SEO title]

META_DESCRIPTION: [SEO meta description]

PRIMARY_KEYWORD: [one primary search keyword]

SECONDARY_KEYWORDS: [4-8 comma-separated keywords]

SEARCH_INTENT: [Informational / News / Commercial investigation]

SUGGESTED_SLUG: [short lowercase SEO slug]

TITLE: [reader-facing article title]

EXCERPT: [20-35 word factual excerpt]

CATEGORY: [Actualités, Guides, Sélections, Tests & Avis]

TAGS: [3-6 comma-separated tags]

CONTENT:
[HTML article only]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SEO strategist "
                    "and conservative French gaming journalist."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.15,
    )

    return (
        response
        .choices[0]
        .message
        .content
    )


# =========================================================
# PARSE SEO ARTICLE
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
            "Generated SEO article could not be parsed."
        )

    content = strip_code_fences(
        content
    )

    # Never trust generated slug blindly.
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

    client = Groq(
        api_key=GROQ_API_KEY
    )

    official_section = ""

    if official_text:
        official_section = f"""

OFFICIAL SOURCE:

{official_text}

"""

    prompt = f"""
You are the final SEO and factual editor
for GamerQuest FR.

Your job is to CORRECT this article,
not reject it.

SOURCE:

{source_text}

{official_section}

CURRENT SEO TITLE:
{seo_title}

CURRENT META DESCRIPTION:
{meta_description}

PRIMARY KEYWORD:
{primary_keyword}

SECONDARY KEYWORDS:
{secondary_keywords}

SEARCH INTENT:
{search_intent}

SUGGESTED SLUG:
{suggested_slug}

CURRENT TITLE:
{title}

CURRENT EXCERPT:
{excerpt}

CATEGORY:
{category}

TAGS:
{tags}

ARTICLE:
{content}


================================================
FACTUAL CORRECTION
================================================

Remove, soften or attribute unsupported claims.

Never invent replacement facts.

If a source gives December 10 without a year,
do not add a year.

If a source says four-player co-op without
stating online/local, do not invent online/local.

If Game Pass information exists only in a
secondary source and no official source verifies it,
attribute it appropriately.


================================================
SEO CORRECTION
================================================

Optimize for search intent.

Ensure:

- primary keyword is clear
- SEO title naturally reflects likely search intent
- meta description clearly summarizes value
- slug is short and relevant
- introduction directly answers the main query
- H2 headings answer useful related searches
- keywords are used naturally
- no keyword stuffing
- no unnecessary filler

Never invent keyword volume, CPC or difficulty.


================================================
MEDIA SAFETY
================================================

Remove any:

- placeholder iframe
- placeholder YouTube URL
- invented media URL
- fake link


================================================
RETURN EXACTLY
================================================

SEO_TITLE: [corrected SEO title]

META_DESCRIPTION: [corrected meta description]

PRIMARY_KEYWORD: [primary keyword]

SECONDARY_KEYWORDS: [comma-separated keywords]

SEARCH_INTENT: [search intent]

SUGGESTED_SLUG: [SEO slug]

TITLE: [article title]

EXCERPT: [excerpt]

CATEGORY: [category]

TAGS: [tags]

CONTENT:
[corrected HTML article only]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an SEO editor and conservative "
                    "gaming fact-checker. Correct problems "
                    "instead of rejecting usable articles."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.05,
    )

    corrected = (
        response
        .choices[0]
        .message
        .content
    )

    return parse_article(
        corrected
    )


# =========================================================
# SAVE SEO DRAFT
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
        / f"{timestamp}-{suggested_slug}.md"
    )

    verification = (
        "No matching official source was found."
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
        "SEO DRAFT CREATED:"
    )
    print(
        filename
    )


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
        "================================="
    )
    print(
        "GamerQuest SEO Automation"
    )
    print(
        "================================="
    )

    # 1. Find internet stories
    results = search_gaming_news()

    # 2. Choose based primarily on SEO opportunity
    story = select_best_story(
        results
    )

    # 3. Extract source
    source_text = extract_page(
        story
    )

    # 4. Reject only unusable source pages
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
        return

    # 5. Look for official verification
    # without another Tavily search
    official_story = (
        find_matching_official_source(
            story,
            results,
        )
    )

    official_text = ""

    if official_story:
        print("")
        print(
            "Official verification source found:"
        )
        print(
            official_story.get(
                "url",
                ""
            )
        )

        official_text = extract_page(
            official_story
        )

    # 6. Generate SEO-first article
    generated = generate_article(
        story,
        source_text,
        official_story,
        official_text,
    )

    article_data = parse_article(
        generated
    )

    # 7. Correct factual + SEO issues
    article_data = verify_and_correct_article(
        article_data,
        source_text,
        official_text,
    )

    # 8. Save corrected SEO draft
    save_draft(
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
