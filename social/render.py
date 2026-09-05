import json
import re
from pathlib import Path

from PIL import (
    Image,
    ImageStat,
)

from social.sources import (
    get_all_content,
)

from social.renderer import (
    render_carousel,
)

from social.openai_image_generator import (
    try_generate_carousel_images,
)


OUTPUT_FILE = Path(
    "social-output.json"
)

OUTPUT_DIR = Path(
    "social-rendered"
)

OPENAI_OUTPUT_DIR = Path(
    "social-generated"
)


# =========================================================
# CREATIVE SAFETY SETTINGS
# =========================================================

MIN_IMAGE_WIDTH = 700
MIN_IMAGE_HEIGHT = 900

BLANK_WHITE_MEAN = 242
BLANK_BLACK_MEAN = 13

MIN_BRIGHTNESS_STDDEV = 8

DUPLICATE_HASH_DISTANCE = 5


# =========================================================
# BASIC HELPERS
# =========================================================

def _clean_text(
    value,
):
    if value is None:
        return ""

    return " ".join(
        str(
            value
        ).split()
    )


def _tokens(
    value,
):
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


def _item_source_id(
    item,
):
    if not isinstance(
        item,
        dict,
    ):
        return ""

    value = _clean_text(
        item.get(
            "source_id"
        )
    )

    if value:
        return value

    slug = _clean_text(
        item.get(
            "slug"
        )
    )

    if slug:
        return (
            f"slug:{slug}"
        )

    title = _clean_text(
        item.get(
            "title"
        )
    )

    if title:
        return (
            f"title:{title}"
        )

    return ""


# =========================================================
# EXACT SOURCE MATCHING
# =========================================================

def find_content_by_source_id(
    source_id,
    content,
):
    source_id = (
        _clean_text(
            source_id
        )
    )

    if not source_id:
        return None

    if not isinstance(
        content,
        list,
    ):
        return None

    for item in content:

        if not isinstance(
            item,
            dict,
        ):
            continue

        if (
            _item_source_id(
                item
            )
            == source_id
        ):
            return item

    return None


