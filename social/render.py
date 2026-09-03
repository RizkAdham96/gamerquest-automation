import json
import re
from pathlib import Path

from social.sources import get_all_content
from social.renderer import render_carousel


OUTPUT_FILE = Path("social-output.json")
OUTPUT_DIR = Path("social-rendered")

MAX_IMAGES = 3


# =========================================================
# BASIC HELPERS
# =========================================================

def _clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def _tokens(value):
    text = _clean_text(value).lower()

    return {
        token
        for token in re.findall(
            r"[a-zA-ZÀ-ÿ0-9]+",
            text,
        )
        if len(token) >= 3
    }


# =========================================================
# IMAGE HELPERS
# =========================================================

def _looks_like_image(value):
    if not isinstance(value, str):
        return False

    value = value.strip().lower()

    if not value:
        return False

    if value.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return True

    return value.endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        )
    )


def _append_image(images, value):
    """
    Adds image URLs/paths without duplicates.

    Supports:
    - string
    - list
    - dictionary
    """

    if not value:
        return

    if isinstance(value, str):
        value = value.strip()

        if (
            _looks_like_image(value)
            and value not in images
        ):
            images.append(value)

        return

    if isinstance(value, list):
        for item in value:
            _append_image(
                images,
                item,
            )

        return

    if isinstance(value, dict):
        possible_keys = (
            "url",
            "src",
            "source_url",
            "image_url",
            "featured_image_url",
            "featured_image",
            "original",
            "large",
            "medium",
        )

        for key in possible_keys:
            _append_image(
                images,
                value.get(key),
            )


# =========================================================
# CAROUSEL SEARCH TEXT
# =========================================================

def _carousel_search_text(carousel):
    if not isinstance(carousel, dict):
        return ""

    parts = [
        carousel.get("topic"),
        carousel.get("hook"),
        carousel.get("angle"),
    ]

    slides = carousel.get(
        "slides",
        [],
    )

    if isinstance(slides, list):
        for slide in slides:
            if not isinstance(slide, dict):
                continue

            parts.append(
                slide.get("title")
            )

            parts.append(
                slide.get("body")
            )

    return " ".join(
        _clean_text(part)
        for part in parts
        if part
    )


# =========================================================
# CONTENT SEARCH TEXT
# =========================================================

def _content_search_text(item):
    if not isinstance(item, dict):
        return ""

    parts = [
        item.get("title"),
        item.get("slug"),
        item.get("category"),
        item.get("excerpt"),
        item.get("description"),
        item.get("content"),
    ]

    tags = item.get(
        "tags",
        [],
    )

    if isinstance(tags, list):
        parts.extend(tags)

    return " ".join(
        _clean_text(part)
        for part in parts
        if part
    )


# =========================================================
# CONTENT MATCHING
# =========================================================

def _match_score(
    carousel,
    item,
):
    carousel_tokens = _tokens(
        _carousel_search_text(
            carousel
        )
    )

    item_tokens = _tokens(
        _content_search_text(
            item
        )
    )

    if (
        not carousel_tokens
        or not item_tokens
    ):
        return 0

    overlap = (
        carousel_tokens
        & item_tokens
    )

    score = len(overlap) * 10

    topic = _clean_text(
        carousel.get("topic")
    ).lower()

    title = _clean_text(
        item.get("title")
    ).lower()

    if topic and title:
        if topic in title:
            score += 50

        if title in topic:
            score += 30

    hook = _clean_text(
        carousel.get("hook")
    ).lower()

    if hook:
        score += (
            len(
                _tokens(hook)
                & item_tokens
            )
            * 5
        )

    return score


def find_best_content(
    carousel,
    content,
):
    """
    Find the GamerQuest content item that best matches
    the generated carousel.
    """

    if not isinstance(content, list):
        return None

    candidates = [
        item
        for item in content
        if isinstance(item, dict)
    ]

    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda item: _match_score(
            carousel,
            item,
        ),
        reverse=True,
    )

    best = ranked[0]

    if _match_score(
        carousel,
        best,
    ) <= 0:
        return None

    return best


