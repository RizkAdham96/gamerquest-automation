import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


# =========================================================
# GAMERQUEST OPENAI IMAGE GENERATOR
# =========================================================

OPENAI_IMAGE_ENDPOINT = (
    "https://api.openai.com/v1/images/generations"
)

OPENAI_IMAGE_MODEL = "gpt-image-1"

OPENAI_IMAGE_SIZE = "1024x1536"

OPENAI_IMAGE_QUALITY = "medium"

OPENAI_IMAGE_FORMAT = "png"

DEFAULT_TIMEOUT_SECONDS = 180


# =========================================================
# MONTHLY SAFETY LIMIT
# =========================================================
#
# We want to stay far below the user's €5/month budget.
#
# At current published GPT-Image-1 pricing:
# medium 1024x1536 ≈ $0.063 / image.
#
# 50 images would be roughly $3.15 in image-output cost.
#
# This is NOT a billing-system hard cap at OpenAI.
# It is an application-level safety limit for this
# automation.
#
# We intentionally keep it conservative.
# =========================================================

MAX_IMAGES_PER_MONTH = 50

USAGE_FILE = Path(
    "social/openai_image_usage.json"
)


# =========================================================
# API KEY
# =========================================================

def _get_api_key():
    api_key = os.environ.get(
        "OPENAI_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing."
        )

    return api_key


# =========================================================
# USAGE TRACKING
# =========================================================

def _current_month_key():
    from datetime import datetime, timezone

    now = datetime.now(
        timezone.utc
    )

    return now.strftime(
        "%Y-%m"
    )


def _load_usage():
    if not USAGE_FILE.exists():
        return {
            "month": _current_month_key(),
            "images_generated": 0,
        }

    try:
        data = json.loads(
            USAGE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            data,
            dict,
        ):
            raise ValueError(
                "Invalid usage file."
            )

    except Exception:
        return {
            "month": _current_month_key(),
            "images_generated": 0,
        }

    current_month = (
        _current_month_key()
    )

    if data.get(
        "month"
    ) != current_month:
        return {
            "month": current_month,
            "images_generated": 0,
        }

    try:
        generated = int(
            data.get(
                "images_generated",
                0,
            )
        )
    except Exception:
        generated = 0

    return {
        "month": current_month,
        "images_generated": generated,
    }


def _save_usage(data):
    USAGE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    USAGE_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _check_budget(
    requested_images,
):
    usage = _load_usage()

    generated = int(
        usage.get(
            "images_generated",
            0,
        )
    )

    remaining = (
        MAX_IMAGES_PER_MONTH
        - generated
    )

    if requested_images > remaining:
        raise RuntimeError(
            "OpenAI image monthly safety limit reached. "
            f"Generated this month: {generated}. "
            f"Limit: {MAX_IMAGES_PER_MONTH}."
        )

    return usage


def _record_image_generated(
    usage,
):
    usage["images_generated"] = (
        int(
            usage.get(
                "images_generated",
                0,
            )
        )
        + 1
    )

    _save_usage(
        usage
    )


# =========================================================
# TEXT HELPERS
# =========================================================

def _clean(value):
    return " ".join(
        str(
            value
            or ""
        ).split()
    )


def _truncate(
    text,
    limit=1800,
):
    text = _clean(
        text
    )

    if len(text) <= limit:
        return text

    return (
        text[:limit]
        .rsplit(
            " ",
            1,
        )[0]
        + "..."
    )


# =========================================================
# ARTICLE CONTEXT
# =========================================================

def _article_context(
    source_item,
):
    if not isinstance(
        source_item,
        dict,
    ):
        source_item = {}

    parts = []

    title = _clean(
        source_item.get(
            "title"
        )
    )

    excerpt = _clean(
        source_item.get(
            "excerpt"
        )
    )

    category = _clean(
        source_item.get(
            "category"
        )
    )

    tags = (
        source_item.get(
            "tags"
        )
        or []
    )

    if title:
        parts.append(
            f"Article title: {title}"
        )

    if excerpt:
        parts.append(
            f"Article summary: "
            f"{_truncate(excerpt, 1200)}"
        )

    if category:
        parts.append(
            f"Category: {category}"
        )

    if isinstance(
        tags,
        list,
    ):
        clean_tags = [
            _clean(tag)
            for tag in tags
            if _clean(tag)
        ]

        if clean_tags:
            parts.append(
                "Relevant tags: "
                + ", ".join(
                    clean_tags[:12]
                )
            )

    return "\n".join(
        parts
    )


# =========================================================
# CAROUSEL CONTEXT
# =========================================================

