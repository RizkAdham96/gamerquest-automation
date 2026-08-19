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

# IMPORTANT:
# Exactly ONE Tavily search per GitHub Action run.
MAX_TAVILY_SEARCHES_PER_RUN = 1

SEARCH_QUERY = (
    "latest video game news announcements releases updates "
    "PlayStation Xbox Nintendo PC Steam gaming"
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


# =========================================================
# RECENT SOURCE DOMAINS
# =========================================================

def get_recent_source_domains():
    if not DRAFTS_FOLDER.exists():
        return []

    domains = []

    files = sorted(
        DRAFTS_FOLDER.glob("*.md"),
        reverse=True
    )

    for draft_file in files[:8]:
        try:
            text = draft_file.read_text(
                encoding="utf-8"
            )

            urls = re.findall(
                r'https?://[^\s<>"\']+',
                text
            )

            for url in urls:
                domain = (
                    urlparse(url)
                    .netloc
                    .lower()
                    .replace("www.", "")
                )

                if domain and domain not in domains:
                    domains.append(domain)

        except Exception:
            continue

    return domains[:5]


# =========================================================
# ONE TAVILY SEARCH
# =========================================================

def search_gaming_news():
    searches_used_this_run = 0

    if searches_used_this_run >= MAX_TAVILY_SEARCHES_PER_RUN:
        raise RuntimeError(
            "Per-run Tavily search limit reached."
        )

    print("")
    print("Searching the web for gaming news...")
    print("Maximum Tavily searches this run: 1")

    response = requests.post(
        TAVILY_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {TAVILY_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "query": SEARCH_QUERY,

            # Basic search = lower credit usage.
            "search_depth": "basic",

            # News-focused results.
            "topic": "news",

            # Only recent stories.
            "time_range": "day",

            # Multiple candidates from one single search.
            "max_results": 10,

            # We do not need Tavily to write an answer.
            "include_answer": False,

            # Try to get page text from the same search.
            "include_raw_content": "text",

            # Prevent automatic upgrade to advanced search.
            "auto_parameters": False,
        },
        timeout=60,
    )

    searches_used_this_run += 1

    response.raise_for_status()

    data = response.json()

    results = data.get(
        "results",
        []
    )

    if not results:
        print(
            "No gaming news results found."
        )
        sys.exit(0)

    print(
        f"Tavily returned {len(results)} candidates."
    )

    new_results = []

    for result in results:
        url = (
            result.get("url", "")
            .strip()
        )

        title = (
            result.get("title", "")
            .strip()
        )

        if not url or not title:
            continue

        if source_already_used(url):
            print(
                f"Skipping duplicate: {title}"
            )
            continue

        new_results.append(
            result
        )

    if not new_results:
        print(
            "All search results were already processed."
        )
        sys.exit(0)

    return new_results


# =========================================================
# LET GROQ SELECT THE BEST STORY
# =========================================================

def select_best_story(results):
    print("")
    print(
        "Asking Groq to select the strongest "
        "story for GamerQuest..."
    )

    client = Groq(
        api_key=GROQ_API_KEY
    )

    recent_domains = (
        get_recent_source_domains()
    )

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

        content = content[:1800]

        candidates_text += f"""
CANDIDATE {index}

TITLE:
{result.get('title', '')}

URL:
{result.get('url', '')}

PUBLISHED:
{result.get('published_date', '')}

SEARCH SCORE:
{result.get('score', '')}

SUMMARY / CONTENT:
{content}

------------------------------
"""

    selection_prompt = f"""
You are the editorial news editor of GamerQuest FR.

Choose ONE story that is most worth covering today
for a French gaming audience.

RECENTLY USED SOURCE DOMAINS:
{recent_domains}

CANDIDATES:
{candidates_text}

SELECTION RULES:

- The story must genuinely concern video games,
  consoles, PC gaming, gaming hardware,
  major updates, releases or the gaming industry.

- Prefer important announcements, releases,
  major updates, significant new features,
  hardware announcements and meaningful
  gaming-industry news.

- Prefer original or official sources when available.

- Otherwise prefer established reputable
  gaming or technology publications.

- Reject SEO spam, affiliate spam,
  low-quality blogs and scraped content.

- Reject obvious clickbait.

- Avoid unverified rumors and leaks.

- Prefer recent stories.

- Prefer source diversity.

- If several stories are equally strong,
  prefer a domain GamerQuest has not used recently.

- Do NOT choose a story simply because
  PlayStation, Xbox or Nintendo published it.

- The goal is to make GamerQuest feel like
  an independent gaming publication.

Return ONLY the candidate number.

Example:

3
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful gaming news editor "
                    "selecting one story."
                )
            },
            {
                "role": "user",
                "content": selection_prompt
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

    match = re.search(
        r"\d+",
        answer
    )

    if not match:
        raise RuntimeError(
            f"Could not parse selected story: {answer}"
        )

    selected_number = int(
        match.group()
    )

    if (
        selected_number < 1
        or selected_number > len(results)
    ):
        raise RuntimeError(
            "Groq selected an invalid candidate."
        )

    selected = results[
        selected_number - 1
    ]

    print(
        f"Selected candidate {selected_number}:"
    )

    print(
        selected.get("title", "")
    )

    print(
        selected.get("url", "")
    )

    return selected


# =========================================================
# GET FULL SOURCE CONTENT
# =========================================================

def get_source_content(story):
    raw_content = (
        story.get("raw_content", "")
        or ""
    )

    if len(raw_content) >= 800:
        print(
            "Using article content returned "
            "by Tavily."
        )

        return raw_content[:25000]

    print(
        "Tavily content is limited. "
        "Fetching selected webpage directly..."
    )

    url = story["url"]

    response = requests.get(
        url,
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

    article = soup.find(
        "article"
    )

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

    text = text[:25000]

    if len(text) < 300:
        raise RuntimeError(
            "Could not extract enough source content."
        )

    return text


# =========================================================
# GENERATE GAMERQUEST ARTICLE
# =========================================================

def generate_article(story):
    print("")
    print(
        "Generating GamerQuest article..."
    )

    client = Groq(
        api_key=GROQ_API_KEY
    )

    full_source = (
        get_source_content(story)
    )

    source_domain = (
        urlparse(story["url"])
        .netloc
        .replace("www.", "")
    )

    prompt = f"""
You are the editor of GamerQuest FR,
an independent French gaming publication.

Write an ORIGINAL French gaming-news article
based ONLY on the supplied source.

SOURCE TITLE:
{story.get('title', '')}

SOURCE DOMAIN:
{source_domain}

SOURCE URL:
{story.get('url', '')}

SOURCE DATE:
{story.get('published_date', '')}

FULL SOURCE:
{full_source}


STRICT EDITORIAL RULES:

1. Use ONLY facts clearly supported
   by the supplied source.

2. Never invent:
   reviews,
   hands-on impressions,
   player reactions,
   sales figures,
   dates,
   pricing,
   platforms,
   technical specifications,
   quotes,
   availability,
   developer intentions.

3. Never add facts from your own memory.

4. Preserve concrete facts:
   names,
   dates,
   platforms,
   prices,
   regions,
   developers,
   publishers,
   game modes,
   maps,
   characters,
   vehicles,
   gameplay systems,
   hardware features.

5. If information is limited,
   write a shorter article.
   NEVER use filler.

6. Rewrite the story originally.
   Do not copy source paragraphs.

7. Write natural professional French.

8. Keep official proper names in their
   original language when appropriate.

9. Avoid exaggerated terms such as
   "révolutionnaire",
   "incroyable",
   "énorme",
   "illimité"
   unless directly justified.

10. Clearly distinguish between:
    announcement,
    launch,
    update,
    trailer,
    interview,
    preview,
    developer explanation,
    rumor.

11. Do not present rumors as facts.

12. Be geographically precise.

13. Never invent French availability.

14. Prioritize named facts over
    vague summaries.

15. Do not write generic conclusions like
    "cela promet une expérience mémorable."

16. Use meaningful H2 headings.

17. Use lists when genuinely helpful.

18. Mention and link the original
    source naturally at the end.

19. Accuracy is more important
    than article length.

20. Do not imitate the writing style
    of the source publication.

21. The finished article must provide
    useful editorial value to GamerQuest
    readers, not simply translate each
    source paragraph one by one.


ARTICLE LENGTH:

Normally 400–700 words when enough
source information exists.

Use 200–400 words when the source is thin.


RETURN EXACTLY:

TITLE: [French headline]

EXCERPT: [20–35 word factual summary]

CATEGORY: [one of: Actualités, Guides, Sélections, Tests & Avis]

TAGS: [3 to 6 comma-separated useful tags]

CONTENT:
[HTML article using <p>, <h2>, <strong>,
<ul>, <li> where appropriate]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a rigorous French gaming "
                    "journalist. Never invent facts."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2,
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
            text
            .split(
                "TITLE:",
                1
            )[1]
            .split(
                "EXCERPT:",
                1
            )[0]
            .strip()
        )

        excerpt = (
            text
            .split(
                "EXCERPT:",
                1
            )[1]
            .split(
                "CATEGORY:",
                1
            )[0]
            .strip()
        )

        category = (
            text
            .split(
                "CATEGORY:",
                1
            )[1]
            .split(
                "TAGS:",
                1
            )[0]
            .strip()
        )

        tags = (
            text
            .split(
                "TAGS:",
                1
            )[1]
            .split(
                "CONTENT:",
                1
            )[0]
            .strip()
        )

        content = (
            text
            .split(
                "CONTENT:",
                1
            )[1]
            .strip()
        )

    except Exception:
        raise RuntimeError(
            "Groq response could not be parsed."
        )

    if not title or not excerpt or not content:
        raise RuntimeError(
            "Generated article is missing required fields."
        )

    return (
        title,
        excerpt,
        category,
        tags,
        content
    )