# =========================================================
# COLLECT IMAGES FROM EXACT ARTICLE
# =========================================================

def collect_item_images(item):
    """
    Collect images belonging ONLY to the matched article.

    We do not search other GamerQuest articles.
    """

    if not isinstance(item, dict):
        return []

    images = []

    # Main article image first.
    preferred_fields = (
        "featured_image_url",
        "featured_image",
        "image_url",
        "image",
        "thumbnail_url",
        "thumbnail",
        "cover_image",
        "cover",
    )

    for field in preferred_fields:
        _append_image(
            images,
            item.get(field),
        )

    # Extra images are allowed ONLY if they belong to the
    # same exact article.
    gallery_fields = (
        "images",
        "gallery",
        "media",
        "screenshots",
        "article_images",
        "content_images",
        "image_urls",
    )

    for field in gallery_fields:
        _append_image(
            images,
            item.get(field),
        )

    return images


# =========================================================
# BACKWARD-COMPATIBLE FEATURED IMAGE
# =========================================================

def find_featured_image_url(
    carousel,
    content=None,
):
    """
    Existing tests use this function, so keep it.
    """

    if content is None:
        content = get_all_content()

    matched_item = find_best_content(
        carousel,
        content,
    )

    if not matched_item:
        return None

    images = collect_item_images(
        matched_item
    )

    if not images:
        return None

    return images[0]


# =========================================================
# STRICT IMAGE SELECTION
# =========================================================

def find_related_images(
    carousel,
    content,
    matched_item=None,
    limit=MAX_IMAGES,
):
    """
    STRICT MODE.

    Only return images belonging to the exact matched article.

    We deliberately DO NOT use images from related articles.

    This prevents:
    - another game's artwork appearing in slide 2 or 3
    - old GamerQuest thumbnails with baked-in text
    - visually unrelated carousel slides

    If only one article image exists:
    renderer.py will reuse that one image with a different
    crop/zoom for each slide.
    """

    if not isinstance(content, list):
        return []

    if matched_item is None:
        matched_item = find_best_content(
            carousel,
            content,
        )

    if not matched_item:
        return []

    images = collect_item_images(
        matched_item
    )

    unique_images = []

    for image in images:
        if image not in unique_images:
            unique_images.append(image)

        if len(unique_images) >= limit:
            break

    return unique_images[:limit]


# =========================================================
# LOAD SOCIAL OUTPUT
# =========================================================

def load_social_output(
    output_file=OUTPUT_FILE,
):
    output_file = Path(
        output_file
    )

    if not output_file.exists():
        raise RuntimeError(
            "social-output.json was not found."
        )

    with output_file.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    return payload


# =========================================================
# COMPATIBILITY VALIDATION
# =========================================================

def _extract_carousel(payload):
    if not isinstance(payload, dict):
        raise RuntimeError(
            "social-output.json must contain a JSON object."
        )

    if payload.get("status") != "ready":
        raise RuntimeError(
            "Social output is not ready for rendering."
        )

    if (
        "fact_checked" in payload
        and payload.get("fact_checked") is not True
    ):
        raise RuntimeError(
            "Social output has not passed fact-checking."
        )

    carousel = payload.get(
        "carousel"
    )

    if not isinstance(
        carousel,
        dict,
    ):
        raise RuntimeError(
            "Social output does not contain a valid carousel."
        )

    slides = carousel.get(
        "slides"
    )

    if (
        not isinstance(slides, list)
        or len(slides) != 3
    ):
        raise RuntimeError(
            "Carousel must contain exactly three slides."
        )

    return carousel


# =========================================================
# RENDER FROM OUTPUT
# =========================================================