def _carousel_context(
    carousel,
):
    if not isinstance(
        carousel,
        dict,
    ):
        carousel = {}

    parts = []

    topic = _clean(
        carousel.get(
            "topic"
        )
    )

    if topic:
        parts.append(
            f"Topic: {topic}"
        )

    slides = (
        carousel.get(
            "slides"
        )
        or []
    )

    if isinstance(
        slides,
        list,
    ):
        for index, slide in enumerate(
            slides,
            start=1,
        ):
            if not isinstance(
                slide,
                dict,
            ):
                continue

            title = _clean(
                slide.get(
                    "title"
                )
            )

            body = _clean(
                slide.get(
                    "body"
                )
            )

            text = (
                f"Slide {index}"
            )

            if title:
                text += (
                    f" title: {title}."
                )

            if body:
                text += (
                    f" Meaning: "
                    f"{_truncate(body, 500)}"
                )

            parts.append(
                text
            )

    return "\n".join(
        parts
    )


# =========================================================
# SHARED VISUAL DIRECTION
# =========================================================

def _shared_style_prompt():
    return """
Create a premium vertical gaming-editorial visual for GamerQuest FR.

Visual direction:
- cinematic gaming magazine aesthetic
- premium, dramatic, modern and highly polished
- realistic lighting and believable materials
- strong depth between foreground, subject and background
- high visual contrast
- composition suitable for Instagram
- dark futuristic atmosphere where appropriate
- subtle blue and purple lighting accents
- visually rich but not cluttered
- professional gaming publication quality
- main subject clearly readable immediately
- leave useful darker/clean visual space in the lower half for a text card
- preserve strong visual interest in the upper half

Important restrictions:
- NO written words
- NO captions
- NO logos
- NO watermarks
- NO UI text
- NO fake magazine typography
- NO GamerQuest branding inside the generated image
- do not render any readable text
- do not invent factual visual details that contradict the supplied story
""".strip()


# =========================================================
# SLIDE-SPECIFIC PROMPTS
# =========================================================

def _slide_direction(
    index,
):
    if index == 1:
        return """
This is slide 1, the hero image.

Create the strongest possible opening visual.
Prioritize a dramatic recognizable subject or scene.
Use a cinematic hero composition.
The image should instantly communicate the gaming story.
Avoid generic gaming hardware unless the story is actually about hardware.
Keep the lower central area calmer because text will be overlaid later.
""".strip()

    if index == 2:
        return """
This is slide 2, the detail/value image.

Create a distinctly different composition from slide 1.
Show gameplay, environment, action, a location, a mechanic, or a meaningful story detail when supported by the supplied context.
Do not simply create another close-up hero portrait.
The visual must still clearly belong to the same gaming story.
Keep the lower central area usable for a text panel.
""".strip()

    return """
This is slide 3, the closing image.

Create a third distinct composition that still belongs to the same story.
Favor a memorable dramatic angle, atmospheric scene, action moment, or secondary visual idea.
It should feel like a satisfying final carousel image, not a repeat of slide 1.
Keep enough clean/darker space in the lower half for the closing text and CTA.
""".strip()


# =========================================================
# PROMPT BUILDER
# =========================================================

def build_image_prompt(
    carousel,
    source_item,
    slide_index,
):
    article = _article_context(
        source_item
    )

    carousel_text = (
        _carousel_context(
            carousel
        )
    )

    slide_direction = (
        _slide_direction(
            slide_index
        )
    )

    shared_style = (
        _shared_style_prompt()
    )

    prompt = f"""
You are creating one visual for a 3-slide Instagram carousel
for GamerQuest FR.

SOURCE STORY
------------
{article}

FACT-CHECKED CAROUSEL CONTEXT
-----------------------------
{carousel_text}

VISUAL ROLE
-----------
{slide_direction}

SHARED ART DIRECTION
--------------------
{shared_style}

CRITICAL SOURCE RULES
---------------------
Use only the supplied story context as the factual basis.

The image does not need to literally illustrate every sentence,
but it must clearly match the same game/topic/story.

Do not switch to another game.
Do not introduce unrelated gaming franchises.
Do not use generic controllers, consoles, keyboards or stock-gaming
imagery unless the actual story is specifically about that hardware.

If a specific game is named, make the composition visually centered
around the world, mood, characters, setting or gameplay concept of
that specific story.

Do not create text inside the image.

OUTPUT
------
One polished vertical background image only.
""".strip()

    return prompt


# =========================================================
# OPENAI REQUEST
# =========================================================

