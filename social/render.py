import json
import re
from pathlib import Path

from social.sources import get_all_content
from social.renderer import render_carousel
from social.image_finder import find_images_for_article


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
        _clean_text(
            value
        )
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


# =========================================================
# SEARCH TEXT
# =========================================================

def _carousel_search_text(
    carousel
):

    if not isinstance(
        carousel,
        dict,
    ):
        return ""

    parts = [
        carousel.get(
            "topic"
        ),
        carousel.get(
            "hook"
        ),
        carousel.get(
            "angle"
        ),
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
                slide.get(
                    "title"
                )
            )

            parts.append(
                slide.get(
                    "body"
                )
            )

    return " ".join(
        _clean_text(
            part
        )
        for part in parts
        if part
    )


def _content_search_text(
    item
):

    if not isinstance(
        item,
        dict,
    ):
        return ""

    parts = [
        item.get(
            "title"
        ),
        item.get(
            "slug"
        ),
        item.get(
            "category"
        ),
        item.get(
            "excerpt"
        ),
        item.get(
            "description"
        ),
        item.get(
            "content"
        ),
    ]

    tags = item.get(
        "tags",
        [],
    )

    if isinstance(
        tags,
        list,
    ):
        parts.extend(
            tags
        )

    return " ".join(
        _clean_text(
            part
        )
        for part in parts
        if part
    )


# =========================================================
# MATCH SCORE
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

    score = len(
        carousel_tokens
        & item_tokens
    ) * 10

    topic = _clean_text(
        carousel.get(
            "topic"
        )
    ).lower()

    title = _clean_text(
        item.get(
            "title"
        )
    ).lower()

    if topic and title:

        if topic in title:
            score += 50

        if title in topic:
            score += 30

    hook = _clean_text(
        carousel.get(
            "hook"
        )
    )

    if hook:

        score += (
            len(
                _tokens(
                    hook
                )
                & item_tokens
            )
            * 5
        )

    return score


# =========================================================
# FIND MATCHED ARTICLE
# =========================================================

def find_best_content(
    carousel,
    content,
):

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
# COMPATIBILITY FEATURED IMAGE
# =========================================================

def find_featured_image_url(
    carousel,
    content=None,
):
    """
    Backward-compatible featured image lookup.

    IMPORTANT:
    This function must NOT download or validate the image.
    Existing tests use example URLs and expect the stored
    featured image URL to be returned directly.

    The real multi-image validation happens later inside
    image_finder.py during the actual social render.
    """

    if content is None:
        content = get_all_content()

    matched_item = find_best_content(
        carousel,
        content,
    )

    if not matched_item:
        return None

    # =====================================================
    # PRIMARY FEATURED IMAGE FIELDS
    # =====================================================

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

        # Direct URL/path
        if isinstance(value, str):
            value = value.strip()

            if value:
                return value

        # Some feeds store image information in a dict.
        if isinstance(value, dict):
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

    # =====================================================
    # FALLBACK TO ARTICLE IMAGE LIST
    # =====================================================

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
        value = matched_item.get(
            field
        )

        if not isinstance(
            value,
            list,
        ):
            continue

        for image in value:
            if isinstance(
                image,
                str,
            ):
                image = image.strip()

                if image:
                    return image

            if isinstance(
                image,
                dict,
            ):
                for key in (
                    "url",
                    "src",
                    "source_url",
                    "image_url",
                    "original",
                    "large",
                    "medium",
                ):
                    candidate = image.get(
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

    if content is None:

        content = (
            get_all_content()
        )

    matched_item = (
        find_best_content(
            carousel,
            content,
        )
    )

    if not matched_item:
        return None

    images = (
        find_images_for_article(
            matched_item,
            topic=carousel.get(
                "topic",
                "",
            ),
            limit=1,
        )
    )

    if not images:
        return None

    return images[0]


# =========================================================
# LOAD JSON
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

        return json.load(
            file
        )


# =========================================================
# COMPATIBILITY VALIDATOR
# =========================================================

def _extract_carousel(
    payload
):

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "social-output.json must contain a JSON object."
        )

    if (
        payload.get(
            "status"
        )
        != "ready"
    ):
        raise RuntimeError(
            "Social output is not ready for rendering."
        )

    if (
        "fact_checked"
        in payload
        and payload.get(
            "fact_checked"
        )
        is not True
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
        not isinstance(
            slides,
            list,
        )
        or len(
            slides
        )
        != 3
    ):
        raise RuntimeError(
            "Carousel must contain exactly three slides."
        )

    return carousel


# =========================================================
# RENDER
# =========================================================

def render_from_output(
    output_file=OUTPUT_FILE,
    output_dir=OUTPUT_DIR,
):

    payload = (
        load_social_output(
            output_file
        )
    )

    # =====================================================
    # SAFE SKIPS
    # =====================================================

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
        payload.get(
            "status"
        )
        != "ready"
    ):
        return {
            "status":
                "skipped",
            "reason":
                "not_ready",
        }

    if (
        "fact_checked"
        in payload
        and payload.get(
            "fact_checked"
        )
        is not True
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
        "slides"
    )

    if (
        not isinstance(
            slides,
            list,
        )
        or len(
            slides
        )
        != 3
    ):
        return {
            "status":
                "skipped",
            "reason":
                "invalid_slide_count",
        }

    # =====================================================
    # MATCH EXACT ARTICLE
    # =====================================================

    content = (
        get_all_content()
    )

    matched_item = (
        find_best_content(
            carousel,
            content,
        )
    )

    featured_images = []

    if matched_item:

        print(
            "Matched article: "
            + _clean_text(
                matched_item.get(
                    "title"
                )
            )
        )

        # =================================================
        # FIND REAL IMAGES
        # =================================================

        featured_images = (
            find_images_for_article(
                matched_item,
                topic=carousel.get(
                    "topic",
                    "",
                ),
                limit=3,
            )
        )

    else:

        print(
            "Matched article: none"
        )

    # =====================================================
    # LOG
    # =====================================================

    print(
        "Social renderer status: rendered"
    )

    print(
        "Real article/source images found: "
        + str(
            len(
                featured_images
            )
        )
    )

    for index, image in enumerate(
        featured_images,
        start=1,
    ):

        print(
            f"Carousel image {index}: "
            f"{image}"
        )

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
        featured_image=featured_image,
        featured_images=featured_images,
    )

    print(
        f"Rendered slides: "
        f"{len(paths)}"
    )

    if len(
        featured_images
    ) >= 3:

        print(
            "Image mode: "
            "three real images"
        )

    elif len(
        featured_images
    ) == 2:

        print(
            "Image mode: "
            "two real images + crop fallback"
        )

    elif len(
        featured_images
    ) == 1:

        print(
            "Image mode: "
            "one real image + crop fallback"
        )

    else:

        print(
            "Image mode: "
            "renderer fallback"
        )

    # =====================================================
    # MANIFEST
    # =====================================================

    manifest = {

        "status":
            "rendered",

        "slides": [
            str(
                path
            )
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
                payload.get(
                    "topic",
                    "",
                ),
            ),

        "featured_image":
            featured_image,

        "featured_images":
            featured_images,

        "image_mode": (
            "three_real_images"
            if len(
                featured_images
            ) >= 3
            else
            "two_images"
            if len(
                featured_images
            ) == 2
            else
            "single_image"
            if len(
                featured_images
            ) == 1
            else
            "fallback"
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
