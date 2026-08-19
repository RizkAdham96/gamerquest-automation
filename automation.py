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

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# HARD LIMIT:
# This script contains exactly ONE Tavily search request.
MAX_TAVILY_SEARCHES_PER_RUN = 1

SEARCH_QUERY = """
latest important video game news today
game announcements releases updates hardware
PlayStation Xbox Nintendo PC Steam
developers publishers gaming industry
"""


# =========================================================
# TRUSTED / OFFICIAL DOMAIN HELPERS
# =========================================================

OFFICIAL_DOMAIN_KEYWORDS = [
    "playstation.com",
    "xbox.com",
    "nintendo.com",
    "steampowered.com",
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
        official in domain
        for official in OFFICIAL_DOMAIN_KEYWORDS
    )


# =========================================================
# DUPLICATE CHECK
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

        except Exception as error:
            print(
                f"Could not read {draft_file}: {error}"
            )

    return False


def get_recent_source_domains():
    if not DRAFTS_FOLDER.exists():
        return []

    domains = []

    files = sorted(
        DRAFTS_FOLDER.glob("*.md"),
        reverse=True
    )

    for draft_file in files[:10]:
        try:
            text = draft_file.read_text(
                encoding="utf-8"
            )

            urls = re.findall(
                r'https?://[^\s<>"\']+',
                text
            )

            for url in urls:
                domain = get_domain(url)

                if domain and domain not in domains:
                    domains.append(domain)

        except Exception:
            continue

    return domains[:8]


# =========================================================
# SINGLE TAVILY SEARCH
# =========================================================

def search_gaming_news():

    print("")
    print("===================================")
    print("Searching gaming news")
    print("Tavily hard limit: 1 search")
    print("===================================")

    response = requests.post(
        TAVILY_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {TAVILY_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "query": SEARCH_QUERY,

            # IMPORTANT:
            # Basic search = 1 credit.
            "search_depth": "basic",

            "topic": "news",

            # Recent news only.
            "time_range": "day",

            # Get several candidates from ONE search.
            "max_results": 15,

            # Tavily should not generate an AI answer.
            "include_answer": False,

            # Give us article text where possible.
            "include_raw_content": "text",

            # Prevent Tavily automatically changing
            # our search configuration.
            "auto_parameters": False,
        },
        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    results = data.get("results", [])

    if not results:
        print("No gaming news found.")
        sys.exit(0)

    print(
        f"Found {len(results)} candidate stories."
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
        print(
            "All returned stories have already been used."
        )
        sys.exit(0)

    return clean_results


# =========================================================
# SELECT STORY
# =========================================================

def select_best_story(results):

    client = Groq(api_key=GROQ_API_KEY)

    recent_domains = get_recent_source_domains()

    candidates = ""

    for index, result in enumerate(results, start=1):

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

CONTENT:
{content[:2000]}

OFFICIAL SOURCE:
{"YES" if looks_official(result.get('url', '')) else "NO"}

-------------------------------------

"""

    prompt = f"""
You are the editor-in-chief of GamerQuest FR.

Choose ONE gaming-news story worth publishing.

Recently used domains:

{recent_domains}

Stories:

{candidates}


RULES:

Choose the story with the highest combination of:

1. News importance
2. Recency
3. Interest for gamers
4. Amount of concrete factual information
5. Reliability of source
6. Originality compared with recent GamerQuest stories


IMPORTANT:

Do NOT automatically select PlayStation.

Do NOT automatically select an official source.

A reputable publication may be the discovery source.

Prefer:

- major game announcements
- major updates
- release announcements
- new gameplay information
- hardware
- acquisitions
- gaming-industry developments
- major trailers
- major DLC
- release dates


Avoid:

- rumors
- leaks
- affiliate articles
- SEO spam
- opinion pieces
- weak listicles
- tiny patches
- stories with almost no factual information


SOURCE DIVERSITY:

If two stories are equally strong,
prefer the source/domain GamerQuest
has used less recently.


Return ONLY the candidate number.

Example:

4
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content":
                    "You are a rigorous gaming-news editor."
            },
            {
                "role": "user",
                "content": prompt
            }
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
            f"Could not understand selection: {answer}"
        )

    number = int(match.group())

    if number < 1 or number > len(results):
        raise RuntimeError(
            "Groq selected invalid candidate."
        )

    story = results[number - 1]

    print("")
    print("Selected story:")
    print(story.get("title", ""))
    print(story.get("url", ""))

    return story


