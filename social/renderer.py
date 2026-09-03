from io import BytesIO
from pathlib import Path
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageOps


WIDTH = 1080
HEIGHT = 1350

# GamerQuest FR brand colors
BG = (5, 8, 15)           # #05080F
PANEL = (15, 20, 33)      # #0F1421
WHITE = (250, 250, 252)
MUTED = (185, 194, 214)

GQ_BLUE = (76, 141, 255)      # #4C8DFF
GQ_PURPLE = (159, 79, 255)    # #9F4FFF

SAFE_X = 84


def _font(size, bold=False):
    candidates = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
        (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ),
    ]

    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue

    return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    words = str(text or "").split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:
        candidate = f"{current} {word}"

        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)

    return lines


def _draw_wrapped(
    draw,
    text,
    xy,
    font,
    fill,
    max_width,
    spacing=16,
    max_lines=None,
):
    lines = _wrap(draw, text, font, max_width)

    if max_lines is not None:
        lines = lines[:max_lines]

    x, y = xy

    bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_height = bbox[3] - bbox[1]

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
        )

        y += line_height + spacing

    return y


def _load_featured_image(source):
    if not source:
        return None

    # Local path
    try:
        path = Path(str(source))

        if path.exists():
            with Image.open(path) as image:
                return image.convert("RGB").copy()

    except (OSError, ValueError):
        pass

    # Remote URL
    if str(source).startswith(("http://", "https://")):
        try:
            request = urllib.request.Request(
                str(source),
                headers={
                    "User-Agent": "GamerQuest-Social/1.0",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=20,
            ) as response:
                raw = response.read()

            with Image.open(BytesIO(raw)) as image:
                return image.convert("RGB").copy()

        except Exception:
            return None

    return None


def _image_background(featured_image, index):
    source = _load_featured_image(featured_image)

    if source is None:
        return None

    # Different crop position depending on slide
    if index == 1:
        centering = (0.50, 0.45)

    elif index == 2:
        centering = (0.42, 0.50)

    elif index == 3:
        centering = (0.62, 0.50)

    elif index == 4:
        centering = (0.50, 0.40)

    else:
        centering = (0.50, 0.55)

    return ImageOps.fit(
        source,
        (WIDTH, HEIGHT),
        method=Image.Resampling.LANCZOS,
        centering=centering,
    )


def _apply_brand_overlay(image, index):
    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(overlay)

    # Global dark filter
    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill=(5, 8, 15, 85),
    )

    # Slide 1
    if index == 1:
        draw.rectangle(
            (0, 0, 760, HEIGHT),
            fill=(5, 8, 15, 195),
        )

        draw.rectangle(
            (0, 0, 10, HEIGHT),
            fill=GQ_BLUE + (255,),
        )

    # Slide 2
    elif index == 2:
        draw.rectangle(
            (0, 690, WIDTH, HEIGHT),
            fill=(5, 8, 15, 225),
        )

        draw.rectangle(
            (70, 745, 330, 757),
            fill=GQ_PURPLE + (255,),
        )

        draw.rectangle(
            (330, 745, 470, 757),
            fill=GQ_BLUE + (255,),
        )

    # Slide 3
    elif index == 3:
        draw.rectangle(
            (0, 0, WIDTH, 690),
            fill=(5, 8, 15, 210),
        )

        draw.rectangle(
            (70, 115, 290, 127),
            fill=GQ_BLUE + (255,),
        )

    # Slide 4
    elif index == 4:
        draw.rectangle(
            (0, 0, WIDTH, HEIGHT),
            fill=(5, 8, 15, 125),
        )

        draw.rectangle(
            (0, 0, WIDTH, 480),
            fill=(5, 8, 15, 200),
        )

        draw.rectangle(
            (70, 110, 220, 122),
            fill=GQ_PURPLE + (255,),
        )

    # Slide 5
    else:
        draw.rectangle(
            (0, 620, WIDTH, HEIGHT),
            fill=(5, 8, 15, 235),
        )

        draw.rectangle(
            (0, 0, WIDTH, 250),
            fill=(5, 8, 15, 165),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")


def _fallback_background(index):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    if index == 1:
        draw.rectangle(
            (0, 0, 10, HEIGHT),
            fill=GQ_BLUE,
        )

        draw.rounded_rectangle(
            (610, 95, 1040, 630),
            radius=60,
            fill=PANEL,
        )

    elif index == 2:
        draw.polygon(
            [
                (0, 0),
                (WIDTH, 0),
                (WIDTH, 360),
                (0, 620),
            ],
            fill=(10, 15, 28),
        )

        draw.rounded_rectangle(
            (70, 800, 1010, 1215),
            radius=48,
            fill=PANEL,
        )

    elif index == 3:
        draw.polygon(
            [
                (650, 0),
                (WIDTH, 0),
                (WIDTH, 850),
                (860, 620),
            ],
            fill=(10, 15, 28),
        )

    elif index == 4:
        draw.rounded_rectangle(
            (80, 200, 1000, 900),
            radius=55,
            fill=PANEL,
        )

    else:
        draw.rounded_rectangle(
            (70, 720, 1010, 1210),
            radius=55,
            fill=PANEL,
        )

    return image


def _draw_progress(draw, index, total, footer_y):
    dot_x = WIDTH - SAFE_X - (total * 22)

    for offset in range(total):
        fill = (
            GQ_BLUE
            if offset == index - 1
            else (80, 89, 108)
        )

        draw.ellipse(
            (
                dot_x + offset * 22,
                footer_y + 8,
                dot_x + 10 + offset * 22,
                footer_y + 18,
            ),
            fill=fill,
        )


def _draw_footer(draw, index, total):
    footer_y = HEIGHT - 105

    draw.rounded_rectangle(
        (
            55,
            footer_y - 18,
            WIDTH - 55,
            footer_y + 48,
        ),
        radius=22,
        fill=BG,
    )

    draw.text(
        (SAFE_X, footer_y),
        "gamerquestfr.com",
        font=_font(
            27,
            bold=True,
        ),
        fill=GQ_BLUE,
    )

    _draw_progress(
        draw,
        index,
        total,
        footer_y,
    )


def _draw_slide_number(draw, index, total):
    draw.text(
        (WIDTH - 190, 60),
        f"{index:02d}/{total:02d}",
        font=_font(
            26,
            bold=True,
        ),
        fill=WHITE,
    )


def _layout_text_settings(index):
    if index == 1:
        return {
            "title_y": 215,
            "max_width": 800,
            "title_size": 72,
            "body_size": 36,
        }

    if index == 2:
        return {
            "title_y": 790,
            "max_width": 900,
            "title_size": 62,
            "body_size": 36,
        }

    if index == 3:
        return {
            "title_y": 200,
            "max_width": 820,
            "title_size": 62,
            "body_size": 36,
        }

    if index == 4:
        return {
            "title_y": 200,
            "max_width": 850,
            "title_size": 60,
            "body_size": 35,
        }

    return {
        "title_y": 720,
        "max_width": 900,
        "title_size": 64,
        "body_size": 36,
    }


def render_slide(
    slide,
    index,
    total,
    output_path,
    featured_image=None,
):
    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = _image_background(
        featured_image,
        index,
    )

    if image is not None:
        image = _apply_brand_overlay(
            image,
            index,
        )

    else:
        image = _fallback_background(index)

    draw = ImageDraw.Draw(image)

    _draw_slide_number(
        draw,
        index,
        total,
    )

    settings = _layout_text_settings(index)

    title = str(
        slide.get("title") or ""
    ).strip()

    body = str(
        slide.get("body") or ""
    ).strip()

    title_font = _font(
        settings["title_size"],
        bold=True,
    )

    body_font = _font(
        settings["body_size"],
    )

    y = _draw_wrapped(
        draw,
        title,
        (
            SAFE_X,
            settings["title_y"],
        ),
        title_font,
        WHITE,
        settings["max_width"],
        spacing=14,
        max_lines=4,
    )

    y += 28

    # Accent line
    draw.rounded_rectangle(
        (
            SAFE_X,
            y,
            SAFE_X + 120,
            y + 10,
        ),
        radius=5,
        fill=GQ_BLUE,
    )

    draw.rounded_rectangle(
        (
            SAFE_X + 120,
            y,
            SAFE_X + 185,
            y + 10,
        ),
        radius=5,
        fill=GQ_PURPLE,
    )

    y += 42

    _draw_wrapped(
        draw,
        body,
        (
            SAFE_X,
            y,
        ),
        body_font,
        MUTED,
        settings["max_width"],
        spacing=15,
        max_lines=6,
    )

    _draw_footer(
        draw,
        index,
        total,
    )

    image.save(
        output_path,
        format="PNG",
        optimize=True,
    )

    return output_path


def render_carousel(
    carousel,
    output_dir,
    featured_image=None,
):
    if not isinstance(carousel, dict):
        raise ValueError(
            "Carousel must be a dictionary."
        )

    slides = carousel.get("slides")

    if (
        not isinstance(slides, list)
        or len(slides) != 5
    ):
        raise ValueError(
            "Renderer requires exactly five slides."
        )

    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    paths = []

    for index, slide in enumerate(
        slides,
        start=1,
    ):
        if not isinstance(slide, dict):
            raise ValueError(
                "Each slide must be a dictionary."
            )

        path = (
            output_dir
            / f"slide-{index:02d}.png"
        )

        paths.append(
            render_slide(
                slide,
                index,
                len(slides),
                path,
                featured_image=featured_image,
            )
        )

    return paths