def render_from_output(
    output_file=OUTPUT_FILE,
    output_dir=OUTPUT_DIR,
):
    payload = load_social_output(
        output_file
    )

    # -----------------------------------------------------
    # INVALID PAYLOAD
    # -----------------------------------------------------

    if not isinstance(payload, dict):
        return {
            "status": "skipped",
            "reason": "invalid_payload",
        }

    # -----------------------------------------------------
    # NOT READY
    # -----------------------------------------------------

    if payload.get("status") != "ready":
        return {
            "status": "skipped",
            "reason": "not_ready",
        }

    # -----------------------------------------------------
    # NOT FACT-CHECKED
    # -----------------------------------------------------

    if (
        "fact_checked" in payload
        and payload.get("fact_checked") is not True
    ):
        return {
            "status": "skipped",
            "reason": "not_fact_checked",
        }

    # -----------------------------------------------------
    # CAROUSEL
    # -----------------------------------------------------

    carousel = payload.get(
        "carousel"
    )

    if not isinstance(
        carousel,
        dict,
    ):
        return {
            "status": "skipped",
            "reason": "missing_carousel",
        }

    slides = carousel.get(
        "slides"
    )

    if (
        not isinstance(slides, list)
        or len(slides) != 3
    ):
        return {
            "status": "skipped",
            "reason": "invalid_slide_count",
        }

    # -----------------------------------------------------
    # LOAD GAMERQUEST CONTENT
    # -----------------------------------------------------

    content = get_all_content()

    matched_item = find_best_content(
        carousel,
        content,
    )

    # -----------------------------------------------------
    # EXACT ARTICLE IMAGES ONLY
    # -----------------------------------------------------

    featured_images = find_related_images(
        carousel,
        content,
        matched_item=matched_item,
        limit=3,
    )

    featured_image = (
        featured_images[0]
        if featured_images
        else None
    )

    print(
        "Social renderer status: rendered"
    )

    if matched_item:
        print(
            "Matched article: "
            + _clean_text(
                matched_item.get("title")
            )
        )
    else:
        print(
            "Matched article: none"
        )

    print(
        f"Images found in exact article: "
        f"{len(featured_images)}"
    )

    for index, image in enumerate(
        featured_images,
        start=1,
    ):
        print(
            f"Article image {index}: "
            f"{image}"
        )

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    paths = render_carousel(
        carousel,
        output_dir,
        featured_image=featured_image,
        featured_images=featured_images,
    )

    print(
        f"Rendered slides: "
        f"{len(paths)}"
    )

    if len(featured_images) == 1:
        print(
            "Image mode: one article image + "
            "three different crops"
        )

    elif len(featured_images) > 1:
        print(
            "Image mode: multiple images from "
            "the exact article"
        )

    else:
        print(
            "Image mode: fallback background"
        )

    # -----------------------------------------------------
    # MANIFEST
    # -----------------------------------------------------

    manifest = {
        "status": "rendered",

        "slides": [
            str(path)
            for path in paths
        ],

        "caption": payload.get(
            "caption",
            carousel.get(
                "caption",
                "",
            ),
        ),

        "hashtags": payload.get(
            "hashtags",
            carousel.get(
                "hashtags",
                [],
            ),
        ),

        "cta": payload.get(
            "cta",
            carousel.get(
                "cta",
                "",
            ),
        ),

        "topic": carousel.get(
            "topic",
            payload.get(
                "topic",
                "",
            ),
        ),

        "featured_image": (
            featured_image
        ),

        "featured_images": (
            featured_images
        ),

        "image_mode": (
            "single_image_crops"
            if len(featured_images) == 1
            else "article_images"
            if len(featured_images) > 1
            else "fallback"
        ),
    }

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path = (
        output_dir
        / "manifest.json"
    )

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            manifest,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return manifest


# =========================================================
# CLI
# =========================================================

if __name__ == "__main__":
    render_from_output()
