from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw


WIDTH = 1200
HEIGHT = 630


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
    """
    Resize and crop the source image to 1200x630
    without stretching or distorting it.
    """

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
    """
    Create a simple GamerQuest-style fallback image
    when the original article image cannot be downloaded.

    IMPORTANT:
    No text is added to the image.
    """

    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (18, 20, 28),
    )

    draw = ImageDraw.Draw(image)

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


def generate_news_image(
    title,
    source_image_url,
    output_path,
):
    """
    Generate the featured image for a GamerQuest article.

    The image contains:
    - Original article artwork
    - 1200x630 crop

    The image DOES NOT contain:
    - Article title
    - GamerQuest text
    - Category text
    - Black overlay
    - Darkening
    - Blur
    """

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
        image = cover_image(
            source_image
        )

    else:
        image = (
            create_fallback_background()
        )

    image.save(
        output_path,
        format="JPEG",
        quality=92,
        optimize=True,
    )

    return output_path
