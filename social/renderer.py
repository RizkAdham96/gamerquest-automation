from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1080
HEIGHT = 1350
BG = (10, 12, 18)
PANEL = (20, 24, 34)
WHITE = (248, 249, 252)
MUTED = (176, 184, 198)
ACCENT = (255, 174, 0)
SAFE_X = 84


def _font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
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
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height + spacing

    return y


def _background(draw, index):
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BG)
    variant = index % 3

    if variant == 1:
        draw.rounded_rectangle(
            (620, 90, 1045, 630),
            radius=60,
            fill=PANEL,
        )
        draw.ellipse(
            (720, 160, 1110, 550),
            fill=(27, 30, 41),
        )
        draw.rectangle((0, 0, 18, HEIGHT), fill=ACCENT)
    elif variant == 2:
        draw.polygon(
            [(0, 0), (WIDTH, 0), (WIDTH, 350), (0, 610)],
            fill=(17, 20, 29),
        )
        draw.rounded_rectangle(
            (70, 800, 1010, 1215),
            radius=48,
            fill=PANEL,
        )
        draw.rectangle((70, 770, 280, 784), fill=ACCENT)
    else:
        draw.ellipse(
            (-230, 720, 560, 1510),
            fill=(18, 21, 31),
        )
        draw.polygon(
            [(670, 0), (WIDTH, 0), (WIDTH, 820), (880, 620)],
            fill=(17, 20, 29),
        )
        draw.rectangle((70, 110, 235, 124), fill=ACCENT)


def render_slide(slide, index, total, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    _background(draw, index)

    brand_font = _font(32, bold=True)
    small_font = _font(26, bold=True)
    title_font = _font(72 if index == 1 else 62, bold=True)
    body_font = _font(36)

    draw.text(
        (SAFE_X, 58),
        "GAMERQUEST",
        font=brand_font,
        fill=WHITE,
    )
    draw.text(
        (WIDTH - 170, 60),
        f"{index:02d}/{total:02d}",
        font=small_font,
        fill=MUTED,
    )

    title = str(slide.get("title") or "").strip()
    body = str(slide.get("body") or "").strip()

    title_y = 245 if index == 1 else 215
    y = _draw_wrapped(
        draw,
        title,
        (SAFE_X, title_y),
        title_font,
        WHITE,
        835,
        spacing=14,
        max_lines=4,
    )

    y += 42
    draw.rounded_rectangle(
        (SAFE_X, y, SAFE_X + 118, y + 12),
        radius=6,
        fill=ACCENT,
    )
    y += 52

    _draw_wrapped(
        draw,
        body,
        (SAFE_X, y),
        body_font,
        MUTED,
        820,
        spacing=15,
        max_lines=7,
    )

    footer_y = HEIGHT - 105
    draw.text(
        (SAFE_X, footer_y),
        "gamerquest.fr",
        font=_font(27, bold=True),
        fill=ACCENT,
    )

    dot_x = WIDTH - SAFE_X - (total * 22)
    for offset in range(total):
        fill = ACCENT if offset == index - 1 else (76, 82, 94)
        draw.ellipse(
            (
                dot_x + offset * 22,
                footer_y + 8,
                dot_x + 10 + offset * 22,
                footer_y + 18,
            ),
            fill=fill,
        )

    image.save(output_path, format="PNG", optimize=True)
    return output_path


def render_carousel(carousel, output_dir):
    if not isinstance(carousel, dict):
        raise ValueError("Carousel must be a dictionary.")

    slides = carousel.get("slides")
    if not isinstance(slides, list) or len(slides) != 5:
        raise ValueError("Renderer requires exactly five slides.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            raise ValueError("Each slide must be a dictionary.")

        path = output_dir / f"slide-{index:02d}.png"
        paths.append(
            render_slide(
                slide,
                index,
                len(slides),
                path,
            )
        )

    return paths
