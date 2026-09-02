import json

from social.ai_client import call_grok
from social.config import SOCIAL_FORMATS
from social.history import get_recent_history


def build_prompt(content):
    recent_history = get_recent_history(20)

    content_sample = content[:12]

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

Allowed formats:
{json.dumps(SOCIAL_FORMATS, ensure_ascii=False)}

Recent social history to avoid repeating:
{json.dumps(recent_history, ensure_ascii=False, indent=2)}

Available GamerQuest content:
{json.dumps(content_sample, ensure_ascii=False, indent=2)}

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
    "caption": "Instagram/Facebook caption",
    "cta": "specific CTA encouraging a visit to GamerQuest.fr"
  }}
]

Rules:
- Scores must be integers from 0 to 10.
- Each carousel must contain 4 to 7 slides.
- Slide copy must be concise.
- Hooks should be understandable immediately.
- Every candidate must use a genuinely different concept.
"""

    return prompt.strip()


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
