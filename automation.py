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

# Safety ceiling. We stop before 900 tracked searches/month.
TAVILY_MONTHLY_SAFETY_LIMIT = 900

# Exactly ONE Tavily Search API request per workflow run.
MAX_TAVILY_SEARCHES_PER_RUN = 1

SEARCH_QUERY = (
    "latest important video game news today "
    "game announcements releases major updates DLC hardware "
    "PlayStation Xbox Nintendo PC Steam gaming industry "
    "developers publishers"
)

MAX_RESULTS = 15
MIN_SOURCE_TEXT_LENGTH = 800
MAX_SOURCE_TEXT_LENGTH = 30000


# =========================================================
# OFFICIAL-SOURCE DOMAIN HELPERS
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
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)

    return text[:80]


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
        print("TAVILY MONTHLY SAFETY STOP")
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
                domain = get_domain(url)

                if (
                    domain
                    and domain not in domains
                ):
                    domains.append(domain)

        except Exception:
            continue

    return domains[:10]


# =========================================================
# ONE TAVILY SEARCH
# =========================================================

def search_gaming_news():
    state = check_monthly_credit_safety()

    searches_this_run = 0

    if (
        searches_this_run
        >= MAX_TAVILY_SEARCHES_PER_RUN
    ):
        raise RuntimeError(
            "Per-run Tavily limit reached."
        )

    print("")
    print("Searching gaming news...")
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

    searches_this_run += 1

    response.raise_for_status()

    # A Tavily search happened, so record it.
    record_tavily_search(
        state
    )

    data = response.json()

    results = data.get(
        "results",
        [],
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
                f"Duplicate skipped: {title}"
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
# EDITORIAL STORY SELECTION
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

OFFICIAL DOMAIN:
{"YES" if looks_official(result.get('url', '')) else "NO"}

CONTENT:
{content[:1800]}

---------------------------------
"""

    prompt = f"""
You are editor-in-chief of GamerQuest FR.

Choose ONE story that is genuinely worth covering
for a French gaming audience.

RECENTLY USED DOMAINS:

{recent_domains}

CANDIDATES:

{candidates}


PREFER:

- major game announcements
- major updates
- release information
- substantial DLC
- gameplay reveals
- gaming hardware
- acquisitions
- major industry developments
- meaningful platform news


REJECT OR DEPRIORITIZE:

- homepages
- category/index pages
- low-quality blogs
- affiliate spam
- SEO spam
- rumors
- leaks
- weak opinion articles
- tiny patches
- unrelated entertainment news
- stories with little factual substance


SOURCE DIVERSITY:

Do not automatically choose PlayStation.

If several stories are similarly strong,
prefer a source GamerQuest has used less recently.


Return ONLY the candidate number.
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict "
                    "gaming-news editor."
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
        answer,
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
    print("Selected story:")
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
            "Using raw article content "
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
                "GamerQuestFR/1.0; "
                "editorial research)"
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
# SOURCE VALIDATION — GATE 1
# =========================================================

def validate_source(
    story,
    source_text,
):
    print("")
    print(
        "Validating source..."
    )

    url = (
        story.get(
            "url",
            ""
        )
        .strip()
    )

    title = (
        story.get(
            "title",
            ""
        )
        .strip()
    )

    parsed = urlparse(
        url
    )

    path = (
        parsed
        .path
        .strip("/")
    )

    # Reject homepage.
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
            "Source title and extracted page "
            "do not match strongly enough."
        )

    client = Groq(
        api_key=GROQ_API_KEY
    )

    prompt = f"""
Validate this source before GamerQuest
is allowed to create an article.

SEARCH TITLE:

{title}

URL:

{url}

EXTRACTED CONTENT:

{source_text[:9000]}


Return VALID only when this is clearly
the specific article represented by the title.

Return INVALID if it appears to be:

- a homepage
- category page
- general news index
- unrelated page
- contaminated extraction
- multiple unrelated stories
- a title/body mismatch

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
                    "Validate web sources "
                    "conservatively."
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
# FIND OFFICIAL MATCH FROM SAME SEARCH
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

TITLE:
{selected_story.get('title', '')}

URL:
{selected_story.get('url', '')}


Possible official sources from the SAME search:

{candidates}


Return the number only if one clearly
covers the same announcement or event.

If none clearly matches, return:

NONE
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "Match official sources "
                    "conservatively."
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
        answer,
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
# ARTICLE GENERATION
# =========================================================

def generate_article(
    story,
    source_text,
    official_story=None,
    official_text="",
):
    print("")
    print(
        "Generating GamerQuest article..."
    )

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
You are a rigorous journalist for GamerQuest FR.

Write an ORIGINAL French gaming-news article.


================================================
DISCOVERY SOURCE
================================================

TITLE:
{story.get('title', '')}

DOMAIN:
{get_domain(story.get('url', ''))}

URL:
{story.get('url', '')}

DATE:
{story.get('published_date', '')}

CONTENT:
{source_text}


{official_section}


================================================
PRIMARY-SOURCE PRIORITY
================================================

If an official source is supplied,
it overrides the secondary discovery source
for factual conflicts involving:

- release dates
- early access
- platforms
- subscription services
- prices
- editions
- physical releases
- availability
- gameplay features
- technical specifications
- developers/publishers


================================================
HIGH-RISK CLAIMS
================================================

The following require extra caution:

- release dates
- early-access dates
- Xbox Game Pass
- PlayStation Plus
- Nintendo Switch Online
- subscription availability
- prices
- editions
- pre-order bonuses
- platforms
- physical editions
- regional availability
- exclusivity
- free-to-play status


IF AN OFFICIAL SOURCE EXISTS:

State these as facts only when the official
source supports them.


IF NO OFFICIAL SOURCE EXISTS:

A high-risk claim from a secondary source
must be clearly attributed.

Example:

GOOD:
"Selon IGN, le jeu devrait rejoindre
Xbox Game Pass dès son lancement."

BAD:
"Le jeu arrivera sur Xbox Game Pass
dès son lancement."


Do NOT make an unverified high-risk
secondary-source claim the main headline
unless attribution appears directly
in the headline.


================================================
NO FALSE CONFIRMATION LANGUAGE
================================================

Never write:

- Jagex confirme
- Sony confirme
- Microsoft confirme
- Nintendo confirme
- le studio confirme
- l'éditeur confirme

unless an official supplied source confirms
that specific fact.


================================================
NEVER INVENT
================================================

Never invent:

- dates
- platforms
- prices
- multiplayer
- single-player
- features
- technical specs
- quotes
- sales
- reviews
- reactions
- availability
- developer intentions


Never add facts from your own memory.


================================================
WRITING RULES
================================================

- Professional natural French.
- Do not copy source paragraphs.
- Do not imitate the source style.
- No clickbait.
- No filler.
- No generic conclusion.
- Preserve official names.
- Use useful H2 headings.
- Use lists only when helpful.
- Be geographically precise.
- Accuracy is more important than length.
- 250–700 words depending on source depth.


================================================
OUTPUT EXACTLY
================================================

TITLE: [French headline]

EXCERPT: [20–35 word factual summary]

CATEGORY: [one of: Actualités, Guides, Sélections, Tests & Avis]

TAGS: [3–6 comma-separated tags]

CONTENT:
[HTML only, no markdown code fences]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a conservative French "
                    "gaming journalist. "
                    "Never invent missing facts."
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
# PARSE GENERATED ARTICLE
# =========================================================

def parse_article(text):
    text = strip_code_fences(
        text
    )

    try:
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
            "Generated article could not be parsed."
        )

    content = strip_code_fences(
        content
    )

    allowed_categories = {
        "Actualités",
        "Guides",
        "Sélections",
        "Tests & Avis",
    }

    if category not in allowed_categories:
        category = "Actualités"

    if (
        not title
        or not excerpt
        or not content
    ):
        raise RuntimeError(
            "Generated article is missing fields."
        )

    return (
        title,
        excerpt,
        category,
        tags,
        content,
    )


# =========================================================
# FINAL FACT CHECK — GATE 2
# =========================================================

def fact_check_draft(
    title,
    excerpt,
    content,
    source_text,
    official_text="",
):
    print("")
    print(
        "Running final fact-check..."
    )

    client = Groq(
        api_key=GROQ_API_KEY
    )

    official_section = ""

    if official_text:
        official_section = f"""

