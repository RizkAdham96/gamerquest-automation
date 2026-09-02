import json
from pathlib import Path

HISTORY_FILE = Path("social_history.json")


def load_history():
    if not HISTORY_FILE.exists():
        return []

    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        return []

    except (json.JSONDecodeError, OSError):
        return []


def save_history(history):
    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)


def add_post_to_history(post):
    history = load_history()
    history.append(post)
    save_history(history)


def get_recent_history(limit=20):
    history = load_history()

    if limit <= 0:
        return []

    return history[-limit:]
