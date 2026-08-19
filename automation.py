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

# Hard limit: exactly ONE Tavily search per workflow run.
MAX_TAVILY_SEARCHES_PER_RUN = 1

SEARCH_QUERY = (
    "latest important video game news today "
    "game announcements releases updates hardware "
    "PlayStation Xbox Nintendo PC Steam "
    "developers publishers gaming industry"
)

MIN_SOURCE_TEXT_LENGTH = 800
MAX_SOURCE_TEXT_LENGTH = 30000


# =========================================================
# BASIC HELPERS
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


def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text[:80]


def normalize_words(text):
    words = re.findall(
        r"[a-zA-Z0-9À-ÿ]+",
        text.lower()
    )

    stopwords = {
        "the", "a", "an", "and", "or", "of", "for", "to",
        "in", "on", "with", "from", "is", "are", "new",
        "game", "games", "video", "news", "update"
    }

    return [
        word
        for word in words
        if len(word) >= 3 and word not in stopwords
    ]


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
# TAVILY SEARCH
# =========================================================

def search_gaming_news():
    print("")
    print("===================================")
    print("GamerQuest Internet Discovery")
    print("===================================")
    print("Tavily searches this run: 1")

    response = requests.post(
        TAVILY_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {TAVILY_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "query": SEARCH_QUERY,

            # Keep this Basic to minimize Tavily credit use.
            "search_depth": "basic",

            "topic": "news",

            # Search recent stories.
            "time_range": "day",

            # Multiple candidates from one search request.
            "max_results": 15,

            "include_answer": False,

            # Useful because it may give us page content
            # without another Tavily request.
            "include_raw_content": "text",

            # Never allow Tavily to auto-upgrade depth.
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
                f"Skipping duplicate: {title}"
            )
            continue

        clean_results.append(result)

    if not clean_results:
        print(
            "All search results were already processed."
        )
        sys.exit(0)

    return clean_results


# =========================================================
# STORY SELECTION
# =========================================================

def select_best_story(results):
    client = Groq(api_key=GROQ_API_KEY)

    recent_domains = get_recent_source_domains()

    candidates_text = ""

    for index, result in enumerate(
        results,
        start=1
    ):
        content = (
            result.get("content", "")
            or result.get("raw_content", "")
            or ""
        )

        candidates_text += f"""
CANDIDATE {index}

TITLE:
{result.get('title', '')}

DOMAIN:
{get_domain(result.get('url', ''))}

URL:
{result.get('url', '')}

PUBLISHED:
{result.get('published_date', '')}

CONTENT:
{content[:1800]}

---------------------------------
"""

    prompt = f"""
You are the editor-in-chief of GamerQuest FR.

Choose ONE story that is worth covering today
for a French gaming audience.

RECENTLY USED DOMAINS:
{recent_domains}

CANDIDATES:
{candidates_text}

RULES:

- The story must genuinely concern gaming.
- Prefer major announcements, releases, updates,
  hardware, acquisitions, important trailers,
  substantial DLC or meaningful industry news.
- Prefer sources that appear to link directly
  to a specific article, not a homepage.
- Prefer reputable or official sources.
- Reject SEO spam, affiliate spam, scraped content,
  low-quality blogs and obvious clickbait.
- Avoid rumors and leaks unless clearly labelled
  and genuinely important.
- Prefer recent stories.
- Prefer source diversity.
- If two stories are similar in quality,
  prefer a domain GamerQuest has used less recently.
- Do not automatically pick PlayStation.

Return ONLY the candidate number.
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict gaming news editor."
                )
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
            f"Could not parse selection: {answer}"
        )

    number = int(match.group())

    if number < 1 or number > len(results):
        raise RuntimeError(
            "Groq selected an invalid candidate."
        )

    selected = results[number - 1]

    print("")
    print("Selected candidate:")
    print(selected.get("title", ""))
    print(selected.get("url", ""))

    return selected


# =========================================================
# SOURCE EXTRACTION
# =========================================================

def extract_page(story):
    raw_content = (
        story.get("raw_content", "")
        or ""
    )

    if len(raw_content) >= MIN_SOURCE_TEXT_LENGTH:
        print(
            "Using raw content returned by Tavily."
        )

        return raw_content[:MAX_SOURCE_TEXT_LENGTH]

    print(
        "Fetching selected page directly..."
    )

    response = requests.get(
        story["url"],
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; GamerQuestFR/1.0; "
                "editorial research)"
            )
        },
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
        "noscript",
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

    return text[:MAX_SOURCE_TEXT_LENGTH]


# =========================================================
# SOURCE VALIDATION GATE
# =========================================================

def validate_source(story, source_text):
    print("")
    print("Validating source...")

    url = story.get("url", "").strip()
    title = story.get("title", "").strip()

    parsed = urlparse(url)

    path = parsed.path.strip("/")

    # Reject obvious homepages.
    if not path:
        print(
            "SOURCE REJECTED: homepage URL."
        )
        return False

    # Reject extremely generic paths.
    generic_paths = {
        "news",
        "gaming",
        "games",
        "articles",
        "latest",
        "home",
    }

    if path.lower() in generic_paths:
        print(
            "SOURCE REJECTED: generic landing page."
        )
        return False

    if len(source_text) < MIN_SOURCE_TEXT_LENGTH:
        print(
            "SOURCE REJECTED: extracted content too short."
        )
        return False

    # Compare meaningful title words against source body.
    title_words = normalize_words(title)

    if not title_words:
        print(
            "SOURCE REJECTED: could not identify title keywords."
        )
        return False

    body_lower = source_text.lower()

    matched_words = sum(
        1
        for word in set(title_words)
        if word in body_lower
    )

    match_ratio = (
        matched_words
        / max(len(set(title_words)), 1)
    )

    print(
        f"Title/body keyword match: "
        f"{match_ratio:.2f}"
    )

    if match_ratio < 0.35:
        print(
            "SOURCE REJECTED: title and page body "
            "do not match strongly enough."
        )
        return False

    # AI semantic validation.
    client = Groq(api_key=GROQ_API_KEY)

    validation_prompt = f"""
You are validating a source page before a journalist
is allowed to write an article.

SEARCH RESULT TITLE:
{title}

URL:
{url}

EXTRACTED PAGE CONTENT:
{source_text[:8000]}

Determine whether this extracted page is clearly
the specific article/story represented by the title.

Reject if:
- it is a homepage
- category page
- general news index
- unrelated page
- multiple unrelated stories are mixed together
- the title and content do not describe the same story
- the extracted page is too ambiguous

Return exactly one word:

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
                )
            },
            {
                "role": "user",
                "content": validation_prompt
            }
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

    print(
        f"AI source validation verdict: {verdict}"
    )

    if verdict != "VALID":
        print(
            "SOURCE REJECTED by semantic validation."
        )
        return False

    print(
        "SOURCE VALIDATED."
    )

    return True


