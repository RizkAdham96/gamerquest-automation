from social.config import RECENT_POST_MEMORY, SOCIAL_FORMATS
from social.history import get_recent_history
from social.scorer import rank_ideas


def get_recent_values(history, key):
    values = []

    for item in history:
        if not isinstance(item, dict):
            continue

        value = item.get(key)

        if value:
            values.append(str(value).strip().lower())

    return values


def is_repetitive(idea, history):
    recent_formats = get_recent_values(history, "format")
    recent_topics = get_recent_values(history, "topic")
    recent_hooks = get_recent_values(history, "hook")

    idea_format = str(idea.get("format", "")).strip().lower()
    idea_topic = str(idea.get("topic", "")).strip().lower()
    idea_hook = str(idea.get("hook", "")).strip().lower()

    # Avoid using the same format twice in a row
    if recent_formats and idea_format == recent_formats[-1]:
        return True

    # Avoid recently repeated topics
    if idea_topic and idea_topic in recent_topics[-10:]:
        return True

    # Avoid repeated hooks
    if idea_hook and idea_hook in recent_hooks[-15:]:
        return True

    return False


def filter_repetitive_ideas(ideas):
    history = get_recent_history(RECENT_POST_MEMORY)

    filtered = []

    for idea in ideas:
        if not isinstance(idea, dict):
            continue

        if is_repetitive(idea, history):
            continue

        filtered.append(idea)

    return filtered


def validate_format(idea):
    idea_format = idea.get("format")

    if idea_format not in SOCIAL_FORMATS:
        idea["format"] = "explainer"

    return idea


def choose_best_idea(ideas):
    cleaned_ideas = []

    for idea in ideas:
        if isinstance(idea, dict):
            cleaned_ideas.append(validate_format(idea.copy()))

    non_repetitive = filter_repetitive_ideas(cleaned_ideas)

    if not non_repetitive:
        return None

    ranked = rank_ideas(non_repetitive)

    if not ranked:
        return None

    return ranked[0]
