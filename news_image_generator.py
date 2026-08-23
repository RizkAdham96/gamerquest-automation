from io import BytesIO
from pathlib import Path
import textwrap

import requests
from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
)

WIDTH = 1200
HEIGHT = 630


def get_font(size, bold=False):
    candidates = []

    if bold:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            ]
        )

    for path in candidates:
        try:
            return ImageFont.truetype(
                path,
                size=size,
            )
        except OSError:
            continue

    return ImageFont.load_default()


def download_source_image(url):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": "GamerQuestFR/1.0",
                "Accept": "image/*",
            },
        )

        response.raise_for_status()

        image = Image.open(
            BytesIO(response.content)
        )

        return image.convert("RGB")

    except Exception as exc:
        print(
            f"News artwork download failed: {exc}"
        )

        return None


def cover_image(image):
    source_width, source_height = image.size

    source_ratio = (
        source_width / source_height
    )

    target_ratio = (
        WIDTH / HEIGHT
    )

    if source_ratio > target_ratio:
        new_height = HEIGHT

        new_width = int(
            HEIGHT * source_ratio
        )
    else:
        new_width = WIDTH

        new_height = int(
            WIDTH / source_ratio
        )

    image = image.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS,
    )

    left = (
        new_width - WIDTH
    ) // 2

    top = (
        new_height - HEIGHT
    ) // 2

    return image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT,
        )
    )


def create_fallback_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (18, 20, 28),
    )

    draw = ImageDraw.Draw(
        image
    )

    for x in range(
        -300,
        WIDTH + 300,
        180,
    ):
        draw.polygon(
            [
                (x, 0),
                (x + 220, 0),
                (x - 80, HEIGHT),
                (x - 300, HEIGHT),
            ],
            fill=(
                30 + (x % 25),
                32,
                48 + (x % 15),
            ),
        )

    return image


def wrap_title(title):
    return textwrap.wrap(
        str(title),
        width=28,
    )[:3]


def generate_news_image(
    title,
    source_image_url,
    output_path,
):
    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_image = download_source_image(
        source_image_url
    )

    if source_image:
        background = cover_image(
            source_image
        )

        background = (
            ImageEnhance
            .Brightness(background)
            .enhance(0.58)
        )

        background = background.filter(
            ImageFilter.GaussianBlur(
                radius=0.6
            )
        )
    else:
        background = (
            create_fallback_background()
        )

    image = background.convert(
        "RGBA"
    )

    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    overlay_draw = ImageDraw.Draw(
        overlay
    )

    overlay_draw.rectangle(
        (0, 0, 780, HEIGHT),
        fill=(5, 6, 12, 190),
    )

    overlay_draw.rectangle(
        (0, 495, WIDTH, HEIGHT),
        fill=(5, 6, 12, 170),
    )

    image = Image.alpha_composite(
        image,
        overlay,
    )

    draw = ImageDraw.Draw(
        image
    )

    brand_font = get_font(
        27,
        bold=True,
    )

    title_font = get_font(
        56,
        bold=True,
    )

    news_font = get_font(
        27,
        bold=False,
    )

    draw.text(
        (55, 48),
        "GAMERQUEST",
        font=brand_font,
        fill=(255, 255, 255),
    )

    y = 145

    for line in wrap_title(title):
        draw.text(
            (55, y),
            line,
            font=title_font,
            fill=(255, 255, 255),
        )

        y += 70

    draw.text(
        (55, 545),
        "ACTUALITÉ GAMING",
        font=news_font,
        fill=(230, 230, 235),
    )

    final_image = image.convert(
        "RGB"
    )

    final_image.save(
        output_path,
        format="JPEG",
        quality=90,
        optimize=True,
    )

    return output_path
