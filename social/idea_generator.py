import json

from social.ai_client import call_grok
from social.config import SOCIAL_FORMATS
from social.history import get_recent_history


MAX_CONTENT_ITEMS = 10
MAX_EXCERPT_CHARS = 700
MAX_PROMPT_CHARS = 18000
RECENT_HISTORY_ITEMS = 8
CONCEPT_COUNT = 3
CAROUSEL_SLIDES = 3


# =========================================================
# HELPERS
# =========================================================

def _clean_text(value, limit=None):
    text = "" if value is None else str(value).strip()

    if limit is not None:
        return text[:limit]

    return text


def _source_id(item):
    if not isinstance(item, dict):
        return ""

    value = _clean_text(
        item.get("source_id")
    )

    if value:
        return value

    slug = _clean_text(
        item.get("slug")
    )

    if slug:
        return f"slug:{slug}"

    title = _clean_text(
        item.get("title")
    )

    if title:
        return f"title:{title}"

    return ""


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


def _source_metadata(item):
    source = item.get("source")

    if not isinstance(source, dict):
        source = {}

    return {
        "source_url": _clean_text(
            item.get("source_url")
            or source.get("url"),
            500,
        ),
        "source_title": _clean_text(
            source.get("title"),
            250,
        ),
        "source_domain": _clean_text(
            source.get("domain"),
            120,
        ),
    }


