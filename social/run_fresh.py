import json
import re
from pathlib import Path
from urllib.parse import urlparse

from social import run as social_run
from social.render_fallback import resolve_featured_images


PUBLISH_HISTORY_FILE = Path("social/publish_history.json")
GENERIC_VISUAL_TERMS = {
    "actualites", "annonce", "annonces", "direct", "game", "gaming", "jeux",
    "news", "nintendo", "playstation", "septembre", "switch", "xbox",
}


def load_publish_history():
    if not PUBLISH_HISTORY_FILE.exists():
        return {}
    try:
        data = json.loads(PUBLISH_HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def filter_already_published(content, publish_history):
    fresh = []
    for item in content:
        source_id = str(item.get("source_id", "")).strip()
        state = publish_history.get(source_id, {}) if source_id else {}
        instagram = state.get("instagram", {}) if isinstance(state, dict) else {}
        if instagram.get("published") is True:
            print(f"Skipping Instagram-published source: {source_id}")
            continue
        fresh.append(item)
    return fresh


def _tokens(value):
    return {
        token.lower()
        for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", str(value or ""))
        if len(token) >= 4
    }


def _visual_terms(item):
    terms = _tokens(item.get("title", ""))
    tags = item.get("tags", [])
    if isinstance(tags, list):
        for tag in tags:
            terms.update(_tokens(tag))
    return terms - GENERIC_VISUAL_TERMS


def _image_terms(url):
    parsed = urlparse(str(url or ""))
    return _tokens(f"{parsed.netloc} {parsed.path}") - GENERIC_VISUAL_TERMS


def images_match_source_topic(item, images):
    """Reject carousels whose resolved images visibly describe unrelated games/topics."""
    if not isinstance(item, dict) or len(images) != 3:
        return False

    source_terms = _visual_terms(item)
    if not source_terms:
        return False

    # Slide 1 is our article/featured visual. Slides 2-3 are external source visuals
    # and must carry at least one specific term from this exact article's topic.
    for image_url in images[1:]:
        if not (source_terms & _image_terms(image_url)):
            return False
    return True


def filter_renderable_sources(content, image_resolver=resolve_featured_images):
    """Keep only fresh sources that can produce 3 unique, topic-coherent visuals."""
    renderable = []
    for item in content:
        source_id = str(item.get("source_id", "")).strip()
        if not source_id:
            continue
        try:
            images = image_resolver(source_id, content_items=content)
        except Exception as exc:
            print(f"Skipping source without 3 usable visuals: {source_id} ({exc})")
            continue
        if len(images) != 3 or len(set(images)) != 3:
            print(f"Skipping source without 3 unique visuals: {source_id}")
            continue
        if not images_match_source_topic(item, images):
            print(f"Skipping source with mixed-topic visuals: {source_id}")
            continue
        renderable.append(item)
    return renderable


def run():
    original_get_all_content = social_run.get_all_content
    publish_history = load_publish_history()

    def get_fresh_content():
        content = original_get_all_content()
        fresh = filter_already_published(content, publish_history)
        renderable = filter_renderable_sources(fresh)
        print(f"Fresh social content items: {len(fresh)}/{len(content)}")
        print(f"Fresh renderable social items: {len(renderable)}/{len(fresh)}")
        return renderable

    social_run.get_all_content = get_fresh_content
    try:
        return social_run.run()
    finally:
        social_run.get_all_content = original_get_all_content


if __name__ == "__main__":
    run()
