import json

from social.ai_client import call_grok
from social.config import SOCIAL_FORMATS
from social.history import get_recent_history


MAX_CONTENT_ITEMS = 10
MAX_EXCERPT_CHARS = 500
MAX_PROMPT_CHARS = 16000
RECENT_HISTORY_ITEMS = 8
CONCEPT_COUNT = 3

CAROUSEL_SLIDES = 3


def _clean_text(value, limit=None):
    text = "" if value is None else str(value).strip()

    if limit is not None:
        return text[:limit]

    return text


def _compact_history_item(item):
    if not isinstance(item, dict):
        return {}

    return {
        "topic": _clean_text(
            item.get("topic"),
            120,
        ),
        "angle": _clean_text(
            item.get("angle"),
            160,
        ),
        "format": _clean_text(
            item.get("format"),
            60,
        ),
        "hook": _clean_text(
            item.get("hook"),
            180,
        ),
        "cta": _clean_text(
            item.get("cta"),
            180,
        ),
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
    valid = [
        item
        for item in content
        if isinstance(item, dict)
    ]

    news = sorted(
        [
            item
            for item in valid
            if item.get("source_type") != "deal"
        ],
        key=_content_sort_key,
        reverse=True,
    )

    deals = sorted(
        [
            item
            for item in valid
            if item.get("source_type") == "deal"
        ],
        key=_content_sort_key,
        reverse=True,
    )

    selected = (
        news[:8]
        + deals[:2]
    )

    if len(selected) < MAX_CONTENT_ITEMS:
        chosen = {
            id(item)
            for item in selected
        }

        remaining = sorted(
            [
                item
                for item in valid
                if id(item) not in chosen
            ],
            key=_content_sort_key,
            reverse=True,
        )

        selected.extend(
            remaining[
                :MAX_CONTENT_ITEMS
                - len(selected)
            ]
        )

    output = []

    for item in selected[:MAX_CONTENT_ITEMS]:

        tags = (
            item.get("tags", [])
            if isinstance(
                item.get("tags", []),
                list,
            )
            else []
        )

        output.append(
            {
                "title": _clean_text(
                    item.get("title"),
                    220,
                ),
                "excerpt": _clean_text(
                    item.get("excerpt")
                    or item.get("description"),
                    MAX_EXCERPT_CHARS,
                ),
                "slug": _clean_text(
                    item.get("slug"),
                    180,
                ),
                "category": _clean_text(
                    item.get("category"),
                    80,
                ),
                "source_type": _clean_text(
                    item.get("source_type"),
                    40,
                ),
                "created_at": _clean_text(
                    item.get("created_at"),
                    80,
                ),
                "tags": [
                    _clean_text(
                        tag,
                        60,
                    )
                    for tag in tags[:5]
                ],
            }
        )

    return output


def _safe_prompt(prompt):
    prompt = prompt.strip()

    if len(prompt) > MAX_PROMPT_CHARS:
        raise RuntimeError(
            "Social AI prompt exceeds safe size: "
            f"{len(prompt)} characters."
        )

    return prompt


def parse_json_response(raw_response):
    text = raw_response.strip()

    if text.startswith("```"):
        text = (
            text
            .replace(
                "```json",
                "",
                1,
            )
            .replace(
                "```",
                "",
            )
            .strip()
        )

    try:
        return json.loads(text)

    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"AI returned invalid JSON: {error}"
        ) from error


# =========================================================
# STEP 1
# Generate 3 different concepts
# =========================================================

def build_prompt(content):
    history = [
        _compact_history_item(item)
        for item in get_recent_history(
            RECENT_HISTORY_ITEMS
        )
        if isinstance(item, dict)
    ]

    sample = prepare_content_for_ai(
        content
    )

    return _safe_prompt(
        f"""
Create exactly {CONCEPT_COUNT} DIFFERENT
compact GamerQuest.fr carousel CONCEPTS.

PRIMARY GOAL:
Drive qualified gaming traffic to GamerQuest.fr.

Use ONLY facts contained in the supplied content.
Never invent or infer facts.

Avoid repeating recent:
- topics
- hooks
- angles
- formats
- CTAs

The concepts should create genuine curiosity,
not misleading clickbait.

Prefer topics that:
1. have a strong visual gaming subject,
2. contain a useful or surprising piece of information,
3. can be understood quickly,
4. give the reader a reason to visit GamerQuest.fr.

Allowed formats:
{json.dumps(
    SOCIAL_FORMATS,
    ensure_ascii=False
)}

Recent history:
{json.dumps(
    history,
    ensure_ascii=False
)}

Available GamerQuest content:
{json.dumps(
    sample,
    ensure_ascii=False
)}

Do NOT write:
- slides
- captions
- hashtags
- visual prompts

Return ONLY a JSON array.

Each object must contain:

{{
    "topic": "...",
    "angle": "...",
    "format": "...",
    "hook": "...",
    "freshness": 0,
    "click_potential": 0,
    "curiosity": 0,
    "shareability": 0,
    "originality": 0,
    "gamerquest_relevance": 0
}}

All scores must be integers from 0 to 10.
"""
    )