# =========================================================
# LOOK FOR MATCHING OFFICIAL SOURCE
# INSIDE THE SAME TAVILY RESULTS
# =========================================================

def find_official_candidate(selected_story, all_results):

    selected_title = selected_story.get(
        "title",
        ""
    )

    official_candidates = []

    for result in all_results:

        if not looks_official(
            result.get("url", "")
        ):
            continue

        official_candidates.append(result)

    if not official_candidates:
        return None

    client = Groq(api_key=GROQ_API_KEY)

    candidate_text = ""

    for index, result in enumerate(
        official_candidates,
        start=1
    ):

        candidate_text += f"""

{index}

TITLE:
{result.get('title', '')}

URL:
{result.get('url', '')}

CONTENT:
{result.get('content', '')[:1200]}

"""

    prompt = f"""
Selected news story:

{selected_title}

Below are official-source pages that happened
to appear in the SAME search results.

Determine whether one of them clearly refers
to the SAME announcement or event.

{candidate_text}

If there is a clear match, return its number.

If NONE clearly matches, return:

NONE

Do not guess.
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content":
                    "Match sources conservatively."
            },
            {
                "role": "user",
                "content": prompt
            }
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

    return official_candidates[number - 1]


# =========================================================
# EXTRACT PAGE
# =========================================================

def extract_page(story):

    raw_content = (
        story.get("raw_content", "")
        or ""
    )

    if len(raw_content) >= 1000:
        return raw_content[:30000]

    try:

        response = requests.get(
            story["url"],
            timeout=30,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(compatible; GamerQuestFR/1.0)"
            }
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for element in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "noscript"
        ]):
            element.decompose()

        article = soup.find("article")

        if article:
            text = article.get_text(
                separator="\n",
                strip=True
            )
        else:
            text = soup.get_text(
                separator="\n",
                strip=True
            )

        return text[:30000]

    except Exception as error:

        print(
            f"Direct extraction failed: {error}"
        )

        return story.get("content", "")[:10000]


# =========================================================
# GENERATE VERIFIED ARTICLE
# =========================================================

def generate_article(
    story,
    official_story=None
):

    client = Groq(api_key=GROQ_API_KEY)

    discovery_content = extract_page(story)

    official_content = ""

    if official_story:

        print("")
        print(
            "Matching official source found:"
        )

        print(
            official_story.get("url", "")
        )

        official_content = extract_page(
            official_story
        )

    else:

        print("")
        print(
            "No matching official source found "
            "inside the single search."
        )

        print(
            "Using conservative single-source mode."
        )


    official_section = ""

    if official_story:

        official_section = f"""

PRIMARY / OFFICIAL SOURCE:

TITLE:
{official_story.get('title', '')}

URL:
{official_story.get('url', '')}

CONTENT:
{official_content}

"""


    prompt = f"""
You are a senior journalist for GamerQuest FR.

Create an original French gaming-news article.

DISCOVERY SOURCE:

TITLE:
{story.get('title', '')}

URL:
{story.get('url', '')}

DATE:
{story.get('published_date', '')}

CONTENT:
{discovery_content}


{official_section}


================================================
FACT-CHECKING RULES
================================================

The most important requirement is FACTUAL ACCURACY.

If an official source is supplied:

Use the official source as the authority for:

- release dates
- early-access dates
- platforms
- prices
- editions
- game features
- names
- specifications
- availability
- cover athletes
- developers
- publishers

If the discovery source conflicts
with the official source:

USE THE OFFICIAL SOURCE.


If NO official source is supplied:

Be extremely conservative.

Only state information clearly supported
by the discovery source.

Do NOT fill missing information
using your memory.


================================================
NEVER INVENT
================================================

Never invent:

- release dates
- prices
- platforms
- gameplay features
- quotes
- technical specifications
- player reactions
- reviews
- impressions
- availability
- sales numbers
- developer intentions
- geographic availability


