import json

from social.ai_client import call_grok
from social.config import SOCIAL_FORMATS
from social.history import get_recent_history


MAX_CONTENT_ITEMS = 10
MAX_EXCERPT_CHARS = 500
MAX_PROMPT_CHARS = 16000
RECENT_HISTORY_ITEMS = 8


def _clean_text(value, limit=None):
    text = "" if value is None else str(value).strip()

    if limit is not None:
        text = text[:limit]

    return text


def _compact_history_item(item):
    if not isinstance(item, dict):
        return {}

    return {
        "topic": _clean_text(item.get("topic"), 120),
        "angle": _clean_text(item.get("angle"), 160),
        "format": _clean_text(item.get("format"), 60),
        "hook": _clean_text(item.get("hook"), 180),
        "cta": _clean_text(item.get("cta"), 180),
    }


def _content_sort_key(item):
    if not isinstance(item, dict):
        return ""

    return _clean_text(
        item.get("created_at")
        or item.get("published_at")
        or item.get("date")
    )


def prepare_content_for_ai(content):
    """Return a compact, recent and slightly balanced AI shortlist."""
    valid_items = [item for item in content if isinstance(item, dict)]

    news = sorted(
        [item for item in valid_items if item.get("source_type") != "deal"],
        key=_content_sort_key,
        reverse=True,
    )
    deals = sorted(
        [item for item in valid_items if item.get("source_type") == "deal"],
        key=_content_sort_key,
        reverse=True,
    )

    selected = news[:8] + deals[:2]

    if len(selected) < MAX_CONTENT_ITEMS:
        already_selected = {id(item) for item in selected}
        remaining = sorted(
            [item for item in valid_items if id(item) not in already_selected],
            key=_content_sort_key,
            reverse=True,
        )
        selected.extend(
            remaining[: MAX_CONTENT_ITEMS - len(selected)]
        )

    compact = []

    for item in selected[:MAX_CONTENT_ITEMS]:
        tags = item.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        compact.append(
            {
                "title": _clean_text(item.get("title"), 220),
                "excerpt": _clean_text(
                    item.get("excerpt") or item.get("description"),
                    MAX_EXCERPT_CHARS,
                ),
                "slug": _clean_text(item.get("slug"), 180),
                "category": _clean_text(item.get("category"), 80),
                "source_type": _clean_text(item.get("source_type"), 40),
                "created_at": _clean_text(item.get("created_at"), 80),
                "tags": [_clean_text(tag, 60) for tag in tags[:5]],
            }
        )

    return compact


def build_prompt(content):
    recent_history = [
        _compact_history_item(item)
        for item in get_recent_history(RECENT_HISTORY_ITEMS)
        if isinstance(item, dict)
    ]

    content_sample = prepare_content_for_ai(content)

    prompt = f"""
You are the social media creative strategist for GamerQuest.fr.

Your goal is to create high-performing Instagram/Facebook carousel ideas
that drive people to visit GamerQuest.fr.

IMPORTANT:
- Do NOT repeat recent topics, hooks, angles, formats, CTAs, or concepts.
- Do NOT invent gaming news or facts.
- Only use information available in the GamerQuest content provided below.
- Create DIFFERENT concepts, not 5 versions of the same idea.
- Prefer strong curiosity, useful information, shareability, and website-click potential.
- If the news is weak, use a stronger angle such as ranking, recommendation,
  comparison, quiz, explainer, challenge, deal alert, or discovery.
- The carousel should give value but NOT reveal everything.
- Leave a reason for the user to visit GamerQuest.fr.
- Avoid clickbait that is false or misleading.
- Write a caption that adds context instead of repeating the slides.
- The caption must include a natural reason to visit GamerQuest.fr.
- Include 3 to 6 relevant hashtags, including #GamerQuest when appropriate.

Allowed formats:
{json.dumps(SOCIAL_FORMATS, ensure_ascii=False)}

Recent social history to avoid repeating:
{json.dumps(recent_history, ensure_ascii=False)}

Available GamerQuest content shortlist:
{json.dumps(content_sample, ensure_ascii=False)}

Create exactly 5 candidate carousel ideas.

Return ONLY valid JSON.

The JSON must be an array of objects using this structure:

[
  {{
    "topic": "main topic",
    "angle": "unique creative angle",
    "format": "one allowed format",
    "hook": "strong first-slide hook",
    "freshness": 0,
    "click_potential": 0,
    "curiosity": 0,
    "shareability": 0,
    "originality": 0,
    "gamerquest_relevance": 0,
    "slides": [
      {{
        "title": "slide title",
        "body": "short slide copy",
        "visual_prompt": "description of the visual"
      }}
    ],
    "caption": "Instagram/Facebook caption that complements the slides",
    "cta": "specific CTA encouraging a visit to GamerQuest.fr",
    "hashtags": ["#GamerQuest", "#Gaming"]
  }}
]

Rules:
- Scores must be integers from 0 to 10.
- Each carousel must contain 4 to 7 slides.
- Slide copy must be concise.
- Hooks should be understandable immediately.
- Every candidate must use a genuinely different concept.
"""

    prompt = prompt.strip()

    if len(prompt) > MAX_PROMPT_CHARS:
        raise RuntimeError(
            f"Social AI prompt exceeds safe size: {len(prompt)} characters."
        )

    return prompt


def parse_json_response(raw_response):
    text = raw_response.strip()

    if text.startswith("```"):
        text = text.replace("```json", "", 1)
        text = text.replace("```", "")
        text = text.strip()

    try:
        data = json.loads(text)

    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"AI returned invalid JSON: {error}"
        ) from error

    if not isinstance(data, list):
        raise RuntimeError(
            "AI response must be a JSON array."
        )

    return data


def generate_ideas(content):
    if not content:
        return []

    prompt = build_prompt(content)

    raw_response = call_grok(prompt)

    ideas = parse_json_response(raw_response)

    return ideas[:5]