# =========================================================
# STEP 2
# Expand winning concept into EXACTLY 3 slides
# =========================================================

def build_expansion_prompt(
    idea,
    content,
):
    sample = prepare_content_for_ai(
        content
    )

    base = {
        key: idea.get(key)
        for key in (
            "topic",
            "angle",
            "format",
            "hook",
        )
    }

    return _safe_prompt(
        f"""
Create the FINAL Instagram/Facebook carousel
for GamerQuest.fr.

CONCEPT:
{json.dumps(
    base,
    ensure_ascii=False
)}

SOURCE CONTENT:
{json.dumps(
    sample,
    ensure_ascii=False
)}

The carousel MUST contain EXACTLY
{CAROUSEL_SLIDES} slides.

========================================
SLIDE STRUCTURE
========================================

SLIDE 1 — HOOK

Purpose:
Stop the scroll.

Requirements:
- Strong concise headline.
- Immediately understandable.
- Create curiosity.
- Introduce the game/news/deal.
- Do NOT explain everything.
- Body must remain short.
- The title should work visually over a gaming image.

SLIDE 2 — VALUE

Purpose:
Give the most useful or interesting
piece of information.

Requirements:
- Explain the key fact.
- Give the reader real value.
- Use ONLY facts explicitly present
  in SOURCE CONTENT.
- Keep title and body concise.
- Do not repeat slide 1.

SLIDE 3 — CURIOSITY + TRAFFIC

Purpose:
Make the reader want to continue
on GamerQuest.fr.

Requirements:
- Give one final useful fact OR
  create a natural curiosity gap.
- Do NOT invent missing information.
- Do NOT use fake suspense.
- Encourage the reader to discover
  the complete information on GamerQuest.fr.
- Keep text concise.

========================================
FACTUAL RULES
========================================

Every factual statement MUST be explicitly
supported by SOURCE CONTENT.

NEVER infer:
- platforms
- release dates
- multiplayer
- compatibility
- prices
- future prices
- availability
- features
- editions
- developers
- publishers

If SOURCE CONTENT does not explicitly
contain a fact, DO NOT mention it.

========================================
TEXT RULES
========================================

Each slide must contain:

"title"
Maximum approximately 8 words.

"body"
Maximum approximately 25 words.

"visual_prompt"
A short description of the desired
visual composition.

The visual_prompt must NOT request:
- text inside the image
- logos
- fake screenshots
- invented game characters

The renderer adds all typography itself.

========================================
CAPTION
========================================

Write one natural social caption.

The caption should:
- introduce the story,
- create curiosity,
- encourage visiting GamerQuest.fr,
- avoid exaggerated clickbait.

========================================
CTA
========================================

Write one short CTA encouraging
the user to visit GamerQuest.fr.

========================================
HASHTAGS
========================================

Provide 3 to 6 relevant hashtags.

========================================
OUTPUT
========================================

Return ONLY valid JSON:

{{
    "slides": [
        {{
            "title": "...",
            "body": "...",
            "visual_prompt": "..."
        }},
        {{
            "title": "...",
            "body": "...",
            "visual_prompt": "..."
        }},
        {{
            "title": "...",
            "body": "...",
            "visual_prompt": "..."
        }}
    ],
    "caption": "...",
    "cta": "...",
    "hashtags": [
        "#GamerQuest"
    ]
}}
"""
    )


# =========================================================
# GENERATE CONCEPTS
# =========================================================

def generate_ideas(content):
    if not content:
        return []

    data = parse_json_response(
        call_grok(
            build_prompt(content)
        )
    )

    if not isinstance(data, list):
        raise RuntimeError(
            "AI response must be a JSON array."
        )

    return data[:CONCEPT_COUNT]


# =========================================================
# EXPAND CONCEPT
# =========================================================

