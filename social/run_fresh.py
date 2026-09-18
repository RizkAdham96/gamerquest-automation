import json
from pathlib import Path

from social import run as social_run
from social.render_fallback import resolve_publishable_images


PUBLISH_HISTORY_FILE = Path("social/publish_history.json")
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


def filter_renderable_sources(content, image_resolver=resolve_publishable_images):
    """Keep only fresh sources that resolve to 3 distinct, relevant visuals."""
    renderable = []
    for item in content:
        source_id = str(item.get("source_id", "")).strip()
        if not source_id:
            continue
        try:
            # resolve_featured_images is the semantic quality gate. It still
            # has URL + alt text + article tags/title available, unlike this
            # wrapper, so relevance belongs there rather than in filename-only
            # heuristics.
            images = image_resolver(source_id, content_items=content)
        except Exception as exc:
            print(f"Skipping source without 3 usable relevant visuals: {source_id} ({exc})")
            continue
        if len(images) != 3 or len(set(images)) != 3:
            print(f"Skipping source without 3 unique visuals: {source_id}")
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
