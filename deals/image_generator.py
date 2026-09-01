from io import BytesIO
from pathlib import Path

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


def create_fallback_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (20, 20, 28),
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
                30 + (x % 30),
                32,
                45 + (x % 20),
            ),
        )

    return image


def format_price(price):
    try:
        value = float(price)
    except (TypeError, ValueError):
        value = 0

    if value == 0:
        return "GRATUIT"

    return (
        f"{value:.2f} €"
        .replace(".", ",")
    )


def generate_deal_image(
    deal,
    output_path,
):
    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    store = str(
        deal.get(
            "store",
            "",
        )
    ).strip()

    try:
        original_price = float(
            deal.get(
                "original_price",
                0,
            )
            or 0
        )
    except (TypeError, ValueError):
        original_price = 0

    try:
        current_price = float(
            deal.get(
                "current_price",
                0,
            )
            or 0
        )
    except (TypeError, ValueError):
        current_price = 0

    try:
        discount = int(
            float(
                deal.get(
                    "discount_percent",
                    0,
                )
                or 0
            )
        )
    except (TypeError, ValueError):
        discount = 0

    source_image = download_image(
        deal.get(
            "image_url"
        )
    )

    if source_image:
        background = cover_image(
            source_image
        )

        background = (
            ImageEnhance
            .Brightness(background)
            .enhance(0.78)
        )

        background = background.filter(
            ImageFilter.GaussianBlur(
                radius=0.2
            )
        )

    else:
        background = (
            create_fallback_background()
        )

    image = background.convert(
        "RGBA"
    )

    # Bottom panel only.
    # No large title panel anymore.
    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    overlay_draw = ImageDraw.Draw(
        overlay
    )

    overlay_draw.rectangle(
        (
            0,
            470,
            WIDTH,
            HEIGHT,
        ),
        fill=(
            5,
            6,
            12,
            175,
        ),
    )

    image = Image.alpha_composite(
        image,
        overlay,
    )

    draw = ImageDraw.Draw(
        image
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

    # Keep GamerQuest branding.
    draw.text(
        (
            55,
            45,
        ),
        "GAMERQUEST",
        font=brand_font,
        fill=(
            255,
            255,
            255,
        ),
    )

    # =====================================================
    # IMPORTANT:
    # GAME TITLE REMOVED
    #
    # No:
    # draw.text(... title ...)
    #
    # WordPress already displays the article title.
    # =====================================================

    # Deal badge.
    if current_price <= 0:
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
            370,
            55 + badge_width,
            450,
        ),
        radius=15,
        fill=(
            255,
            255,
            255,
        ),
    )

    draw.text(
        (
            80,
            375,
        ),
        badge,
        font=badge_font,
        fill=(
            12,
            13,
            18,
        ),
    )

    # Price.
    if current_price <= 0:
        if original_price > 0:
            price_text = (
                f"{format_price(original_price)}"
                "  →  GRATUIT"
            )
        else:
            price_text = "GRATUIT"

    else:
        price_text = (
            f"{format_price(original_price)}"
            "  →  "
            f"{format_price(current_price)}"
        )

    draw.text(
        (
            55,
            495,
        ),
        price_text,
        font=price_font,
        fill=(
            255,
            255,
            255,
        ),
    )

    # Store.
    if store:
        draw.text(
            (
                55,
                555,
            ),
            store,
            font=small_font,
            fill=(
                225,
                225,
                230,
            ),
        )

    final_image = image.convert(
        "RGB"
    )

    final_image.save(
        output_path,
        format="JPEG",
        quality=92,
        optimize=True,
    )

    return output_path