# =========================================================
# ARTICLE GENERATION
# =========================================================

def generate_article(story, source_text):
    print("")
    print(
        "Generating GamerQuest article..."
    )

    client = Groq(api_key=GROQ_API_KEY)

    source_domain = get_domain(
        story.get("url", "")
    )

    prompt = f"""
You are a rigorous journalist for GamerQuest FR.

Write an ORIGINAL French gaming-news article
based ONLY on the source below.

SOURCE TITLE:
{story.get('title', '')}

SOURCE DOMAIN:
{source_domain}

SOURCE URL:
{story.get('url', '')}

SOURCE DATE:
{story.get('published_date', '')}

FULL SOURCE:
{source_text}


STRICT FACTUAL RULES:

1. Use ONLY facts explicitly supported by the source.

2. Never add information from memory.

3. Never invent:
   - release dates
   - platforms
   - prices
   - multiplayer modes
   - gameplay features
   - quotes
   - sales figures
   - reviews
   - player reactions
   - technical specifications
   - developer intentions
   - geographic availability

4. If something is unclear, OMIT it.

5. Preserve exact named facts:
   games, characters, developers, features,
   modes, hardware, platforms and dates.

6. Do not reinterpret branded terminology.

7. If the source says "single-player",
   never transform it into multiplayer.

8. If the source does not mention multiplayer,
   do not claim multiplayer exists.

9. If the source does not mention a release date,
   do not say there is or is not one.

10. If the source is thin,
    write a shorter article rather than padding.

11. Do not copy source paragraphs.

12. Write natural professional French.

13. No clickbait.

14. No generic filler conclusions.

15. Use meaningful H2 headings.

16. Mention and link the source at the end.

17. Accuracy is more important than completeness.


OUTPUT EXACTLY:

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
                "content": (
                    "You are a conservative French gaming "
                    "journalist. Never invent missing facts."
                )
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
# PARSE GENERATED ARTICLE
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

    if not title or not excerpt or not content:
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
# FACT-CHECK GATE
# =========================================================

def fact_check_draft(
    title,
    excerpt,
    category,
    tags,
    content,
    story,
    source_text
):
    print("")
    print(
        "Running final fact-check..."
    )

    client = Groq(api_key=GROQ_API_KEY)

    fact_check_prompt = f"""