================================================
INTERPRETATION SAFETY
================================================

Do NOT guess the meaning of branded
gameplay terminology.

For example:

If a feature is called:

"Cap Breakers"

do NOT reinterpret it as:

"salary-cap management"

unless the supplied sources explicitly
say that.

When uncertain, retain the official
English feature name and describe only
what the source confirms.


================================================
WRITING RULES
================================================

Write in professional natural French.

Do not translate mechanically.

Do not copy source paragraphs.

No clickbait.

No filler.

No generic conclusion.

No fake impressions.

No unsupported adjectives.

Preserve official product names.

Use short paragraphs.

Use meaningful H2 headings.

Use bullet lists where useful.

Normally write 400–700 words.

If there is not enough reliable information,
write 250–400 words instead.

SHORT AND ACCURATE IS BETTER THAN
LONG AND WRONG.


================================================
SOURCE TRANSPARENCY
================================================

At the end of the article,
mention the discovery source.

If an official source was used,
mention it as the primary verification source.


================================================
OUTPUT
================================================

Return EXACTLY:

TITLE: [headline]

EXCERPT: [20–35 word factual summary]

CATEGORY: [Actualités, Guides, Sélections, Tests & Avis]

TAGS: [3–6 comma-separated tags]

CONTENT:
[HTML article]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content":
                    "You are a rigorous French gaming "
                    "journalist and fact-checker. "
                    "Accuracy always beats completeness."
            },
            {
                "role": "user",
                "content": prompt
            }
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
# PARSE
# =========================================================

def parse_article(text):

    try:

        title = (
            text.split("TITLE:", 1)[1]
            .split("EXCERPT:", 1)[0]
            .strip()
        )

        excerpt = (
            text.split("EXCERPT:", 1)[1]
            .split("CATEGORY:", 1)[0]
            .strip()
        )

        category = (
            text.split("CATEGORY:", 1)[1]
            .split("TAGS:", 1)[0]
            .strip()
        )

        tags = (
            text.split("TAGS:", 1)[1]
            .split("CONTENT:", 1)[0]
            .strip()
        )

        content = (
            text.split("CONTENT:", 1)[1]
            .strip()
        )

    except Exception:

        raise RuntimeError(
            "Generated article could not be parsed."
        )

    if not title or not content:
        raise RuntimeError(
            "Generated article missing required fields."
        )

    return (
        title,
        excerpt,
        category,
        tags,
        content
    )


# =========================================================
# SLUG
# =========================================================

def slugify(text):

    text = text.lower()

    text = re.sub(
        r"[^\w\s-]",
        "",
        text
    )

    text = re.sub(
        r"[\s_-]+",
        "-",
        text
    )

    return text.strip("-")[:80]


# =========================================================
# SAVE
# =========================================================

def save_draft(
    title,
    excerpt,
    category,
    tags,
    content,
    story,
    official_story=None
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


    verification_section = """

## Verification

No matching official primary source was found in the search results.

"""

    if official_story:

        verification_section = f"""

## Official verification source

{official_story.get('title', '')}

{official_story.get('url', '')}

"""


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
{verification_section}
## Status

DRAFT - HUMAN REVIEW REQUIRED BEFORE PUBLISHING
"""

    filename.write_text(
        markdown,
        encoding="utf-8"
    )

    print("")
    print("===================================")
    print("DRAFT CREATED")
    print("===================================")
    print(filename)


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print("===================================")
    print("GamerQuest News Automation")
    print("===================================")

    print(
        "Tavily searches allowed this run: "
        f"{MAX_TAVILY_SEARCHES_PER_RUN}"
    )

    # ONLY TAVILY SEARCH IN THE SCRIPT
    results = search_gaming_news()

    story = select_best_story(
        results
    )

    official_story = find_official_candidate(
        story,
        results
    )

    generated = generate_article(
        story,
        official_story
    )

    (
        title,
        excerpt,
        category,
        tags,
        content
    ) = parse_article(
        generated
    )

    save_draft(
        title,
        excerpt,
        category,
        tags,
        content,
        story,
        official_story
    )

    print("")
    print(
        "Automation completed successfully."
    )


if __name__ == "__main__":
    main()
