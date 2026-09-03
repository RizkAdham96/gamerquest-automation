import json
import re
from pathlib import Path

from social.sources import get_all_content
from social.renderer import render_carousel
from social.image_finder import (
    find_images_for_article,
)


OUTPUT_FILE = Path(
    "social-output.json"
)

OUTPUT_DIR = Path(
    "social-rendered"
)


# =========================================================
# HELPERS
# =========================================================

def _clean_text(value):
    if value is None:
        return ""

    return str(
        value
    ).strip()


def _tokens(value):
    text = (
        _clean_text(value)
        .lower()
    )

    return {
        token
        for token in re.findall(
            r"[a-zA-ZÀ-ÿ0-9]+",
            text,
        )
        if len(token) >= 3
    }


def _item_source_id(item):
    if not isinstance(
        item,
        dict,
    ):
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


# =========================================================
# EXACT SOURCE LOOKUP
# =========================================================

def find_content_by_source_id(
    source_id,
    content,
):
    source_id = _clean_text(
        source_id
    )

    if not source_id:
        return None

    for item in content:
        if not isinstance(
            item,
            dict,
        ):
            continue

        if (
            _item_source_id(item)
            == source_id
        ):
            return item

    return None


# =========================================================
# LEGACY MATCHING
# Used only for backwards compatibility/tests.
# Production rendering DOES NOT use this when source_id exists.
# =========================================================

def _carousel_search_text(
    carousel,
):
    if not isinstance(
        carousel,
        dict,
    ):
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

    if isinstance(
        slides,
        list,
    ):
        for slide in slides:
            if not isinstance(
                slide,
                dict,
            ):
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
    if not isinstance(
        item,
        dict,
    ):
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

    if isinstance(
        tags,
        list,
    ):
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

    score = len(
        carousel_tokens
        & item_tokens
    ) * 10

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

    return score


def find_best_content(
    carousel,
    content,
):
    """
    Legacy compatibility helper.

    The production render path uses source_id instead.
    """

    if not isinstance(
        content,
        list,
    ):
        return None

    candidates = [
        item
        for item in content
        if isinstance(
            item,
            dict,
        )
    ]

    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda item:
            _match_score(
                carousel,
                item,
            ),
        reverse=True,
    )

    best = ranked[0]

    if (
        _match_score(
            carousel,
            best,
        )
        <= 0
    ):
        return None

    return best


# =========================================================
# FEATURED IMAGE COMPATIBILITY
# =========================================================

def find_featured_image_url(
    carousel,
    content=None,
):
    if content is None:
        content = get_all_content()

    source_id = _clean_text(
        carousel.get("source_id")
        if isinstance(
            carousel,
            dict,
        )
        else ""
    )

    if source_id:
        matched_item = (
            find_content_by_source_id(
                source_id,
                content,
            )
        )

    else:
        matched_item = (
            find_best_content(
                carousel,
                content,
            )
        )

    if not matched_item:
        return None

    primary_fields = (
        "featured_image_url",
        "featured_image",
        "image_url",
        "image",
        "thumbnail_url",
        "thumbnail",
        "cover_image",
        "cover",
    )

    for field in primary_fields:
        value = matched_item.get(
            field
        )

        if isinstance(
            value,
            str,
        ):
            value = value.strip()

            if value:
                return value

        if isinstance(
            value,
            dict,
        ):
            for key in (
                "url",
                "src",
                "source_url",
                "image_url",
                "featured_image_url",
                "original",
                "large",
                "medium",
            ):
                candidate = value.get(
                    key
                )

                if isinstance(
                    candidate,
                    str,
                ):
                    candidate = (
                        candidate.strip()
                    )

                    if candidate:
                        return candidate

    return None


# =========================================================
# SOURCE-ONLY IMAGE ITEM
# =========================================================

def _source_only_item(item):
    """
    Copy the article but remove automatically generated
    GamerQuest image fields before searching source images.

    This prevents a bad generated thumbnail from becoming
    slide 1 simply because it already exists in the feed.

    The original source URL/data remain intact.
    """

    if not isinstance(
        item,
        dict,
    ):
        return {}

    clean = item.copy()

    image_fields = (
        "featured_image_url",
        "featured_image",
        "image_url",
        "image",
        "thumbnail_url",
        "thumbnail",
        "cover_image",
        "cover",
        "images",
        "gallery",
        "media",
        "screenshots",
        "article_images",
        "content_images",
        "image_urls",
    )

    for field in image_fields:
        clean.pop(
            field,
            None,
        )

    return clean


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
        return json.load(file)


# =========================================================
# VALIDATOR
# =========================================================