# =========================================================
# SAFE FILE NAME
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

    text = re.sub(
        r"^-+|-+$",
        "",
        text
    )

    return text[:80]


# =========================================================
# SAVE DRAFT
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

    date_str = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d-%H%M"
    )

    slug = slugify(
        title
    )

    filename = (
        DRAFTS_FOLDER
        / f"{date_str}-{slug}.md"
    )

    source_domain = (
        urlparse(
            story["url"]
        )
        .netloc
        .replace(
            "www.",
            ""
        )
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

## Original source

{source_domain}

## Source title

{story.get('title', '')}

## Source URL

{story.get('url', '')}

## Source date

{story.get('published_date', '')}

## Status

DRAFT - HUMAN REVIEW REQUIRED BEFORE PUBLISHING
"""

    filename.write_text(
        markdown,
        encoding="utf-8"
    )

    print("")
    print(
        "Draft saved successfully:"
    )

    print(
        filename
    )


# =========================================================
# MAIN
# =========================================================

def main():
    print(
        "==================================="
    )

    print(
        "GamerQuest Internet News Automation"
    )

    print(
        "==================================="
    )

    print(
        "Maximum Tavily searches this run: "
        f"{MAX_TAVILY_SEARCHES_PER_RUN}"
    )

    results = (
        search_gaming_news()
    )

    selected_story = (
        select_best_story(
            results
        )
    )

    generated = (
        generate_article(
            selected_story
        )
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
        selected_story
    )

    print("")
    print(
        "Automation completed successfully."
    )


if __name__ == "__main__":
    main()