def expand_idea(
    idea,
    content,
):
    if not isinstance(idea, dict):
        return None

    data = parse_json_response(
        call_grok(
            build_expansion_prompt(
                idea,
                content,
            )
        )
    )

    if not isinstance(data, dict):
        raise RuntimeError(
            "AI carousel response must be a JSON object."
        )

    slides = data.get(
        "slides",
        []
    )

    if (
        not isinstance(slides, list)
        or len(slides) != CAROUSEL_SLIDES
    ):
        raise RuntimeError(
            "AI carousel must contain exactly "
            f"{CAROUSEL_SLIDES} slides."
        )

    result = idea.copy()

    for key in (
        "slides",
        "caption",
        "cta",
        "hashtags",
    ):
        result[key] = data.get(
            key,
            (
                []
                if key in (
                    "slides",
                    "hashtags",
                )
                else ""
            ),
        )

    return result


# =========================================================
# FACT CHECK
# =========================================================

def verify_carousel(
    idea,
    content,
):
    sample = prepare_content_for_ai(
        content
    )

    package = {
        key: idea.get(key)
        for key in (
            "topic",
            "hook",
            "slides",
            "caption",
            "cta",
        )
    }

    prompt = _safe_prompt(
        f"""
Fact-check PACKAGE against ONLY SOURCE.

SOURCE:
{json.dumps(
    sample,
    ensure_ascii=False
)}

PACKAGE:
{json.dumps(
    package,
    ensure_ascii=False
)}

Check EVERY factual claim.

Pay particular attention to:
- dates
- platforms
- multiplayer
- prices
- future pricing
- availability
- compatibility
- features

Explicit support in SOURCE is required.

If any factual claim is unsupported,
valid MUST be false.

Marketing language or CTA wording
does not require factual verification
unless it contains a factual claim.

Return ONLY JSON:

{{
    "valid": true,
    "unsupported_claims": [],
    "reason": ""
}}
"""
    )

    data = parse_json_response(
        call_grok(prompt)
    )

    if (
        not isinstance(data, dict)
        or not isinstance(
            data.get("valid"),
            bool,
        )
    ):
        raise RuntimeError(
            "AI fact-check response is invalid."
        )

    claims = data.get(
        "unsupported_claims",
        []
    )

    if not isinstance(claims, list):
        claims = []

    return {
        "valid": data["valid"],
        "unsupported_claims": claims,
        "reason": _clean_text(
            data.get("reason"),
            500,
        ),
    }


# =========================================================
# REPAIR FAILED FACT CHECK
# =========================================================

def repair_carousel(
    idea,
    content,
    unsupported_claims,
):
    sample = prepare_content_for_ai(
        content
    )

    package = {
        key: idea.get(key)
        for key in (
            "slides",
            "caption",
            "cta",
            "hashtags",
        )
    }

    prompt = _safe_prompt(
        f"""
Repair this GamerQuest carousel
using ONLY SOURCE facts.

SOURCE:
{json.dumps(
    sample,
    ensure_ascii=False
)}

CURRENT PACKAGE:
{json.dumps(
    package,
    ensure_ascii=False
)}

UNSUPPORTED CLAIMS:
{json.dumps(
    unsupported_claims,
    ensure_ascii=False
)}

Requirements:

- Remove or rewrite ONLY what is needed.
- Do not add new facts.
- Preserve the original topic and angle.
- Preserve EXACTLY {CAROUSEL_SLIDES} slides.
- Keep the structure:

Slide 1 = Hook
Slide 2 = Value
Slide 3 = Curiosity + traffic

Every factual statement must be
explicitly supported by SOURCE.

Return ONLY JSON:

{{
    "slides": [
        {{
            "title": "...",
            "body": "...",
            "visual_prompt": "..."
        }},
        {{
            "title": "...",
            "body": "...",
            "visual_prompt": "..."
        }},
        {{
            "title": "...",
            "body": "...",
            "visual_prompt": "..."
        }}
    ],
    "caption": "...",
    "cta": "...",
    "hashtags": [
        "#GamerQuest"
    ]
}}
"""
    )

    data = parse_json_response(
        call_grok(prompt)
    )

    if not isinstance(data, dict):
        raise RuntimeError(
            "AI repair response must be a JSON object."
        )

    repaired_slides = data.get(
        "slides",
        package.get(
            "slides",
            [],
        ),
    )

    if (
        not isinstance(
            repaired_slides,
            list,
        )
        or len(repaired_slides)
        != CAROUSEL_SLIDES
    ):
        raise RuntimeError(
            "Repaired carousel must contain exactly "
            f"{CAROUSEL_SLIDES} slides."
        )

    result = idea.copy()

    for key in (
        "slides",
        "caption",
        "cta",
        "hashtags",
    ):
        result[key] = data.get(
            key,
            package.get(
                key,
                (
                    []
                    if key in (
                        "slides",
                        "hashtags",
                    )
                    else ""
                ),
            ),
        )

    return result
