import os
import requests
import feedparser
from requests.auth import HTTPBasicAuth

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
WP_URL = os.environ["WP_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

# First test source
RSS_URL = "https://blog.playstation.com/feed/"

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


def generate_article(story):
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
- Rewrite everything originally. Do not copy source paragraphs.
- Write for French gamers.
- Use a clear journalistic tone.
- 500 to 800 words maximum.
- Use short paragraphs.
- Include useful H2 headings.
- No fake quotes.
- No exaggerated clickbait.
- Mention the original source naturally at the end.

Return exactly this format:

TITLE: [article title]

EXCERPT: [one short SEO-friendly summary]

CONTENT:
[full article in HTML using <h2>, <p>, <strong>, <ul>, <li> where useful]
"""

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "qwen/qwen3-32b",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a careful gaming journalist who never invents facts.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.4,
        },
        timeout=120,
    )

    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]


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


def create_wordpress_draft(title, excerpt, content):
    endpoint = f"{WP_URL}/wp-json/wp/v2/posts"

    response = requests.post(
        endpoint,
        auth=HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD),
        json={
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": "draft",
        },
        timeout=120,
    )

    response.raise_for_status()

    post = response.json()

    print("Draft created successfully.")
    print("Post ID:", post["id"])
    print("Edit URL:", f"{WP_URL}/wp-admin/post.php?post={post['id']}&action=edit")


def main():
    story = get_latest_story()

    print("Source:", story["title"])

    generated = generate_article(story)

    title, excerpt, content = parse_article(generated)

    create_wordpress_draft(title, excerpt, content)


if __name__ == "__main__":
    main()