OFFICIAL VERIFICATION SOURCE:

{official_text}

"""

    prompt = f"""
You are GamerQuest's final fact-checker.

DISCOVERY SOURCE:

{source_text}


{official_section}


GENERATED TITLE:

{title}


GENERATED EXCERPT:

{excerpt}


GENERATED ARTICLE:

{content}


Audit every material claim.

Check especially:

- dates
- platforms
- subscription availability
- Game Pass
- PlayStation Plus
- prices
- editions
- pre-order bonuses
- physical releases
- exclusivity
- multiplayer/single-player
- features
- technical specs
- names
- quotes
- geographic availability


If an official source exists,
it overrides conflicting secondary information.


If NO official source exists:

High-risk claims from a secondary source
must be explicitly attributed.

The TITLE and EXCERPT must also respect this.

Reject false confirmation wording such as:

"Jagex confirme"
"Sony confirme"
"Microsoft confirme"
"Nintendo confirme"

when there is no supplied official source.


If everything material is supported,
return exactly:

APPROVED


Otherwise return:

REJECTED

Then briefly explain why.
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an extremely conservative "
                    "gaming fact-checker."
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
    )

    print("")
    print(
        "FACT CHECK RESULT:"
    )
    print(
        verdict
    )

    return (
        verdict.upper().startswith(
            "APPROVED"
        ),
        verdict,
    )


