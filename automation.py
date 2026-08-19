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

TAVILY_MONTHLY_SAFETY_LIMIT = 900
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
        "the", "and", "for", "from", "with",
        "this", "that", "into", "new", "news",
        "game", "games", "gaming", "video",
        "update", "reveals", "revealed",
        "announces", "announced",
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
    STATE_FOLDER.mkdir(exist_ok=True)

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
            state.get("searches_used", 0)
        )
    except Exception:
        searches_used = 0

    return {
        "month": month,
        "searches_used": searches_used,
    }


def save_tavily_state(state):
    STATE_FOLDER.mkdir(exist_ok=True)

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
        f"{used} / {TAVILY_MONTHLY_SAFETY_LIMIT}"
    )

    if used >= TAVILY_MONTHLY_SAFETY_LIMIT:
        print("")
        print("TAVILY MONTHLY SAFETY STOP")
        print(
            "No Tavily search will be performed this month."
        )
        sys.exit(0)

    return state


def record_tavily_search(state):
    state["searches_used"] += 1
    save_tavily_state(state)

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

    for draft_file in DRAFTS_FOLDER.glob("*.md"):
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

                if domain and domain not in domains:
                    domains.append(domain)

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
    print("Maximum Tavily searches this run: 1")

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

    record_tavily_search(state)

    data = response.json()

    results = data.get("results", [])

    if not results:
        print("No gaming-news results found.")
        sys.exit(0)

    print(
        f"Tavily returned {len(results)} candidates."
    )

    clean_results = []

    for result in results:
        title = result.get("title", "").strip()
        url = result.get("url", "").strip()

        if not title or not url:
            continue

        if source_already_used(url):
            print(
                f"Duplicate skipped: {title}"
            )
            continue

        clean_results.append(result)

    if not clean_results:
        print("Every result was already used.")
        sys.exit(0)

    return clean_results


# =========================================================
# STORY SELECTION
# =========================================================