# =========================================================
# LEGACY SEARCH HELPERS
#
# These remain ONLY because the existing unit tests
# depend on find_featured_image_url().
#
# Production with source_id NEVER uses fuzzy matching
# for images anymore.
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

    slides = (
        carousel.get(
            "slides",
            [],
        )
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
    item,
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

    tags = (
        item.get(
            "tags",
            [],
        )
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


def _match_score(
    carousel,
    item,
):
    carousel_tokens = (
        _tokens(
            _carousel_search_text(
                carousel
            )
        )
    )

    item_tokens = (
        _tokens(
            _content_search_text(
                item
            )
        )
    )

    if (
        not carousel_tokens
        or not item_tokens
    ):
        return 0

    score = (
        len(
            carousel_tokens
            & item_tokens
        )
        * 10
    )

    topic = (
        _clean_text(
            carousel.get(
                "topic"
            )
        )
        .lower()
    )

    title = (
        _clean_text(
            item.get(
                "title"
            )
        )
        .lower()
    )

    if (
        topic
        and title
    ):
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
# FEATURED IMAGE LEGACY HELPER
# =========================================================

def find_featured_image_url(
    carousel,
    content=None,
):
    """
    Compatibility helper for old tests.

    IMPORTANT:
    Production social publishing does NOT use this
    as an image fallback anymore.
    """

    if content is None:
        content = (
            get_all_content()
        )

    source_id = ""

    if isinstance(
        carousel,
        dict,
    ):
        source_id = (
            _clean_text(
                carousel.get(
                    "source_id"
                )
            )
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

        value = (
            matched_item.get(
                field
            )
        )

        if isinstance(
            value,
            str,
        ):
            value = (
                value.strip()
            )

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

                candidate = (
                    value.get(
                        key
                    )
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

        value = (
            matched_item.get(
                field
            )
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
                image = (
                    image.strip()
                )

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

                    candidate = (
                        image.get(
                            key
                        )
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
# CTA CLEANER
# =========================================================

CTA_PATTERNS = (
    r"\s*Lire la suite sur "
    r"GamerQuest(?:\.fr|fr)?\.?",

    r"\s*Lire la suite sur "
    r"GamerQuestfr\.com\.?",

    r"\s*Plus d['’]informations "
    r"sur GamerQuest(?:\.fr|fr)?\.?",

    r"\s*Plus d['’]infos "
    r"sur GamerQuest(?:\.fr|fr)?\.?",

    r"\s*Découvre la suite "
    r"sur GamerQuest(?:\.fr|fr)?\.?",

    r"\s*Découvrir la suite "
    r"sur GamerQuest(?:\.fr|fr)?\.?",
)


def remove_redundant_cta(
    text,
):
    """
    Remove CTA phrases from slide body text.

    The renderer already displays the GamerQuest
    website and final CTA separately.
    """

    text = _clean_text(
        text
    )

    if not text:
        return ""

    for pattern in CTA_PATTERNS:

        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(
        r"\s+([,.!?;:])",
        r"\1",
        text,
    )

    text = re.sub(
        r"\.{2,}",
        ".",
        text,
    )

    text = (
        text.strip(
            " -"
        )
    )

    return text


def clean_carousel_copy(
    carousel,
):
    if not isinstance(
        carousel,
        dict,
    ):
        return carousel

    cleaned = dict(
        carousel
    )

    slides = (
        carousel.get(
            "slides",
            [],
        )
    )

    cleaned_slides = []

    for slide in slides:

        if not isinstance(
            slide,
            dict,
        ):
            cleaned_slides.append(
                slide
            )
            continue

        new_slide = dict(
            slide
        )

        new_slide[
            "body"
        ] = (
            remove_redundant_cta(
                slide.get(
                    "body"
                )
            )
        )

        cleaned_slides.append(
            new_slide
        )

    cleaned[
        "slides"
    ] = cleaned_slides

    return cleaned


# =========================================================
# IMAGE QUALITY VALIDATION
# =========================================================

def _open_local_image(
    path,
):
    path = Path(
        path
    )

    if not path.exists():
        raise RuntimeError(
            "Generated image is missing: "
            f"{path}"
        )

    try:
        with Image.open(
            path
        ) as source:

            image = (
                source
                .convert(
                    "RGB"
                )
                .copy()
            )

    except Exception as error:
        raise RuntimeError(
            "Generated image could not "
            f"be opened: {path}"
        ) from error

    return image


def _image_brightness_stats(
    image,
):
    grayscale = (
        image.convert(
            "L"
        )
    )

    stat = ImageStat.Stat(
        grayscale
    )

    mean = float(
        stat.mean[0]
    )

    stddev = float(
        stat.stddev[0]
    )

    return (
        mean,
        stddev,
    )


def _is_blank_image(
    image,
):
    mean, stddev = (
        _image_brightness_stats(
            image
        )
    )

    almost_white = (
        mean >= BLANK_WHITE_MEAN
        and stddev
        <= MIN_BRIGHTNESS_STDDEV
    )

    almost_black = (
        mean <= BLANK_BLACK_MEAN
        and stddev
        <= MIN_BRIGHTNESS_STDDEV
    )

    return (
        almost_white
        or almost_black
    )


def _average_hash(
    image,
):
    """
    Small perceptual hash.

    Used only to detect duplicate /
    near-duplicate carousel images.
    """

    image = (
        image
        .convert(
            "L"
        )
        .resize(
            (
                16,
                16,
            ),
            Image.Resampling.LANCZOS,
        )
    )

    pixels = list(
        image.getdata()
    )

    average = (
        sum(
            pixels
        )
        / len(
            pixels
        )
    )

    bits = [
        1
        if pixel >= average
        else 0
        for pixel in pixels
    ]

    return bits


def _hash_distance(
    first,
    second,
):
    return sum(
        left != right
        for left, right
        in zip(
            first,
            second,
        )
    )


def validate_generated_images(
    paths,
):
    """
    Hard production gate.

    This does NOT try to decide whether Wolverine
    looks exactly like Wolverine.

    It prevents the proven technical failures:
    - missing images
    - corrupt images
    - blank/white images
    - blank/black images
    - tiny images
    - duplicate/near-duplicate images
    """

    if not isinstance(
        paths,
        (
            list,
            tuple,
        ),
    ):
        raise RuntimeError(
            "Generated images must "
            "be a list."
        )

    if len(paths) != 3:
        raise RuntimeError(
            "Creative validation failed: "
            "exactly 3 generated images "
            "are required."
        )

    validated_paths = []
    hashes = []

    for index, path in enumerate(
        paths,
        start=1,
    ):

        image = (
            _open_local_image(
                path
            )
        )

        if (
            image.width
            < MIN_IMAGE_WIDTH
            or image.height
            < MIN_IMAGE_HEIGHT
        ):
            raise RuntimeError(
                "Creative validation failed: "
                f"slide {index} image "
                "is too small."
            )

        if _is_blank_image(
            image
        ):
            raise RuntimeError(
                "Creative validation failed: "
                f"slide {index} is blank "
                "or nearly blank."
            )

        image_hash = (
            _average_hash(
                image
            )
        )

        for previous_index, previous_hash in enumerate(
            hashes,
            start=1,
        ):

            distance = (
                _hash_distance(
                    previous_hash,
                    image_hash,
                )
            )

            if (
                distance
                <= DUPLICATE_HASH_DISTANCE
            ):
                raise RuntimeError(
                    "Creative validation failed: "
                    f"slide {index} is duplicate "
                    "or too similar to "
                    f"slide {previous_index}."
                )

        hashes.append(
            image_hash
        )

        validated_paths.append(
            str(
                Path(
                    path
                )
            )
        )

    return validated_paths


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
            "social-output.json "
            "was not found."
        )

    with output_file.open(
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(
            file
        )


# =========================================================
# BASIC CAROUSEL VALIDATION
# =========================================================

def _extract_carousel(
    payload,
):
    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "social-output.json "
            "must contain a JSON object."
        )

    if (
        payload.get(
            "status"
        )
        != "ready"
    ):
        raise RuntimeError(
            "Social output is not "
            "ready for rendering."
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
            "Social output has not "
            "passed fact-checking."
        )

    carousel = (
        payload.get(
            "carousel"
        )
    )

    if not isinstance(
        carousel,
        dict,
    ):
        raise RuntimeError(
            "Social output does not "
            "contain a valid carousel."
        )

    slides = (
        carousel.get(
            "slides"
        )
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
            "Carousel must contain "
            "exactly three slides."
        )

    return carousel


# =========================================================
# OPENAI IMAGE GENERATION
# =========================================================

def _generate_openai_images(
    carousel,
    matched_item,
):
    if not matched_item:
        raise RuntimeError(
            "Exact source article "
            "was not found."
        )

    print(
        "Trying OpenAI visual generation..."
    )

    generated = (
        try_generate_carousel_images(
            carousel=carousel,
            source_item=matched_item,
            output_dir=(
                OPENAI_OUTPUT_DIR
            ),
        )
    )

    if not isinstance(
        generated,
        (
            list,
            tuple,
        ),
    ):
        generated = []

    generated = [
        str(
            path
        )
        for path in generated
        if path
    ]

    if len(
        generated
    ) != 3:

        raise RuntimeError(
            "OpenAI did not generate "
            "a complete 3-image carousel. "
            "Publishing stopped. "
            "Web-image fallback is disabled "
            "in production to prevent "
            "unrelated images."
        )

    print(
        "OpenAI generated "
        "three images."
    )

    return generated


# =========================================================
# MANIFEST
# =========================================================

def _write_manifest(
    output_dir,
    carousel,
    rendered_paths,
    source_id="",
    image_mode="",
):
    output_dir = Path(
        output_dir
    )

    manifest = {
        "source_id":
            source_id,

        "caption":
            _clean_text(
                carousel.get(
                    "caption"
                )
            ),

        "cta":
            _clean_text(
                carousel.get(
                    "cta"
                )
            ),

        "hashtags":
            carousel.get(
                "hashtags",
                [],
            ),

        "slides": [
            str(
                path
            )
            for path in rendered_paths
        ],

        "image_mode":
            image_mode,
    }

    manifest_path = (
        output_dir
        / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return manifest_path


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

    # -----------------------------------------------------
    # Normal skips
    # -----------------------------------------------------

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

    carousel = (
        payload.get(
            "carousel"
        )
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

    slides = (
        carousel.get(
            "slides"
        )
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

    carousel = (
        clean_carousel_copy(
            carousel
        )
    )

    # -----------------------------------------------------
    # SOURCE ID
    # -----------------------------------------------------

    source_id = (
        _clean_text(
            payload.get(
                "source_id"
            )
            or carousel.get(
                "source_id"
            )
        )
    )

    output_dir = Path(
        output_dir
    )

    # =====================================================
    # LEGACY UNIT-TEST MODE
    #
    # Existing renderer tests do not provide source_id.
    # Keep this fallback ONLY for local/test compatibility.
    #
    # It is NOT used by real GamerQuest production posts.
    # =====================================================

    if not source_id:

        print(
            "Legacy/test payload: "
            "no source_id supplied."
        )

        print(
            "Skipping OpenAI/article lookup "
            "and using renderer fallback."
        )

        rendered_paths = (
            render_carousel(
                carousel,
                output_dir,
            )
        )

        manifest_path = (
            _write_manifest(
                output_dir=output_dir,
                carousel=carousel,
                rendered_paths=
                    rendered_paths,
                source_id="",
                image_mode=
                    "test_fallback",
            )
        )

        print(
            "Final image mode: "
            "test_fallback"
        )

        print(
            "Rendered slides: "
            f"{len(rendered_paths)}"
        )

        return {
            "status":
                "rendered",

            "slides":
                [
                    str(
                        path
                    )
                    for path
                    in rendered_paths
                ],

            "manifest":
                str(
                    manifest_path
                ),

            "image_mode":
                "test_fallback",
        }

    # =====================================================
    # REAL PRODUCTION MODE
    # =====================================================

    print(
        "Render source_id: "
        f"{source_id}"
    )

    content = (
        get_all_content()
    )

    matched_item = (
        find_content_by_source_id(
            source_id,
            content,
        )
    )

    if not matched_item:

        raise RuntimeError(
            "Production rendering stopped: "
            "the exact source article "
            f"could not be found for "
            f"source_id {source_id}."
        )

    print(
        "Matched EXACT article: "
        + _clean_text(
            matched_item.get(
                "title"
            )
        )
    )

    # -----------------------------------------------------
    # OPENAI ONLY
    #
    # CRITICAL:
    # NO image_finder fallback.
    # NO generic web images.
    # NO unrelated article images.
    # -----------------------------------------------------

    generated_images = (
        _generate_openai_images(
            carousel,
            matched_item,
        )
    )

    # -----------------------------------------------------
    # HARD QUALITY GATE
    # -----------------------------------------------------

    print(
        "Running creative image "
        "quality validation..."
    )

    validated_images = (
        validate_generated_images(
            generated_images
        )
    )

    print(
        "Creative validation: PASS"
    )

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    print(
        "Final image mode: "
        "openai_validated"
    )

    print(
        "Images sent to renderer: "
        f"{len(validated_images)}"
    )

    for index, image_path in enumerate(
        validated_images,
        start=1,
    ):
        print(
            f"Carousel image "
            f"{index}: "
            f"{image_path}"
        )

    rendered_paths = (
        render_carousel(
            carousel,
            output_dir,
            featured_images=
                validated_images,
        )
    )

    if len(
        rendered_paths
    ) != 3:

        raise RuntimeError(
            "Renderer did not produce "
            "exactly three slides. "
            "Publishing stopped."
        )

    # -----------------------------------------------------
    # FINAL FILE CHECK
    # -----------------------------------------------------

    for path in rendered_paths:

        path = Path(
            path
        )

        if not path.exists():

            raise RuntimeError(
                "Rendered slide is missing: "
                f"{path}"
            )

        try:
            with Image.open(
                path
            ) as image:

                if image.size != (
                    1080,
                    1350,
                ):
                    raise RuntimeError(
                        "Rendered slide has "
                        "invalid dimensions: "
                        f"{path}"
                    )

        except RuntimeError:
            raise

        except Exception as error:
            raise RuntimeError(
                "Rendered slide could "
                "not be validated: "
                f"{path}"
            ) from error

    # -----------------------------------------------------
    # MANIFEST
    # -----------------------------------------------------

    manifest_path = (
        _write_manifest(
            output_dir=
                output_dir,

            carousel=
                carousel,

            rendered_paths=
                rendered_paths,

            source_id=
                source_id,

            image_mode=
                "openai_validated",
        )
    )

    print(
        "Rendered slides: "
        f"{len(rendered_paths)}"
    )

    print(
        "Social renderer status: "
        "rendered"
    )

    return {
        "status":
            "rendered",

        "source_id":
            source_id,

        "slides":
            [
                str(
                    path
                )
                for path
                in rendered_paths
            ],

        "manifest":
            str(
                manifest_path
            ),

        "image_mode":
            "openai_validated",
    }


# =========================================================
# CLI
# =========================================================

def main():
    result = (
        render_from_output()
    )

    status = (
        result.get(
            "status"
        )
        if isinstance(
            result,
            dict,
        )
        else ""
    )

    if status == "skipped":

        print(
            "Social renderer skipped."
        )

        reason = (
            result.get(
                "reason",
                "",
            )
        )

        if reason:
            print(
                "Reason: "
                f"{reason}"
            )

        return

    print(
        "Social renderer completed."
    )


if __name__ == "__main__":
    main()