def _extract_carousel(payload):
    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "social-output.json must contain "
            "a JSON object."
        )

    if (
        payload.get("status")
        != "ready"
    ):
        raise RuntimeError(
            "Social output is not ready "
            "for rendering."
        )

    if (
        "fact_checked"
        in payload
        and payload.get(
            "fact_checked"
        ) is not True
    ):
        raise RuntimeError(
            "Social output has not "
            "passed fact-checking."
        )

    carousel = payload.get(
        "carousel"
    )

    if not isinstance(
        carousel,
        dict,
    ):
        raise RuntimeError(
            "Social output does not "
            "contain a valid carousel."
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
        raise RuntimeError(
            "Carousel must contain "
            "exactly three slides."
        )

    return carousel


# =========================================================
# RENDER
# =========================================================

def render_from_output(
    output_file=OUTPUT_FILE,
    output_dir=OUTPUT_DIR,
):
    payload = load_social_output(
        output_file
    )

    if not isinstance(
        payload,
        dict,
    ):
        return {
            "status":
                "skipped",
            "reason":
                "invalid_payload",
        }

    if (
        payload.get("status")
        != "ready"
    ):
        return {
            "status":
                "skipped",
            "reason":
                "not_ready",
        }

    if (
        payload.get(
            "fact_checked"
        ) is not True
    ):
        return {
            "status":
                "skipped",
            "reason":
                "not_fact_checked",
        }

    carousel = payload.get(
        "carousel"
    )

    if not isinstance(
        carousel,
        dict,
    ):
        return {
            "status":
                "skipped",
            "reason":
                "missing_carousel",
        }

    slides = carousel.get(
        "slides",
        [],
    )

    if (
        not isinstance(
            slides,
            list,
        )
        or len(slides) != 3
    ):
        return {
            "status":
                "skipped",
            "reason":
                "invalid_slide_count",
        }

    # =====================================================
    # SOURCE ID IS NOW MANDATORY
    # =====================================================

    source_id = _clean_text(
        payload.get("source_id")
        or carousel.get(
            "source_id"
        )
    )

    if not source_id:
        print(
            "Social render rejected: "
            "missing source_id."
        )

        return {
            "status":
                "skipped",
            "reason":
                "missing_source_id",
        }

    # =====================================================
    # EXACT ARTICLE — NO FUZZY MATCHING
    # =====================================================

    content = get_all_content()

    matched_item = (
        find_content_by_source_id(
            source_id,
            content,
        )
    )

    if not matched_item:
        print(
            "Social render rejected: "
            f"source_id not found: "
            f"{source_id}"
        )

        return {
            "status":
                "skipped",
            "reason":
                "source_id_not_found",
            "source_id":
                source_id,
        }

    print(
        "Render source_id: "
        f"{source_id}"
    )

    print(
        "Matched EXACT article: "
        + _clean_text(
            matched_item.get(
                "title"
            )
        )
    )

    # =====================================================
    # IMAGES
    #
    # FIRST TRY:
    # Original source page ONLY.
    #
    # This avoids trusting a generated GamerQuest image
    # that may itself have originated from the wrong
    # picture in a roundup article.
    # =====================================================

    source_only = (
        _source_only_item(
            matched_item
        )
    )

    topic = (
        carousel.get(
            "topic",
            "",
        )
    )

    featured_images = (
        find_images_for_article(
            source_only,
            topic=topic,
            limit=3,
        )
    )

    print(
        "Exact-source images found: "
        f"{len(featured_images)}"
    )

    # =====================================================
    # FALLBACK
    #
    # If source-page extraction gives nothing,
    # use exact article image data.
    #
    # IMPORTANT:
    # We DO NOT search another GamerQuest article.
    # =====================================================

    if not featured_images:
        print(
            "Source page supplied no usable image. "
            "Trying exact article image only."
        )

        featured_images = (
            find_images_for_article(
                matched_item,
                topic=topic,
                limit=3,
            )
        )

    print(
        "Real article/source images found: "
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

    # =====================================================
    # NO CROSS-ARTICLE FALLBACK
    # =====================================================

    featured_image = (
        featured_images[0]
        if featured_images
        else None
    )

    # =====================================================
    # RENDER
    # =====================================================

    paths = render_carousel(
        carousel,
        output_dir,
        featured_image=
            featured_image,
        featured_images=
            featured_images,
    )

    print(
        f"Renderer received "
        f"{len(featured_images)} "
        "unique image(s)."
    )

    print(
        f"Rendered slides: "
        f"{len(paths)}"
    )

    if len(
        featured_images
    ) >= 3:
        image_mode = (
            "three_real_images"
        )

        print(
            "Image mode: "
            "three real exact-source images"
        )

    elif len(
        featured_images
    ) == 2:
        image_mode = (
            "two_images"
        )

        print(
            "Image mode: "
            "two exact-source images "
            "+ crop fallback"
        )

    elif len(
        featured_images
    ) == 1:
        image_mode = (
            "single_image"
        )

        print(
            "Image mode: "
            "one exact-source image "
            "+ crop fallback"
        )

    else:
        image_mode = (
            "fallback"
        )

        print(
            "Image mode: "
            "renderer fallback"
        )

    # =====================================================
    # MANIFEST
    # =====================================================

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest = {
        "status":
            "rendered",

        "source_id":
            source_id,

        "source_title":
            matched_item.get(
                "title",
                "",
            ),

        "slides": [
            str(path)
            for path in paths
        ],

        "caption":
            payload.get(
                "caption",
                carousel.get(
                    "caption",
                    "",
                ),
            ),

        "hashtags":
            payload.get(
                "hashtags",
                carousel.get(
                    "hashtags",
                    [],
                ),
            ),

        "cta":
            payload.get(
                "cta",
                carousel.get(
                    "cta",
                    "",
                ),
            ),

        "topic":
            carousel.get(
                "topic",
                "",
            ),

        "featured_image":
            featured_image,

        "featured_images":
            featured_images,

        "image_mode":
            image_mode,
    }

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

def main():
    result = (
        render_from_output()
    )

    print(
        "Social renderer status: "
        f"{result.get('status')}"
    )


if __name__ == "__main__":
    main()
