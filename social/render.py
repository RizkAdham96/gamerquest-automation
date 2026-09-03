import json
import re
from pathlib import Path

from social.sources import get_all_content
from social.renderer import render_carousel


OUTPUT_FILE = Path("social-output.json")
OUTPUT_DIR = Path("social-rendered")

MAX_IMAGES = 3


# =========================================================
# HELPERS
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


def _looks_like_image(value):
    if not isinstance(value, str):
        return False

    value = value.strip().lower()

    if not value:
        return False

    if value.startswith(
        ("http://", "https://")
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
# MATCH CONTENT
# =========================================================

def _match_score(carousel, item):
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
# IMAGE EXTRACTION
# =========================================================

def collect_item_images(item):
    if not isinstance(item, dict):
        return []

    images = []

    # Main/featured images first.
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

    # Additional images.
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
# BACKWARD-COMPATIBLE FUNCTION
#
# Existing tests call this function directly.
# DO NOT REMOVE.
# =========================================================

def find_featured_image_url(
    carousel,
    content=None,
):
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
# RELATED IMAGE SEARCH
# =========================================================

def find_related_images(
    carousel,
    content,
    matched_item=None,
    limit=MAX_IMAGES,
):
    """
    Return up to 3 unique images.

    Priority:
    1. Images belonging to the exact matched article.
    2. Images from other GamerQuest content strongly related
       to the same game/topic.
    3. If fewer than 3 are found, renderer.py reuses the
       available image with different crops.
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

    images = []

    # -----------------------------------------------------
    # 1. Exact article
    # -----------------------------------------------------

    for image in collect_item_images(
        matched_item
    ):
        if image not in images:
            images.append(image)

        if len(images) >= limit:
            return images[:limit]

    # -----------------------------------------------------
    # 2. Related GamerQuest articles
    # -----------------------------------------------------

    matched_title_tokens = _tokens(
        matched_item.get("title")
    )

    topic_tokens = _tokens(
        carousel.get("topic")
    )

    carousel_tokens = _tokens(
        _carousel_search_text(
            carousel
        )
    )

    related = []

    for item in content:
        if not isinstance(item, dict):
            continue

        if item is matched_item:
            continue

        item_tokens = _tokens(
            _content_search_text(
                item
            )
        )

        item_title_tokens = _tokens(
            item.get("title")
        )

        # General topical overlap.
        general_overlap = len(
            carousel_tokens
            & item_tokens
        )

        # Stronger signal: same game/name appears in titles.
        title_overlap = len(
            matched_title_tokens
            & item_title_tokens
        )

        # Topic explicitly overlaps this article.
        topic_overlap = len(
            topic_tokens
            & item_tokens
        )

        if (
            general_overlap <= 0
            and title_overlap <= 0
            and topic_overlap <= 0
        ):
            continue

        score = (
            general_overlap * 3
            + topic_overlap * 10
            + title_overlap * 30
        )

        related.append(
            (
                score,
                item,
            )
        )

    related.sort(
        key=lambda pair: pair[0],
        reverse=True,
    )

    for _, item in related:
        for image in collect_item_images(
            item
        ):
            if image in images:
                continue

            images.append(image)

            if len(images) >= limit:
                return images[:limit]

    return images[:limit]


# =========================================================
# VALIDATION
# =========================================================

def _extract_carousel(payload):
    """
    Supports the current ready payload as well as the
    fact-check structure used by the existing tests.
    """

    if not isinstance(payload, dict):
        raise RuntimeError(
            "social-output.json must contain a JSON object."
        )

    status = payload.get(
        "status"
    )

    if status != "ready":
        raise RuntimeError(
            "Social output is not ready for rendering."
        )

    # If fact_checked exists explicitly, it must be true.
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
# LOAD OUTPUT
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
# RENDER FROM OUTPUT
# =========================================================

def render_from_output(
    output_file=OUTPUT_FILE,
    output_dir=OUTPUT_DIR,
):
    payload = load_social_output(
        output_file
    )

    carousel = _extract_carousel(
        payload
    )

    content = get_all_content()

    matched_item = find_best_content(
        carousel,
        content,
    )

    featured_images = find_related_images(
        carousel,
        content,
        matched_item=matched_item,
        limit=3,
    )

    # -----------------------------------------------------
    # BACKWARD COMPATIBILITY
    #
    # The old renderer/tests expect a single featured image.
    # The new renderer can additionally receive multiple.
    # -----------------------------------------------------

    featured_image = (
        featured_images[0]
        if featured_images
        else None
    )

    print(
        "Social renderer status: rendered"
    )

    print(
        f"Images found for carousel: "
        f"{len(featured_images)}"
    )

    for index, image in enumerate(
        featured_images,
        start=1,
    ):
        print(
            f"Carousel image {index}: "
            f"{image}"
        )

    paths = render_carousel(
        carousel,
        output_dir,
        featured_image=featured_image,
        featured_images=featured_images,
    )

    print(
        f"Rendered slides: {len(paths)}"
    )

    if featured_image:
        print(
            f"Featured image: "
            f"{featured_image}"
        )
    else:
        print(
            "Featured image: none"
        )

    # -----------------------------------------------------
    # MANIFEST
    #
    # Keep old fields so tests/workflows don't break.
    # Add featured_images for new functionality.
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

        # Old compatibility field
        "featured_image": (
            featured_image
        ),

        # New multi-image field
        "featured_images": (
            featured_images
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
