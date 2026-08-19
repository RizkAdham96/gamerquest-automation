import os
import requests
import feedparser

from groq import Groq
from requests.auth import HTTPBasicAuth


# =========================
# CONFIGURATION
# =========================

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
WP_URL = os.environ["WP_URL"].rstrip("/")
WP_USERNAME = os.environ["WP_USERNAME"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]

RSS_URL = "https://blog.playstation.com/feed/"


# =========================
# GET GAMING NEWS
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

EXCERPT: [short description]

CONTENT:
[article in HTML]
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
# SEPARATE TITLE / EXCERPT / ARTICLE
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
# SEND ARTICLE TO WORDPRESS
# =========================

def create_wordpress_draft(title, excerpt, content):

    endpoint = f"{WP_URL}/wp-json/wp/v2/posts"

    response = requests.post(
        endpoint,
        auth=HTTPBasicAuth(
            WP_USERNAME,
            WP_APP_PASSWORD
        ),
        json={
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": "draft",
        },
        timeout=120,
    )

    if not response.ok:
        print("WordPress response:", response.status_code)
        print(response.text[:1000])

    response.raise_for_status()

    post = response.json()

    print("SUCCESS - WordPress draft created!")
    print("Post ID:", post["id"])
    print(
        "Edit URL:",
        f"{WP_URL}/wp-admin/post.php?post={post['id']}&action=edit"
    )


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

    print("Sending article to WordPress...")

    create_wordpress_draft(
        title,
        excerpt,
        content
    )


if __name__ == "__main__":
    main()
