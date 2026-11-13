"""Regenerate News featured images that came out as the blank fallback.

For each feed article whose local image in generated_news_images/ is the
plain gradient, look for real artwork (YouTube thumbnail, then official
Steam artwork) and rewrite the file. The repair job then uploads the new
file to WordPress for posts whose live image is still blank.
"""

import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from image_fallbacks import (  # noqa: E402
    steam_artwork_candidates,
    youtube_thumbnail_candidates,
)
from news_image_generator import (  # noqa: E402
    cover_image,
    download_source_image,
    image_is_blank,
)

NEWS_FEED_FILE = Path("gamerquest-news-feed.json")
NEWS_IMAGES_FOLDER = Path("generated_news_images")
MIN_WIDTH = 600


def artwork_candidates(article):
    source = article.get("source") or {}
    source_url = source.get("url", "") if isinstance(source, dict) else ""
    candidates = list(youtube_thumbnail_candidates(source_url))
    candidates += steam_artwork_candidates(article.get("title", ""))
    return candidates


def refresh_article_image(article, images_folder=NEWS_IMAGES_FOLDER, find=artwork_candidates):
    """Return the artwork URL used when the image was refreshed, else ""."""
    filename = str((article.get("featured_image") or {}).get("filename", "")).strip()
    if not filename:
        return ""
    path = Path(images_folder) / filename
    if not path.is_file():
        return ""
    with Image.open(path) as current:
        if not image_is_blank(current):
            return ""
    for url in find(article):
        image = download_source_image(url)
        if image is None or image.width < MIN_WIDTH or image_is_blank(image):
            continue
        cover_image(image).save(path, format="JPEG", quality=92, optimize=True)
        return url
    return ""


def main():
    payload = json.loads(NEWS_FEED_FILE.read_text(encoding="utf-8"))
    refreshed = 0
    for article in payload.get("articles", []):
        try:
            url = refresh_article_image(article)
        except Exception as exc:
            print(f"Refresh failed for {article.get('slug')}: {exc}")
            continue
        if url:
            refreshed += 1
            print(f"Refreshed blank image: {article.get('slug')} <- {url}")
    print(f"Blank News images refreshed: {refreshed}")


if __name__ == "__main__":
    main()
