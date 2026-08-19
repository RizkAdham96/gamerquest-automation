import os
import re
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

import feedparser
import requests

from bs4 import BeautifulSoup
from groq import Groq


# =========================================================
# CONFIGURATION
# =========================================================

GROQ_API_KEY = os.environ["GROQ_API_KEY"]

DRAFTS_FOLDER = Path("drafts")

SOURCES = [
    {
        "name": "PlayStation Blog",
        "feed": "https://blog.playstation.com/feed/",
    },
    {
        "name": "Nintendo",
        "feed": "https://www.nintendo.co.jp/news/whatsnew.xml",
    },
]


# =========================================================
# DUPLICATE CHECK
# =========================================================

def source_already_used(source_url):

    if not DRAFTS_FOLDER.exists():
        return False

    for draft_file in DRAFTS_FOLDER.glob("*.md"):

        try:
            content = draft_file.read_text(
                encoding="utf-8"
            )

            if source_url in content:
                return True

        except Exception as error:
            print(
                f"Could not read {draft_file}: {error}"
            )

    return False


# =========================================================
# DATE PARSING
# =========================================================

def parse_date(entry):

    date_string = entry.get(
        "published",
        entry.get("updated", "")
    )

    if not date_string:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )

    try:

        parsed = parsedate_to_datetime(
            date_string
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed

    except Exception:

        return datetime.min.replace(
            tzinfo=timezone.utc
        )


# =========================================================
# COLLECT STORIES FROM ALL SOURCES
# =========================================================

def collect_stories():

    stories = []

    for source in SOURCES:

        print(
            f"Checking {source['name']}..."
        )

        feed = feedparser.parse(
            source["feed"]
        )

        if not feed.entries:

            print(
                f"No entries from {source['name']}."
            )

            continue

        for entry in feed.entries[:15]:

            link = entry.get(
                "link",
                ""
            ).strip()

            title = entry.get(
                "title",
                ""
            ).strip()

            if not link or not title:
                continue

            story = {
                "source": source["name"],
                "title": title,
                "link": link,
                "summary": entry.get(
                    "summary",
                    ""
                ).strip(),
                "published": entry.get(
                    "published",
                    entry.get(
                        "updated",
                        ""
                    )
                ).strip(),
                "date": parse_date(entry),
            }

            stories.append(story)

    return stories


# =========================================================
# SELECT NEWEST UNUSED STORY
# =========================================================

def get_latest_story():

    stories = collect_stories()

    if not stories:
        raise RuntimeError(
            "No stories found from any source."
        )

    stories.sort(
        key=lambda item: item["date"],
        reverse=True
    )

    for story in stories:

        if source_already_used(
            story["link"]
        ):

            print(
                "Skipping duplicate:"
            )

            print(
                story["title"]
            )

            continue

        return story

    raise RuntimeError(
        "No new unused stories were found."
    )


# =========================================================
# FETCH FULL ARTICLE
# =========================================================

def fetch_full_article(url):

    print(
        "Fetching full source article..."
    )

    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; GamerQuestFR/1.0)"
            )
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

    text = text[:25000]

    if len(text) < 300:

        raise RuntimeError(
            "Could not extract enough article content."
        )

    print(
        f"Extracted {len(text)} characters."
    )

    return text


# =========================================================
# GENERATE GAMERQUEST ARTICLE
# =========================================================

def generate_article(story):

    client = Groq(
        api_key=GROQ_API_KEY
    )

    full_source = fetch_full_article(
        story["link"]
    )

    prompt = f"""
You are the editor of GamerQuest FR,
an independent French gaming publication.

Create an ORIGINAL French gaming-news article
based exclusively on the source supplied below.

SOURCE:
{story['source']}

SOURCE TITLE:
{story['title']}

SOURCE DATE:
{story['published']}

SOURCE URL:
{story['link']}

RSS SUMMARY:
{story['summary']}

FULL SOURCE:
{full_source}


STRICT EDITORIAL RULES:

1. Use ONLY facts supported by the source.

2. Never invent facts, reactions, reviews,
sales numbers, dates, prices, quotes,
technical specifications or opinions.

3. Never use your own memory to add information.

4. Preserve useful concrete details:
dates, platforms, prices, game modes,
characters, developers, publishers,
vehicles, maps, features and regions.

5. If the source contains little information,
write a shorter article rather than adding filler.

6. Rewrite the information originally.
Do not copy paragraphs from the source.

7. Write natural professional French.

8. Keep official names of games, modes,
characters and branded features when necessary.

9. Avoid exaggerated wording such as
"révolutionnaire", "incroyable", "énorme",
"illimité" or similar terms unless clearly
supported by the source.

10. Clearly distinguish an announcement,
release, trailer, interview, update,
preview or developer explanation.

11. Never infer platform availability
simply because the story appears on
PlayStation, Xbox or Nintendo's website.

12. Be geographically precise.

13. Do not invent French availability
when an announcement concerns another region.

14. Prioritize named facts over vague summaries.

15. Do not write generic conclusions such as
"cela promet une expérience mémorable."

16. Use meaningful H2 sections.

17. Use bullet lists only when they genuinely
make information easier to understand.

18. Mention the original source naturally
at the end.

19. Accuracy is more important than length.


ARTICLE QUALITY:

Aim for approximately 400–700 words when
the source contains enough information.

Otherwise write 200–400 words.

The introduction should immediately explain
the news and its importance.

Avoid repetition.

Write for readers of GamerQuest FR.


RETURN EXACTLY:

TITLE: [French headline]

EXCERPT: [20–35 word factual summary]

CONTENT:
[HTML article using <p>, <h2>, <strong>,
<ul> and <li> where appropriate]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a rigorous French gaming "
                    "news editor. Accuracy is more "
                    "important than length. Never "
                    "invent missing information."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content


# =========================================================
# PARSE AI RESPONSE
# =========================================================

def parse_article(text):

    title = ""
    excerpt = ""
    content = ""

    if "TITLE:" in text:

        title = (
            text.split(
                "TITLE:",
                1
            )[1]
            .split(
                "EXCERPT:",
                1
            )[0]
            .strip()
        )

    if "EXCERPT:" in text:

        excerpt = (
            text.split(
                "EXCERPT:",
                1
            )[1]
            .split(
                "CONTENT:",
                1
            )[0]
            .strip()
        )

    if "CONTENT:" in text:

        content = (
            text.split(
                "CONTENT:",
                1
            )[1]
            .strip()
        )

    if not title or not excerpt or not content:

        raise RuntimeError(
            "Groq response could not be parsed."
        )

    return title, excerpt, content


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

    filename = (
        DRAFTS_FOLDER
        / f"{date_str}-{slugify(title)}.md"
    )

    markdown = f"""# {title}

## Excerpt

{excerpt}

## Article

{content}

## Original source

{story['source']}

## Source title

{story['title']}

## Source URL

{story['link']}

## Source date

{story['published']}

## Status

DRAFT - HUMAN REVIEW REQUIRED BEFORE PUBLISHING
"""

    filename.write_text(
        markdown,
        encoding="utf-8"
    )

    print(
        "Draft saved:"
    )

    print(
        filename
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "GamerQuest Automation V2"
    )

    story = get_latest_story()

    print(
        "\nSelected story:"
    )

    print(
        story["source"]
    )

    print(
        story["title"]
    )

    print(
        story["link"]
    )

    generated = generate_article(
        story
    )

    title, excerpt, content = (
        parse_article(
            generated
        )
    )

    save_draft(
        title,
        excerpt,
        content,
        story
    )

    print(
        "\nDone."
    )


if __name__ == "__main__":
    main()