# =========================================================
# SAVE APPROVED DRAFT
# =========================================================

def save_draft(
    title,
    excerpt,
    category,
    tags,
    content,
    story,
    official_story=None,
):
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
        / f"{timestamp}-{slugify(title)}.md"
    )

    verification = (
        "No matching official source was found "
        "in the same Tavily search."
    )

    if official_story:
        verification = (
            f"{official_story.get('title', '')}\n\n"
            f"{official_story.get('url', '')}"
        )

    markdown = f"""# {title}

## Excerpt

{excerpt}

## Category

{category}

## Tags

{tags}

## Article

{content}

## Discovery source

{get_domain(story.get('url', ''))}

## Source title

{story.get('title', '')}

## Source URL

{story.get('url', '')}

## Source date

{story.get('published_date', '')}

## Verification source

{verification}

## Validation

Source validation: PASSED

Fact-check: PASSED

## Status

DRAFT - HUMAN REVIEW REQUIRED BEFORE PUBLISHING
"""

    filename.write_text(
        markdown,
        encoding="utf-8",
    )

    print("")
    print(
        "APPROVED DRAFT CREATED:"
    )
    print(
        filename
    )


# =========================================================
# SAVE REJECTION REPORT
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

NO DRAFT WAS SAVED.
"""

    filename.write_text(
        report,
        encoding="utf-8",
    )

    print("")
    print(
        "Rejection report saved:"
    )
    print(
        filename
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
        "GamerQuest Automation"
    )
    print(
        "==================================="
    )

    results = search_gaming_news()

    story = select_best_story(
        results
    )

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

        print(
            "No article created."
        )

        return

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
            "Official matching source found:"
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

    else:
        print("")
        print(
            "No matching official source "
            "found in this search."
        )

    generated = generate_article(
        story,
        source_text,
        official_story,
        official_text,
    )

    (
        title,
        excerpt,
        category,
        tags,
        content,
    ) = parse_article(
        generated
    )

    approved, verdict = fact_check_draft(
        title,
        excerpt,
        content,
        source_text,
        official_text,
    )

    if not approved:
        save_rejection_report(
            "FACT CHECK",
            verdict,
            story,
        )

        print(
            "Draft rejected. "
            "Nothing saved to drafts/."
        )

        return

    save_draft(
        title,
        excerpt,
        category,
        tags,
        content,
        story,
        official_story,
    )

    print("")
    print(
        "Automation completed successfully."
    )


if __name__ == "__main__":
    main()
