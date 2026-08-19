import os
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser
from groq import Groq


# =========================
# CONFIGURATION
# =========================

GROQ_API_KEY = os.environ["GROQ_API_KEY"]

RSS_URL = "https://blog.playstation.com/feed/"

DRAFTS_FOLDER = Path("drafts")


# =========================
# DUPLICATE CHECK
# =========================

def source_already_used(source_url):
    if not DRAFTS_FOLDER.exists():
        return False

    for draft_file in DRAFTS_FOLDER.glob("*.md"):
        try:
            content = draft_file.read_text(encoding="utf-8")

            if source_url in content:
                return True

        except Exception as error:
            print(f"Could not read {draft_file}: {error}")

    return False


# =========================
# GET LATEST UNUSED STORY
# =========================

def get_latest_story():
    feed = feedparser.parse(RSS_URL)

    if not feed.entries:
        raise RuntimeError("No RSS entries found.")

    for entry in feed.entries[:20]:

        story = {
            "title": entry.get("title", "").strip(),
            "link": entry.get("link", "").strip(),
            "summary": entry.get("summary", "").strip(),
            "published": entry.get("published", "").strip(),
        }

        if not story["link"]:
            continue

        if source_already_used(story["link"]):
            print("Skipping duplicate:")
            print(story["title"])
            continue

        return story

    raise RuntimeError(
        "No new stories found. Recent RSS stories were already processed."
    )


# =========================
# GENERATE ARTICLE
# =========================

def generate_article(story):
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""
You are the editor of GamerQuest FR, an independent French gaming publication.

Your job is to transform ONE source into a useful, accurate French gaming-news draft.

SOURCE TITLE:
{story['title']}

SOURCE SUMMARY:
{story['summary']}

SOURCE DATE:
{story['published']}

SOURCE URL:
{story['link']}

STRICT EDITORIAL RULES:

1. Use ONLY facts that are clearly present in the supplied source information.
2. Never invent:
   - reviews
   - hands-on impressions
   - player reactions
   - sales figures
   - release dates
   - technical specifications
   - availability
   - pricing
   - quotes
   - developer intentions
   unless they are explicitly supported by the source.
3. Do not write filler such as:
   - "les premiers tests montrent..."
   - "les joueurs apprécieront..."
   - "cela promet une expérience mémorable..."
   unless the source explicitly supports it.
4. Preserve concrete useful facts whenever they are available:
   - dates
   - platforms
   - regions
   - prices
   - product features
   - gameplay mechanics
   - editions
   - pre-order dates
   - developer/publisher names
5. Be precise about geography.
   If an announcement is for Southeast Asia, do not frame it as a French release.
6. Distinguish clearly between:
   - official announcement
   - trailer
   - release information
   - developer explanation
   - hands-on preview
   Never present one as another.
7. If the source is thin, write a SHORTER article.
   Never pad the article with speculation.
8. Rewrite everything originally.
   Do not reproduce source paragraphs.
9. Use natural French for a French gaming audience.
10. Keep the tone informative, neutral and useful.
11. Use short paragraphs and meaningful H2 headings.
12. Avoid exaggerated clickbait.
13. Mention the original source at the end.
14. Do not add facts from your own memory.

ARTICLE QUALITY:

- Aim for roughly 400–700 words only when the source contains enough detail.
- If not, 200–400 words is preferable to invented content.
- The introduction should immediately explain what happened and why it matters.
- Prioritize concrete information over atmosphere or generic commentary.
- Avoid repeating the same fact in multiple sections.

Return EXACTLY this format:

TITLE: [clear French headline]

EXCERPT: [one factual summary of about 20–35 words]

CONTENT:
[HTML article using <p>, <h2>, <strong>, <ul>, <li> where appropriate]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a rigorous gaming-news editor. "
                    "Accuracy is more important than article length. "
                    "Never invent missing information."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content


# =========================
# PARSE RESPONSE
# =========================

def parse_article(text):
    title = ""
    excerpt = ""
    content = ""

    if "TITLE:" in text:
        title = (
            text.split("TITLE:", 1)[1]
            .split("EXCERPT:", 1)[0]
            .strip()
        )

    if "EXCERPT:" in text:
        excerpt = (
            text.split("EXCERPT:", 1)[1]
            .split("CONTENT:", 1)[0]
            .strip()
        )

    if "CONTENT:" in text:
        content = text.split("CONTENT:", 1)[1].strip()

    if not title or not excerpt or not content:
        raise RuntimeError("Groq response could not be parsed.")

    return title, excerpt, content


# =========================
# CREATE SAFE FILE NAME
# =========================

def slugify(text):
    text = text.lower()

    text = re.sub(
        r"[^\w\s-]",
        "",
        text,
    )

    text = re.sub(
        r"[\s_-]+",
        "-",
        text,
    )

    text = re.sub(
        r"^-+|-+$",
        "",
        text,
    )

    return text[:80]


# =========================
# SAVE DRAFT
# =========================

def save_draft(title, excerpt, content, story):
    DRAFTS_FOLDER.mkdir(exist_ok=True)

    date_str = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d-%H%M")

    slug = slugify(title)

    filename = (
        DRAFTS_FOLDER
        / f"{date_str}-{slug}.md"
    )

    markdown = f"""# {title}

## Excerpt

{excerpt}

## Article

{content}

## Source title

{story['title']}

## Source

{story['link']}

## Source date

{story['published']}

## Status

DRAFT - HUMAN REVIEW REQUIRED BEFORE PUBLISHING
"""

    filename.write_text(
        markdown,
        encoding="utf-8",
    )

    print("Draft saved successfully.")
    print("File:", filename)


# =========================
# RUN
# =========================

def main():
    print("Looking for a new gaming story...")

    story = get_latest_story()

    print("Selected:")
    print(story["title"])
    print(story["link"])

    print("Generating editorial draft with Groq...")

    generated_article = generate_article(story)

    title, excerpt, content = parse_article(
        generated_article
    )

    print("Draft generated.")

    save_draft(
        title,
        excerpt,
        content,
        story,
    )

    print("Done.")


if __name__ == "__main__":
    main()