def select_best_story(results):
    client = Groq(api_key=GROQ_API_KEY)

    recent_domains = get_recent_source_domains()

    candidates = ""

    for index, result in enumerate(
        results,
        start=1,
    ):
        content = (
            result.get("content", "")
            or result.get("raw_content", "")
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

Choose ONE story that is worth covering
for a French gaming audience.

RECENTLY USED DOMAINS:

{recent_domains}

CANDIDATES:

{candidates}

Prefer:
- major announcements
- releases
- substantial updates
- DLC
- gameplay reveals
- hardware
- acquisitions
- industry developments
- meaningful platform news

Avoid:
- homepages
- category pages
- spam
- affiliate content
- weak opinion pieces
- rumors
- leaks
- clickbait
- thin stories

Prefer source diversity.

Return ONLY the candidate number.
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict gaming-news editor."
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

    match = re.search(r"\d+", answer)

    if not match:
        raise RuntimeError(
            f"Could not parse selection: {answer}"
        )

    number = int(match.group())

    if number < 1 or number > len(results):
        raise RuntimeError(
            "Groq selected an invalid candidate."
        )

    story = results[number - 1]

    print("")
    print("Selected story:")
    print(story.get("title", ""))
    print(story.get("url", ""))

    return story


# =========================================================
# PAGE EXTRACTION
# =========================================================

def extract_page(story):
    raw_content = (
        story.get("raw_content", "")
        or ""
    )

    if len(raw_content) >= MIN_SOURCE_TEXT_LENGTH:
        print(
            "Using raw article content returned by Tavily."
        )

        return raw_content[
            :MAX_SOURCE_TEXT_LENGTH
        ]

    print("Fetching selected page directly...")

    response = requests.get(
        story["url"],
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; GamerQuestFR/1.0)"
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

    article = soup.find("article")

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

    return text[:MAX_SOURCE_TEXT_LENGTH]


# =========================================================
# SOURCE VALIDATION
# =========================================================

def validate_source(story, source_text):
    url = story.get("url", "").strip()
    title = story.get("title", "").strip()

    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if not path:
        return False, "Homepage URL detected."

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

    if len(source_text) < MIN_SOURCE_TEXT_LENGTH:
        return (
            False,
            "Extracted article content is too short."
        )

    title_words = normalize_words(title)
    unique_words = set(title_words)

    if not unique_words:
        return False, "Could not analyse source title."

    body_lower = source_text.lower()

    matched = sum(
        1
        for word in unique_words
        if word in body_lower
    )

    ratio = (
        matched
        / max(len(unique_words), 1)
    )

    print(
        f"Title/body match ratio: {ratio:.2f}"
    )

    if ratio < 0.35:
        return (
            False,
            "Source title and extracted page "
            "do not match strongly enough."
        )

    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""
Validate this source.

SEARCH TITLE:
{title}

URL:
{url}

CONTENT:
{source_text[:9000]}

Return VALID only if this is clearly
the specific article represented by the title.

Return INVALID for:
- homepage
- category page
- index page
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
                    "Validate sources conservatively."
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

    return True, "Source validation passed."


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
            result.get("url", "")
        )
    ]

    if not official_candidates:
        return None

    client = Groq(api_key=GROQ_API_KEY)

    candidates = ""

    for index, result in enumerate(
        official_candidates,
        start=1,
    ):
        content = (
            result.get("content", "")
            or result.get("raw_content", "")
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

Return the number only if one clearly
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
                    "Match official sources conservatively."
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

    match = re.search(r"\d+", answer)

    if not match:
        return None

    number = int(match.group())

    if (
        number < 1
        or number > len(official_candidates)
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
    client = Groq(api_key=GROQ_API_KEY)

    official_section = ""

    if official_story and official_text:
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

DISCOVERY SOURCE:

TITLE:
{story.get('title', '')}

URL:
{story.get('url', '')}

CONTENT:
{source_text}

{official_section}

RULES:

- Use only supported facts.
- Never add facts from memory.
- Never invent dates, platforms, prices,
  modes, features or availability.
- If a date contains no year, do NOT add a year.
- If co-op is confirmed but local/online is not,
  say only "coopératif jusqu'à X joueurs".
- Never infer online or local multiplayer.
- Never infer platform availability.
- Never reinterpret branded terminology.
- If no official source exists, high-risk claims
  from secondary sources must be attributed.
- Accuracy is more important than length.
- Write natural professional French.
- No filler.
- No clickbait.
- No generic conclusion.

Return exactly:

TITLE: [headline]

EXCERPT: [20–35 word factual summary]

CATEGORY: [Actualités, Guides, Sélections, Tests & Avis]

TAGS: [3–6 comma-separated tags]

CONTENT:
[HTML only]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a conservative French "
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

    return (
        response
        .choices[0]
        .message
        .content
    )


# =========================================================
# PARSING
# =========================================================

def parse_article(text):
    text = strip_code_fences(text)

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

    content = strip_code_fences(content)

    allowed_categories = {
        "Actualités",
        "Guides",
        "Sélections",
        "Tests & Avis",
    }

    if category not in allowed_categories:
        category = "Actualités"

    return (
        title,
        excerpt,
        category,
        tags,
        content,
    )


# =========================================================
# FACT CHECK
# =========================================================

def fact_check_draft(
    title,
    excerpt,
    content,
    source_text,
    official_text="",
):
    client = Groq(api_key=GROQ_API_KEY)

    official_section = ""

    if official_text:
        official_section = f"""

OFFICIAL SOURCE:

{official_text}

"""

    prompt = f"""
You are GamerQuest's final fact-checker.

SOURCE:

{source_text}

{official_section}

TITLE:
{title}

EXCERPT:
{excerpt}

ARTICLE:
{content}

Check every material claim.

Pay special attention to:
- dates
- years
- platforms
- co-op
- local/online multiplayer
- Game Pass
- PlayStation Plus
- prices
- editions
- features
- availability
- quotes
- branded terminology

If everything is supported, return exactly:

APPROVED

If anything is unsupported, return:

REJECTED

Then explain each unsupported claim clearly.
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
    print("FACT CHECK RESULT:")
    print(verdict)

    return (
        verdict.upper().startswith("APPROVED"),
        verdict,
    )


# =========================================================
# AUTOMATIC REPAIR
# =========================================================

def repair_article(
    title,
    excerpt,
    category,
    tags,
    content,
    rejection_reason,
    story,
    source_text,
    official_text="",
):
    print("")
    print(
        "Attempting one automatic repair..."
    )

    client = Groq(api_key=GROQ_API_KEY)

    official_section = ""

    if official_text:
        official_section = f"""

OFFICIAL SOURCE:

{official_text}

"""

    prompt = f"""
You are repairing a GamerQuest article
that failed fact-checking.

SOURCE:

{source_text}

{official_section}

CURRENT TITLE:
{title}

CURRENT EXCERPT:
{excerpt}

CURRENT CATEGORY:
{category}

CURRENT TAGS:
{tags}

CURRENT ARTICLE:
{content}

FACT-CHECK REJECTION:

{rejection_reason}


TASK:

Correct ONLY the unsupported or overstated claims.

Do not add new facts.

If the problem is:
- unsupported year -> remove the year
- local/online co-op unsupported -> say only co-op
- unsupported platform -> remove it
- unsupported subscription claim -> attribute or remove
- unsupported price -> remove it
- unsupported interpretation -> use neutral wording

Keep the article useful and natural.

Return exactly:

TITLE: [corrected headline]

EXCERPT: [corrected excerpt]

CATEGORY: [Actualités, Guides, Sélections, Tests & Avis]

TAGS: [3–6 comma-separated tags]

CONTENT:
[corrected HTML article only]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "Repair only unsupported claims. "
                    "Never invent replacement facts."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.05,
    )

    repaired_text = (
        response
        .choices[0]
        .message
        .content
    )

    return parse_article(
        repaired_text
    )


# =========================================================
# SAVE DRAFT
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
    DRAFTS_FOLDER.mkdir(exist_ok=True)

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d-%H%M")

    filename = (
        DRAFTS_FOLDER
        / f"{timestamp}-{slugify(title)}.md"
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
    print("APPROVED DRAFT CREATED:")
    print(filename)


# =========================================================
# SAVE REJECTION REPORT
# =========================================================

def save_rejection_report(
    stage,
    reason,
    story=None,
):
    REJECTED_FOLDER.mkdir(exist_ok=True)

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d-%H%M%S")

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
    print("Rejection report saved:")
    print(filename)


# =========================================================
# MAIN
# =========================================================

def main():
    print("")
    print("==============================")
    print("GamerQuest Automation")
    print("==============================")

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

        return

    official_story = (
        find_matching_official_source(
            story,
            results,
        )
    )

    official_text = ""

    if official_story:
        official_text = extract_page(
            official_story
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

    # =====================================================
    # ONE REPAIR ATTEMPT
    # =====================================================

    if not approved:
        print("")
        print(
            "First draft rejected. "
            "Starting automatic repair."
        )

        (
            title,
            excerpt,
            category,
            tags,
            content,
        ) = repair_article(
            title,
            excerpt,
            category,
            tags,
            content,
            verdict,
            story,
            source_text,
            official_text,
        )

        approved, second_verdict = (
            fact_check_draft(
                title,
                excerpt,
                content,
                source_text,
                official_text,
            )
        )

        if not approved:
            save_rejection_report(
                "FACT CHECK AFTER REPAIR",
                second_verdict,
                story,
            )

            print("")
            print(
                "Repair failed. "
                "Nothing saved to drafts."
            )

            return

        print("")
        print(
            "Repair passed fact-check."
        )

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