def _request_image(
    prompt,
):
    api_key = _get_api_key()

    payload = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "size": OPENAI_IMAGE_SIZE,
        "quality": OPENAI_IMAGE_QUALITY,
        "output_format": OPENAI_IMAGE_FORMAT,
        "n": 1,
    }

    body = json.dumps(
        payload
    ).encode(
        "utf-8"
    )

    request = urllib.request.Request(
        OPENAI_IMAGE_ENDPOINT,
        data=body,
        headers={
            "Authorization":
                f"Bearer {api_key}",
            "Content-Type":
                "application/json",
            "User-Agent":
                "GamerQuest-Social/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as response:
            raw = response.read()

    except urllib.error.HTTPError as error:
        try:
            details = (
                error.read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )
        except Exception:
            details = ""

        raise RuntimeError(
            "OpenAI image generation failed "
            f"with HTTP {error.code}: "
            f"{details[:1000]}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            "OpenAI image request failed: "
            f"{error}"
        ) from error

    except Exception as error:
        raise RuntimeError(
            "OpenAI image request failed: "
            f"{error}"
        ) from error

    try:
        data = json.loads(
            raw.decode(
                "utf-8"
            )
        )
    except Exception as error:
        raise RuntimeError(
            "OpenAI returned invalid JSON."
        ) from error

    images = data.get(
        "data"
    )

    if (
        not isinstance(
            images,
            list,
        )
        or not images
    ):
        raise RuntimeError(
            "OpenAI response contained no image."
        )

    first = images[0]

    if not isinstance(
        first,
        dict,
    ):
        raise RuntimeError(
            "OpenAI returned an invalid image object."
        )

    encoded = first.get(
        "b64_json"
    )

    if not encoded:
        raise RuntimeError(
            "OpenAI response did not contain b64_json."
        )

    try:
        return base64.b64decode(
            encoded
        )
    except Exception as error:
        raise RuntimeError(
            "Could not decode OpenAI image."
        ) from error


# =========================================================
# GENERATE ONE IMAGE
# =========================================================

def generate_slide_image(
    carousel,
    source_item,
    slide_index,
    output_path,
    usage=None,
):
    if slide_index not in (
        1,
        2,
        3,
    ):
        raise ValueError(
            "slide_index must be 1, 2 or 3."
        )

    if usage is None:
        usage = _check_budget(
            1
        )

    prompt = build_image_prompt(
        carousel=carousel,
        source_item=source_item,
        slide_index=slide_index,
    )

    print(
        "Generating OpenAI visual "
        f"{slide_index}/3..."
    )

    image_bytes = _request_image(
        prompt
    )

    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_bytes(
        image_bytes
    )

    _record_image_generated(
        usage
    )

    print(
        "OpenAI visual saved: "
        f"{output_path}"
    )

    return output_path


# =========================================================
# GENERATE 3-SLIDE VISUAL SET
# =========================================================

def generate_carousel_images(
    carousel,
    source_item,
    output_dir="social-generated",
):
    """
    Generate exactly three images.

    Returns:
        [
            Path("...slide-01-source.png"),
            Path("...slide-02-source.png"),
            Path("...slide-03-source.png"),
        ]

    If generation fails on any slide, the exception is raised.
    The caller will later handle fallback to the existing
    exact-source image system.
    """

    if not isinstance(
        carousel,
        dict,
    ):
        raise ValueError(
            "Carousel must be a dictionary."
        )

    slides = carousel.get(
        "slides"
    )

    if (
        not isinstance(
            slides,
            list,
        )
        or len(slides) != 3
    ):
        raise ValueError(
            "OpenAI image generator requires exactly 3 slides."
        )

    if not isinstance(
        source_item,
        dict,
    ):
        raise ValueError(
            "source_item must be a dictionary."
        )

    usage = _check_budget(
        3
    )

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    generated_paths = []

    for slide_index in (
        1,
        2,
        3,
    ):
        output_path = (
            output_dir
            / (
                f"slide-{slide_index:02d}"
                "-source.png"
            )
        )

        path = generate_slide_image(
            carousel=carousel,
            source_item=source_item,
            slide_index=slide_index,
            output_path=output_path,
            usage=usage,
        )

        generated_paths.append(
            path
        )

    print(
        "OpenAI visual set complete: "
        f"{len(generated_paths)} images."
    )

    return generated_paths


# =========================================================
# SAFE WRAPPER FOR AUTOMATION
# =========================================================

def try_generate_carousel_images(
    carousel,
    source_item,
    output_dir="social-generated",
):
    """
    Safe automation wrapper.

    Returns an empty list if OpenAI generation fails,
    allowing social/render.py to fall back to the
    existing exact-source image pipeline.
    """

    try:
        return generate_carousel_images(
            carousel=carousel,
            source_item=source_item,
            output_dir=output_dir,
        )

    except Exception as error:
        print(
            "OpenAI image generation unavailable. "
            "Existing image fallback will be used."
        )

        print(
            f"Reason: {error}"
        )

        return []
