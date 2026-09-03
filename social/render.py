import json
import re
from pathlib import Path

from social.sources import get_all_content
from social.renderer import render_carousel


OUTPUT_FILE = Path("social-output.json")
OUTPUT_DIR = Path("social-rendered")

MAX_IMAGES = 3


# =========================================================
# TEXT HELPERS
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
# CONTENT MATCHING
# =========================================================

def _carousel_search_text(carousel):
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
            score += 40

        if title in topic:
            score += 25

    hook = _clean_text(
        carousel.get("hook")
    ).lower()

    if hook and title:
        hook_tokens = _tokens(hook)

        score += (
            len(
                hook_tokens
                & item_tokens
            )
            * 5
        )

    return score


def find_best_content(
    carousel,
    content,
):
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


def _append_image(
    images,
    value,
):
    if not value:
        return

    # Direct string
    if isinstance(value, str):
        value = value.strip()

        if (
            _looks_like_image(value)
            and value not in images
        ):
            images.append(value)

        return

    # List of URLs or image dictionaries
    if isinstance(value, list):
        for item in value:
            _append_image(
                images,
                item,
            )

        return

    # Image dictionaries returned by APIs / feeds
    if isinstance(value, dict):
        possible_keys = (
            "url",
            "src",
            "source_url",
            "image_url",
            "featured_image_url",
            "original",
            "large",
            "medium",
        )

        for key in possible_keys:
            _append_image(
                images,
                value.get(key),
            )


def collect_item_images(item):
    """
    Collect every usable image attached to the matched GamerQuest item.

    The function supports several possible field names so it works
    even if the news/deals feeds do not use exactly the same schema.
    """

    if not isinstance(item, dict):
        return []

    images = []

    # Featured image first.
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

    # Then additional article images.
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
# FIND EXTRA IMAGES FROM SAME GAME / TOPIC
# =========================================================

def find_related_images(
    carousel,
    content,
    matched_item,
    limit=MAX_IMAGES,
):
    """
    Image strategy:

    Slide 1:
        featured image of the exact matched article

    Slides 2/3:
        another image from the article if available

        OR

        an image from another GamerQuest article about the
        same game/topic.

    If only one image exists, renderer.py will use different
    crops/zoom automatically.
    """

    images = []

    # -----------------------------------------------------
    # Exact article images first
    # -----------------------------------------------------

    for image in collect_item_images(
        matched_item
    ):
        if image not in images:
            images.append(image)

        if len(images) >= limit:
            return images[:limit]

    # -----------------------------------------------------
    # Then search other GamerQuest content about same topic
    # -----------------------------------------------------

    matched_tokens = _tokens(
        _content_search_text(
            matched_item
        )
    )

    carousel_tokens = _tokens(
        _carousel_search_text(
            carousel
        )
    )

    target_tokens = (
        matched_tokens
        | carousel_tokens
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

        overlap = len(
            target_tokens
            & item_tokens
        )

        if overlap <= 0:
            continue

        score = overlap * 10

        matched_title_tokens = _tokens(
            matched_item.get(
                "title"
            )
        )

        title_tokens = _tokens(
            item.get(
                "title"
            )
        )

        # Strong bonus when both articles clearly concern
        # the same named game/topic.
        score += (
            len(
                matched_title_tokens
                & title_tokens
            )
            * 20
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
# OUTPUT LOADING
# =========================================================

def load_social_output():
    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "social-output.json was not found."
        )

    with OUTPUT_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "social-output.json must contain a JSON object."
        )

    if data.get("status") != "ready":
        raise RuntimeError(
            "Social output is not ready for rendering."
        )

    carousel = data.get(
        "carousel"
    )

    if not isinstance(
        carousel,
        dict,
    ):
        raise RuntimeError(
            "Social output does not contain a valid carousel."
        )

    return carousel


# =========================================================
# MAIN RENDER
# =========================================================

def render_from_output(
    output_file=OUTPUT_FILE,
    output_dir=OUTPUT_DIR,
):
    global OUTPUT_FILE

    original_output = OUTPUT_FILE
    OUTPUT_FILE = Path(output_file)

    try:
        carousel = load_social_output()
    finally:
        OUTPUT_FILE = original_output

    content = get_all_content()

    matched_item = find_best_content(
        carousel,
        content,
    )

    featured_images = []

    if matched_item:
        featured_images = find_related_images(
            carousel,
            content,
            matched_item,
            limit=3,
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
        featured_images=featured_images,
    )

    print(
        f"Rendered slides: {len(paths)}"
    )

    if featured_images:
        print(
            "Featured images: "
            + " | ".join(
                featured_images
            )
        )
    else:
        print(
            "Featured images: none"
        )

    manifest = {
        "status": "rendered",
        "slides": [
            str(path)
            for path in paths
        ],
        "featured_images": featured_images,
    }

    manifest_path = (
        Path(output_dir)
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