You are a strict fact-checker.

Compare the GENERATED DRAFT against the SOURCE.

SOURCE:
{source_text[:18000]}

SOURCE URL:
{story.get('url', '')}

GENERATED TITLE:
{title}

GENERATED EXCERPT:
{excerpt}

GENERATED ARTICLE:
{content}


Check for any unsupported factual claim,
including:

- wrong release dates
- wrong platforms
- invented multiplayer
- invented single-player
- invented prices
- invented quotes
- invented features
- invented game modes
- invented specifications
- invented availability
- incorrect interpretation of terminology
- statements that are stronger than the source supports


If EVERY material factual claim is supported,
return exactly:

APPROVED


If ANY material factual claim is unsupported,
return:

REJECTED

Then on the next lines briefly list
the unsupported claims.

Do not approve a draft just because it
sounds plausible.
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an extremely conservative "
                    "fact-checker."
                )
            },
            {
                "role": "user",
                "content": fact_check_prompt
            }
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
        "FACT-CHECK RESULT:"
    )

    print(
        verdict
    )

    if not verdict.upper().startswith(
        "APPROVED"
    ):
        return False

    return True


# =========================================================
# SAVE APPROVED DRAFT
# =========================================================

def save_draft(
    title,
    excerpt,
    category,
    tags,
    content,
    story
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

## Validation

Source validation: PASSED

Fact-check: PASSED

## Status

DRAFT - HUMAN REVIEW REQUIRED BEFORE PUBLISHING
"""

    filename.write_text(
        markdown,
        encoding="utf-8"
    )

    print("")
    print(
        "APPROVED DRAFT SAVED:"
    )

    print(
        filename
    )


# =========================================================
# MAIN
# =========================================================

def main():
    print("")
    print("===================================")
    print("GamerQuest Automation V4")
    print("===================================")

    results = search_gaming_news()

    story = select_best_story(
        results
    )

    source_text = extract_page(
        story
    )

    if not validate_source(
        story,
        source_text
    ):
        print("")
        print(
            "Automation stopped safely."
        )
        print(
            "No article was generated."
        )
        sys.exit(0)

    generated = generate_article(
        story,
        source_text
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

    approved = fact_check_draft(
        title,
        excerpt,
        category,
        tags,
        content,
        story,
        source_text
    )

    if not approved:
        print("")
        print(
            "Draft rejected by fact-check."
        )
        print(
            "Nothing will be saved."
        )
        sys.exit(0)

    save_draft(
        title,
        excerpt,
        category,
        tags,
        content,
        story
    )

    print("")
    print(
        "Automation completed successfully."
    )


if __name__ == "__main__":
    main()
