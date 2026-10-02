"""Hard publication contract for the GamerQuest master carousel style.

The visual reference for this contract is the Instagram carousel that the
editor approved as the permanent GamerQuest standard:
https://www.instagram.com/p/Dc9goyhFrV7/?img_index=1

This module intentionally fails closed.  A carousel that cannot fit the
approved 9:16 layout, or whose rendered package is malformed, must not reach
WordPress staging or Meta publishing.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageDraw

from social import renderer


# The editor approved edge-to-edge artwork on 2026-10-02. Bumping the
# contract prevents recovery from reusing images rendered in the old,
# contained-image layout, even when their copy and dimensions are valid.
MASTER_SPEC_VERSION = "gamerquest-carousel-v2"
MASTER_REFERENCE_POST = "https://www.instagram.com/p/Dc9goyhFrV7/?img_index=1"
MASTER_WIDTH = 1080
MASTER_HEIGHT = 1920
MASTER_SLIDE_COUNT = 3
MASTER_BRAND = "GamerQuest"

# These are the actual line caps used by renderer.py.  The gate checks the
# untruncated copy before rendering so _draw_wrapped() can never silently hide
# overflowing words from a published carousel.
_TITLE_LINE_LIMITS = {1: 4, 2: 3, 3: 3}
_BODY_LINE_LIMITS = {1: 3, 2: 5, 3: 5}


def _line_count(text: str, *, index: int, body: bool) -> int:
    settings = renderer._layout_text_settings(index)
    canvas = Image.new("RGB", (MASTER_WIDTH, MASTER_HEIGHT))
    draw = ImageDraw.Draw(canvas)

    if index == 1:
        max_width = settings["max_width"]
    else:
        max_width = MASTER_WIDTH - 2 * (renderer.SAFE_X + 42)

    font = renderer._font(
        settings["body_size"] if body else settings["title_size"],
        bold=not body,
    )
    return len(renderer._wrap(draw, text, font, max_width))


def validate_master_copy(social_output: dict) -> None:
    if not isinstance(social_output, dict):
        raise RuntimeError("Master carousel requires a social-output object.")
    if social_output.get("status") != "ready":
        raise RuntimeError("Master carousel can only publish ready social output.")
    if social_output.get("fact_checked") is not True:
        raise RuntimeError("Master carousel must be fact-checked before publishing.")

    carousel = social_output.get("carousel")
    if not isinstance(carousel, dict):
        raise RuntimeError("Master carousel payload is missing.")
    if str(carousel.get("brand", "")).strip() != MASTER_BRAND:
        raise RuntimeError("Master carousel brand must be GamerQuest.")

    slides = carousel.get("slides")
    if not isinstance(slides, list) or len(slides) != MASTER_SLIDE_COUNT:
        raise RuntimeError("Master carousel requires exactly three slides.")

    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            raise RuntimeError(f"Master carousel slide {index} is invalid.")

        title = " ".join(str(slide.get("title", "")).split())
        body = " ".join(str(slide.get("body", "")).split())
        if not title:
            raise RuntimeError(f"Master carousel slide {index} needs a title.")
        if not body:
            raise RuntimeError(f"Master carousel slide {index} needs body copy.")

        title_lines = _line_count(title, index=index, body=False)
        body_lines = _line_count(body, index=index, body=True)
        if title_lines > _TITLE_LINE_LIMITS[index]:
            raise RuntimeError(
                f"Master carousel slide {index} title is too dense: "
                f"{title_lines} lines; maximum {_TITLE_LINE_LIMITS[index]}."
            )
        if body_lines > _BODY_LINE_LIMITS[index]:
            raise RuntimeError(
                f"Master carousel slide {index} body is too dense: "
                f"{body_lines} lines; maximum {_BODY_LINE_LIMITS[index]}."
            )


def validate_rendered_package(image_paths) -> None:
    paths = [Path(path) for path in image_paths]
    if len(paths) != MASTER_SLIDE_COUNT:
        raise RuntimeError("Master carousel requires exactly three rendered images.")

    expected_names = [f"slide-{index:02d}.png" for index in range(1, 4)]
    if [path.name for path in paths] != expected_names:
        raise RuntimeError(
            "Master carousel images must be slide-01.png, slide-02.png and slide-03.png."
        )

    hashes = []
    for path in paths:
        if not path.exists():
            raise RuntimeError(f"Master carousel image is missing: {path}")
        raw = path.read_bytes()
        hashes.append(sha256(raw).hexdigest())
        try:
            with Image.open(path) as image:
                image.load()
                if image.format != "PNG":
                    raise RuntimeError(
                        f"Master carousel image must be PNG: {path.name}."
                    )
                if image.size != (MASTER_WIDTH, MASTER_HEIGHT):
                    raise RuntimeError(
                        f"Master carousel image {path.name} is {image.size}; "
                        f"expected {(MASTER_WIDTH, MASTER_HEIGHT)}."
                    )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Master carousel image is unreadable: {path.name}."
            ) from exc

    if len(set(hashes)) != MASTER_SLIDE_COUNT:
        raise RuntimeError("Master carousel rendered slides must be distinct.")


def validate_master_package(*, social_output: dict, image_paths) -> None:
    validate_master_copy(social_output)
    validate_rendered_package(image_paths)
