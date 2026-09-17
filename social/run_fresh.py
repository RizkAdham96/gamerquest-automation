import json
from pathlib import Path

from social import run as social_run


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


def run():
    original_get_all_content = social_run.get_all_content
    publish_history = load_publish_history()

    def get_fresh_content():
        content = original_get_all_content()
        fresh = filter_already_published(content, publish_history)
        print(f"Fresh social content items: {len(fresh)}/{len(content)}")
        return fresh

    social_run.get_all_content = get_fresh_content
    try:
        return social_run.run()
    finally:
        social_run.get_all_content = original_get_all_content


if __name__ == "__main__":
    run()
