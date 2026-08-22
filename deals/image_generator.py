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

    for font_path in candidates:
        try:
            return ImageFont.truetype(
                font_path,
                size=size,
            )
        except OSError:
            continue

    return ImageFont.load_default()


def download_image(url):
    if not url:
        return None

    try:
        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": "GamerQuestFR/1.0"
            },
        )

        response.raise_for_status()

        image = Image.open(
            BytesIO(response.content)
        )

        return image.convert("RGB")

    except Exception as exc:
        print(
            f"Artwork download failed: {exc}"
        )

        return None


def cover_image(image):
    source_width, source_height = image.size

    source_ratio = (
        source_width / source_height
    )

    target_ratio = WIDTH / HEIGHT

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


def create_fallback_background(title):
    """
    Free fallback when no game artwork
    can be downloaded.
    """

    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (20, 20, 28),
    )

    draw = ImageDraw.Draw(image)

    # Simple gaming-style geometric pattern.
    for x in range(-300, WIDTH + 300, 180):
        draw.polygon(
            [
                (x, 0),
                (x + 220, 0),
                (x - 80, HEIGHT),
                (x - 300, HEIGHT),
            ],
            fill=(
                30 + (x % 30),
                32,
                45 + (x % 20),
            ),
        )

    return image


def wrap_title(title):
    return textwrap.wrap(
        title,
        width=27,
    )[:3]


def format_price(price):
    if float(price) == 0:
        return "GRATUIT"

    return (
        f"{float(price):.2f} €"
        .replace(".", ",")
    )


def generate_deal_image(
    deal,
    output_path,
):
    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    title = str(
        deal.get("title", "GamerQuest")
    )

    store = str(
        deal.get("store", "")
    )

    original_price = float(
        deal.get("original_price", 0)
    )

    current_price = float(
        deal.get("current_price", 0)
    )

    discount = int(
        deal.get(
            "discount_percent",
            0,
        )
    )

    source_image = download_image(
        deal.get("image_url")
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
                radius=0.5
            )
        )

    else:
        background = (
            create_fallback_background(
                title
            )
        )

    image = background.convert("RGBA")

    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    overlay_draw = ImageDraw.Draw(
        overlay
    )

    # Dark gradient-like panel.
    overlay_draw.rectangle(
        (0, 0, 760, HEIGHT),
        fill=(5, 6, 12, 190),
    )

    overlay_draw.rectangle(
        (0, 470, WIDTH, HEIGHT),
        fill=(5, 6, 12, 175),
    )

    image = Image.alpha_composite(
        image,
        overlay,
    )

    draw = ImageDraw.Draw(image)

    title_font = get_font(
        58,
        bold=True,
    )

    badge_font = get_font(
        56,
        bold=True,
    )

    price_font = get_font(
        31,
        bold=True,
    )

    small_font = get_font(
        26,
        bold=False,
    )

    brand_font = get_font(
        28,
        bold=True,
    )

    # GamerQuest label.
    draw.text(
        (55, 45),
        "GAMERQUEST",
        font=brand_font,
        fill=(255, 255, 255),
    )

    # Main game title.
    y = 125

    for line in wrap_title(title):
        draw.text(
            (55, y),
            line,
            font=title_font,
            fill=(255, 255, 255),
        )

        y += 68

    # Deal badge.
    if current_price == 0:
        badge = "GRATUIT"
    else:
        badge = f"-{discount}%"

    badge_box = draw.textbbox(
        (0, 0),
        badge,
        font=badge_font,
    )

    badge_width = (
        badge_box[2]
        - badge_box[0]
        + 55
    )

    draw.rounded_rectangle(
        (
            55,
            360,
            55 + badge_width,
            435,
        ),
        radius=15,
        fill=(255, 255, 255),
    )

    draw.text(
        (80, 365),
        badge,
        font=badge_font,
        fill=(12, 13, 18),
    )

    # Prices.
    price_text = (
        f"{format_price(original_price)}"
        f"  →  "
        f"{format_price(current_price)}"
    )

    draw.text(
        (55, 485),
        price_text,
        font=price_font,
        fill=(255, 255, 255),
    )

    # Store.
    draw.text(
        (55, 545),
        store,
        font=small_font,
        fill=(225, 225, 230),
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
