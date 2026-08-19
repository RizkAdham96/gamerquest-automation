import os
import re
from datetime import datetime

import feedparser
from groq import Groq


# =========================
# CONFIGURATION
# =========================

GROQ_API_KEY = os.environ["GROQ_API_KEY"]

RSS_URL = "https://blog.playstation.com/feed/"


# =========================
# GET LATEST GAMING NEWS
# =========================

def get_latest_story():
    feed = feedparser.parse(RSS_URL)

    if not feed.entries:
        raise RuntimeError("No RSS entries found.")

    entry = feed.entries[0]

    return {
        "title": entry.get("title", ""),
        "link": entry.get("link", ""),
        "summary": entry.get("summary", ""),
    }


# =========================
# GENERATE ARTICLE WITH GROQ
# =========================

def generate_article(story):
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""
You are an editor for GamerQuest FR, an independent French gaming website.

Using ONLY the source information below, write an original French gaming news article.

SOURCE TITLE:
{story['title']}

SOURCE SUMMARY:
{story['summary']}

SOURCE URL:
{story['link']}

Requirements:

- Write in French.
- Do not invent facts.
- Do not claim information not present in the source.
- Rewrite everything originally.
- Do not copy source paragraphs.
- Write for French gamers.
- Use a clear journalistic tone.
- Use short paragraphs.
- Include useful H2 headings.
- No fake quotes.
- No exaggerated clickbait.
- Mention the original source naturally at the end.

Return exactly this format:

TITLE: [article title]

EXCERPT: [short SEO-friendly description]

CONTENT:
[full article in HTML using <h2>, <p>, <strong>, <ul>, <li> where useful]
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": "You are a careful gaming journalist. Never invent facts."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.4,
    )

    return response.choices[0].message.content


# =========================
# PARSE GROQ RESPONSE
# =========================

def parse_article(text):
    title = ""
    excerpt = ""
    content = ""

    if "TITLE:" in text:
        title = text.split("TITLE:", 1)[1].split("EXCERPT:", 1)[0].strip()

    if "EXCERPT:" in text:
        excerpt = text.split("EXCERPT:", 1)[1].split("CONTENT:", 1)[0].strip()

    if "CONTENT:" in text:
        content = text.split("CONTENT:", 1)[1].strip()

    if not title or not content:
        raise RuntimeError("Groq response could not be parsed.")

    return title, excerpt, content


# =========================
# CREATE SAFE FILE NAME
# =========================

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)

    return text[:80]


# =========================
# SAVE ARTICLE TO GITHUB FILE
# =========================

def save_draft(title, excerpt, content, source_url):
    os.makedirs("drafts", exist_ok=True)

    date_str = datetime.utcnow().strftime("%Y-%m-%d-%H%M")
    slug = slugify(title)

    filename = f"drafts/{date_str}-{slug}.md"

    markdown = f"""# {title}

## Excerpt

{excerpt}

## Article

{content}

## Source

{source_url}

## Status

DRAFT - REVIEW BEFORE PUBLISHING
"""

    with open(filename, "w", encoding="utf-8") as file:
        file.write(markdown)

    print("Draft saved successfully.")
    print("File:", filename)


# =========================
# RUN AUTOMATION
# =========================

def main():
    print("Getting latest gaming news...")

    story = get_latest_story()

    print("Found:")
    print(story["title"])

    print("Generating French article with Groq...")

    generated_article = generate_article(story)

    print("Article generated.")

    title, excerpt, content = parse_article(generated_article)

    print("Saving draft to GitHub repository...")

    save_draft(
        title,
        excerpt,
        content,
        story["link"]
    )

    print("Done.")


if __name__ == "__main__":
    main()