# =========================================================
# PREPARE CONTENT
# =========================================================

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

        source_metadata = (
            _source_metadata(item)
        )

        output.append(
            {
                "source_id":
                    _source_id(item),

                "title":
                    _clean_text(
                        item.get("title"),
                        220,
                    ),

                "excerpt":
                    _clean_text(
                        item.get("excerpt")
                        or item.get("description"),
                        MAX_EXCERPT_CHARS,
                    ),

                "slug":
                    _clean_text(
                        item.get("slug"),
                        180,
                    ),

                "category":
                    _clean_text(
                        item.get("category"),
                        80,
                    ),

                "source_type":
                    _clean_text(
                        item.get("source_type"),
                        40,
                    ),

                "created_at":
                    _clean_text(
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

                **source_metadata,
            }
        )

    return output


# =========================================================
# EXACT SOURCE LOOKUP
# =========================================================

def find_source_item(content, source_id):
    source_id = _clean_text(
        source_id
    )

    if not source_id:
        return None

    for item in content:
        if not isinstance(item, dict):
            continue

        if _source_id(item) == source_id:
            return item

    return None


def _exact_source_content(
    idea,
    content,
):
    if not isinstance(content, list):
        return []

    source_id = ""

    if isinstance(idea, dict):
        source_id = _clean_text(
            idea.get("source_id")
        )

    if source_id:
        item = find_source_item(
            content,
            source_id,
        )

        if item:
            return [item]

    # Compatibility for tests / explicit single-item calls.
    valid = [
        item
        for item in content
        if isinstance(item, dict)
    ]

    if len(valid) == 1:
        return valid

    return []


# =========================================================
# PROMPT SAFETY
# =========================================================

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
# CONCEPT PROMPT
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
GamerQuest.fr social carousel concepts.

IMPORTANT ARCHITECTURE RULE:

Each concept MUST come from ONE AND ONLY ONE
GamerQuest content item.

You MUST copy the exact "source_id" of the
chosen content item into the concept.

NEVER combine facts from two articles.
NEVER combine two similar stories.
NEVER use information from another source_id.

PRIMARY GOAL:
Drive qualified gaming traffic to GamerQuest.fr.

Use ONLY explicit facts contained in the
ONE selected content item.

Never invent.
Never infer.
Never merge separate facts into a new claim.

Example:
"construction de villes"
+
"exploration sous-marine"

DOES NOT mean:
"villes sous-marines"

Prefer content with:
1. strong gaming visual potential,
2. useful or surprising information,
3. a dedicated original source page,
4. clear factual information,
5. good traffic potential.

When two GamerQuest articles cover a similar topic,
prefer the article whose original source_title is
specifically about that same game/story rather than
a generic roundup page.

Allowed formats:
{json.dumps(
    SOCIAL_FORMATS,
    ensure_ascii=False
)}

Recent social history:
{json.dumps(
    history,
    ensure_ascii=False
)}

Available GamerQuest content:
{json.dumps(
    sample,
    ensure_ascii=False
)}

Return ONLY a JSON array.

Each object MUST contain:

{{
    "source_id": "COPY EXACT SOURCE ID",
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

Write all public-facing concepts in French.
"""
    )


# =========================================================
# EXPANSION PROMPT
# =========================================================

def build_expansion_prompt(
    idea,
    content,
):
    exact_content = (
        _exact_source_content(
            idea,
            content,
        )
    )

    if not exact_content:
        raise RuntimeError(
            "Could not resolve exact source for carousel."
        )

    sample = prepare_content_for_ai(
        exact_content
    )

    base = {
        key: idea.get(key)
        for key in (
            "source_id",
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

LANGUAGE:
French only.

CONCEPT:
{json.dumps(
    base,
    ensure_ascii=False
)}

ONE AND ONLY SOURCE:
{json.dumps(
    sample,
    ensure_ascii=False
)}

CRITICAL:
The source above is the ONLY article you may use.

Do not use general knowledge.
Do not use information from another article.
Do not infer information that is not written there.

Do not combine two separate facts into a stronger
relationship.

Example:

SUPPORTED:
- construction de villes
- exploration sous-marine

UNSUPPORTED:
- construction de villes sous-marines
- villes submergées
- cités sous-marines

unless the source explicitly says the cities
themselves are underwater.

The carousel MUST contain EXACTLY
{CAROUSEL_SLIDES} slides.

SLIDE 1 — HOOK

- Strong headline.
- Maximum approximately 8 words.
- Short body.
- Create curiosity.
- Do not reveal everything.

SLIDE 2 — VALUE

- Most useful supported fact.
- Maximum approximately 8-word title.
- Maximum approximately 25-word body.
- No unsupported interpretation.

SLIDE 3 — CURIOSITY + TRAFFIC

- Give another supported fact OR a natural
  curiosity gap.
- Do not invent future information.
- Encourage visiting GamerQuest.fr.
- Avoid generic filler when a concrete supported
  fact is available.

Each slide must contain:

"title"
"body"
"visual_prompt"

visual_prompt must NOT request:
- text inside images
- logos
- fake screenshots
- invented characters

Write a French caption.

Write a short French CTA.

Provide 3 to 6 hashtags.

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
# GENERATE IDEAS
# =========================================================

def generate_ideas(content):
    if not content:
        return []

    sample = prepare_content_for_ai(
        content
    )

    valid_source_ids = {
        item.get("source_id")
        for item in sample
        if item.get("source_id")
    }

    data = parse_json_response(
        call_grok(
            build_prompt(content)
        )
    )

    if not isinstance(data, list):
        raise RuntimeError(
            "AI response must be a JSON array."
        )

    output = []

    for idea in data:
        if not isinstance(idea, dict):
            continue

        source_id = _clean_text(
            idea.get("source_id")
        )

        # Compatibility with tests where only one source exists.
        if (
            not source_id
            and len(valid_source_ids) == 1
        ):
            source_id = next(
                iter(valid_source_ids)
            )

        if source_id not in valid_source_ids:
            continue

        clean_idea = idea.copy()
        clean_idea[
            "source_id"
        ] = source_id

        output.append(
            clean_idea
        )

    return output[:CONCEPT_COUNT]


# =========================================================
# EXPAND IDEA
# =========================================================

def expand_idea(
    idea,
    content,
):
    if not isinstance(idea, dict):
        return None

    exact_content = (
        _exact_source_content(
            idea,
            content,
        )
    )

    if not exact_content:
        raise RuntimeError(
            "Exact source article was not found."
        )

    data = parse_json_response(
        call_grok(
            build_expansion_prompt(
                idea,
                exact_content,
            )
        )
    )

    if not isinstance(data, dict):
        raise RuntimeError(
            "AI carousel response must be a JSON object."
        )

    slides = data.get(
        "slides",
        [],
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
    exact_content = (
        _exact_source_content(
            idea,
            content,
        )
    )

    if not exact_content:
        return {
            "valid": False,
            "unsupported_claims": [
                "Exact source article missing"
            ],
            "reason":
                "The carousel cannot be fact-checked "
                "without its exact source article.",
        }

    sample = prepare_content_for_ai(
        exact_content
    )

    package = {
        key: idea.get(key)
        for key in (
            "source_id",
            "topic",
            "hook",
            "slides",
            "caption",
            "cta",
        )
    }

    prompt = _safe_prompt(
        f"""
Fact-check PACKAGE using ONLY the ONE SOURCE.

ONE SOURCE:
{json.dumps(
    sample,
    ensure_ascii=False
)}

PACKAGE:
{json.dumps(
    package,
    ensure_ascii=False
)}

Check EVERY factual claim in:
- every slide title
- every slide body
- caption
- CTA if factual

A claim is valid ONLY if explicitly supported
by the source.

VERY IMPORTANT:
Check relationships between facts.

If the source separately says:
- construction de villes
- exploration sous-marine

then these claims are NOT supported:
- villes sous-marines
- villes submergées
- cités sous-marines

unless the source explicitly states that the
cities themselves are underwater.

Also carefully check:
- dates
- platforms
- price
- availability
- multiplayer
- features
- developers
- publishers
- editions
- locations
- future announcements

Do not use outside knowledge.

If ONE claim is unsupported:
"valid" MUST be false.

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
        [],
    )

    if not isinstance(claims, list):
        claims = []

    return {
        "valid":
            data["valid"],

        "unsupported_claims":
            claims,

        "reason":
            _clean_text(
                data.get("reason"),
                700,
            ),
    }


# =========================================================
# REPAIR
# =========================================================

def repair_carousel(
    idea,
    content,
    unsupported_claims,
):
    exact_content = (
        _exact_source_content(
            idea,
            content,
        )
    )

    if not exact_content:
        raise RuntimeError(
            "Exact source article missing during repair."
        )

    sample = prepare_content_for_ai(
        exact_content
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
Repair this GamerQuest carousel.

Use ONLY this ONE SOURCE:

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

RULES:

- Rewrite or remove every unsupported claim.
- Never add a new fact.
- Do not use outside knowledge.
- Preserve the topic.
- Preserve EXACTLY 3 slides.
- French only.

IMPORTANT semantic rule:

"construction de villes"
+
"exploration sous-marine"

must remain two separate facts.

Never transform them into:
- villes sous-marines
- cités sous-marines
- villes submergées

unless SOURCE explicitly states this.

Slide 1 = Hook
Slide 2 = Value
Slide 3 = Curiosity + traffic

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
