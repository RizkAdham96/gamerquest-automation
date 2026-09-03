from io import BytesIO
from pathlib import Path
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH = 1080
HEIGHT = 1350
BG = (7, 10, 22)
PANEL = (17, 22, 43)
WHITE = (250, 250, 252)
MUTED = (202, 207, 220)
GQ_PURPLE = (124, 58, 237)
GQ_BLUE = (56, 189, 248)
SAFE_X = 84


def _font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
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


def _draw_wrapped(draw, text, xy, font, fill, max_width, spacing=16, max_lines=None):
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


def _load_featured_image(source):
    if not source:
        return None
    try:
        path = Path(str(source))
        if path.exists():
            with Image.open(path) as image:
                return image.convert("RGB").copy()
    except (OSError, ValueError):
        pass

    if str(source).startswith(("http://", "https://")):
        try:
            request = urllib.request.Request(
                str(source),
                headers={"User-Agent": "GamerQuest-Social/1.0"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
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

    canvas = ImageOps.fit(
        source,
        (WIDTH, HEIGHT),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )

    if index % 3 == 2:
        canvas = canvas.crop((0, 0, WIDTH, HEIGHT)).resize((WIDTH, HEIGHT))
    elif index % 3 == 0:
        canvas = ImageOps.fit(source, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS, centering=(0.62, 0.5))

    return canvas


def _apply_brand_overlay(image, index):
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # GamerQuest FR: deep navy/black foundation with neon purple + electric blue accents.
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(5, 7, 18, 94))
    if index % 3 == 1:
        draw.rectangle((0, 0, 760, HEIGHT), fill=(7, 9, 24, 188))
        draw.rectangle((0, 0, 18, HEIGHT), fill=GQ_PURPLE + (255,))
        draw.rectangle((18, 0, 26, HEIGHT), fill=GQ_BLUE + (255,))
    elif index % 3 == 2:
        draw.rectangle((0, 700, WIDTH, HEIGHT), fill=(7, 9, 24, 222))
        draw.rectangle((70, 748, 340, 760), fill=GQ_PURPLE + (255,))
        draw.rectangle((340, 748, 460, 760), fill=GQ_BLUE + (255,))
    else:
        draw.rectangle((0, 0, WIDTH, 650), fill=(7, 9, 24, 204))
        draw.rectangle((70, 110, 250, 124), fill=GQ_PURPLE + (255,))
        draw.rectangle((250, 110, 330, 124), fill=GQ_BLUE + (255,))

    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _fallback_background(index):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    if index % 3 == 1:
        draw.rectangle((0, 0, 18, HEIGHT), fill=GQ_PURPLE)
        draw.rectangle((18, 0, 26, HEIGHT), fill=GQ_BLUE)
        draw.rounded_rectangle((620, 90, 1045, 630), radius=60, fill=PANEL)
    elif index % 3 == 2:
        draw.polygon([(0, 0), (WIDTH, 0), (WIDTH, 350), (0, 610)], fill=(12, 16, 34))
        draw.rounded_rectangle((70, 800, 1010, 1215), radius=48, fill=PANEL)
        draw.rectangle((70, 770, 300, 784), fill=GQ_PURPLE)
        draw.rectangle((300, 770, 400, 784), fill=GQ_BLUE)
    else:
        draw.polygon([(670, 0), (WIDTH, 0), (WIDTH, 820), (880, 620)], fill=(12, 16, 34))
        draw.rectangle((70, 110, 235, 124), fill=GQ_PURPLE)
        draw.rectangle((235, 110, 305, 124), fill=GQ_BLUE)
    return image


def render_slide(slide, index, total, output_path, featured_image=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = _image_background(featured_image, index)
    image = _apply_brand_overlay(image, index) if image is not None else _fallback_background(index)
    draw = ImageDraw.Draw(image)

    brand_font = _font(32, bold=True)
    small_font = _font(26, bold=True)
    title_font = _font(72 if index == 1 else 62, bold=True)
    body_font = _font(36)

    draw.rounded_rectangle((SAFE_X - 18, 42, SAFE_X + 258, 104), radius=20, fill=BG)
    draw.text((SAFE_X, 58), "GAMERQUEST FR", font=brand_font, fill=WHITE)
    draw.rounded_rectangle((SAFE_X - 18, 100, SAFE_X + 258, 106), radius=3, fill=GQ_PURPLE)
    draw.rounded_rectangle((SAFE_X + 135, 100, SAFE_X + 258, 106), radius=3, fill=GQ_BLUE)
    draw.text((WIDTH - 190, 60), f"{index:02d}/{total:02d}", font=small_font, fill=WHITE)

    title = str(slide.get("title") or "").strip()
    body = str(slide.get("body") or "").strip()

    if index % 3 == 2:
        title_y = 785
        max_width = 900
    else:
        title_y = 230 if index == 1 else 205
        max_width = 800

    y = _draw_wrapped(draw, title, (SAFE_X, title_y), title_font, WHITE, max_width, spacing=14, max_lines=4)
    y += 30
    draw.rounded_rectangle((SAFE_X, y, SAFE_X + 105, y + 10), radius=5, fill=GQ_PURPLE)
    draw.rounded_rectangle((SAFE_X + 105, y, SAFE_X + 165, y + 10), radius=5, fill=GQ_BLUE)
    y += 42

    _draw_wrapped(draw, body, (SAFE_X, y), body_font, MUTED, max_width, spacing=15, max_lines=6)

    footer_y = HEIGHT - 105
    draw.rounded_rectangle((55, footer_y - 18, WIDTH - 55, footer_y + 48), radius=22, fill=BG)
    draw.text((SAFE_X, footer_y), "gamerquestfr.com", font=_font(27, bold=True), fill=GQ_BLUE)

    dot_x = WIDTH - SAFE_X - (total * 22)
    for offset in range(total):
        fill = GQ_PURPLE if offset == index - 1 else (95, 103, 124)
        draw.ellipse((dot_x + offset * 22, footer_y + 8, dot_x + 10 + offset * 22, footer_y + 18), fill=fill)

    image.save(output_path, format="PNG", optimize=True)
    return output_path


def render_carousel(carousel, output_dir, featured_image=None):
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
        paths.append(render_slide(slide, index, len(slides), path, featured_image=featured_image))
    return paths
