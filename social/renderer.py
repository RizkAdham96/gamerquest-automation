from io import BytesIO
from pathlib import Path
import urllib.request

from PIL import (
    Image,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
)


# =========================================================
# GAMERQUEST SOCIAL RENDERER
# 3-slide cinematic carousel
# =========================================================

WIDTH = 1080
HEIGHT = 1350

SAFE_X = 78


# GamerQuest FR colors
BG = (5, 8, 15)               # #05080F
PANEL = (15, 20, 33)          # #0F1421

WHITE = (250, 250, 252)
MUTED = (192, 199, 215)

GQ_BLUE = (76, 141, 255)      # #4C8DFF
GQ_PURPLE = (159, 79, 255)    # #9F4FFF


# =========================================================
# FONT
# =========================================================

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
            return ImageFont.truetype(
                path,
                size=size,
            )

        except OSError:
            continue

    return ImageFont.load_default()


# =========================================================
# TEXT
# =========================================================

def _wrap(draw, text, font, max_width):

    words = str(text or "").split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:

        candidate = f"{current} {word}"

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
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

    lines = _wrap(
        draw,
        text,
        font,
        max_width,
    )

    if max_lines is not None:
        lines = lines[:max_lines]

    x, y = xy

    bbox = draw.textbbox(
        (0, 0),
        "Ag",
        font=font,
    )

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


# =========================================================
# FEATURED IMAGE
# =========================================================

def _load_featured_image(source):

    if not source:
        return None

    # Local image
    try:

        path = Path(str(source))

        if path.exists():

            with Image.open(path) as image:
                return image.convert("RGB").copy()

    except (
        OSError,
        ValueError,
    ):
        pass

    # Remote image
    if str(source).startswith(
        (
            "http://",
            "https://",
        )
    ):

        try:

            request = urllib.request.Request(
                str(source),
                headers={
                    "User-Agent":
                        "GamerQuest-Social/1.0",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=20,
            ) as response:

                raw = response.read()

            with Image.open(
                BytesIO(raw)
            ) as image:

                return image.convert("RGB").copy()

        except Exception:
            return None

    return None


def _image_background(
    featured_image,
    index,
):

    source = _load_featured_image(
        featured_image
    )

    if source is None:
        return None

    # Different crop per slide
    if index == 1:

        centering = (
            0.55,
            0.42,
        )

    elif index == 2:

        centering = (
            0.42,
            0.50,
        )

    else:

        centering = (
            0.58,
            0.46,
        )

    return ImageOps.fit(
        source,
        (
            WIDTH,
            HEIGHT,
        ),
        method=Image.Resampling.LANCZOS,
        centering=centering,
    )


# =========================================================
# DEPTH EFFECTS
# =========================================================

def _add_vignette(image):

    overlay = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT,
        ),
        (
            0,
            0,
            0,
            0,
        ),
    )

    draw = ImageDraw.Draw(
        overlay
    )

    # Top darkness
    for i in range(420):

        alpha = int(
            165 * (
                1 - i / 420
            )
        )

        draw.line(
            (
                0,
                i,
                WIDTH,
                i,
            ),
            fill=(
                5,
                8,
                15,
                alpha,
            ),
        )

    # Bottom darkness
    for i in range(600):

        y = HEIGHT - i - 1

        alpha = int(
            210 * (
                1 - i / 600
            )
        )

        draw.line(
            (
                0,
                y,
                WIDTH,
                y,
            ),
            fill=(
                5,
                8,
                15,
                alpha,
            ),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    )


def _draw_glow(
    image,
    center,
    radius,
    color,
    opacity=110,
):

    glow = Image.new(
        "RGBA",
        image.size,
        (
            0,
            0,
            0,
            0,
        ),
    )

    glow_draw = ImageDraw.Draw(
        glow
    )

    x, y = center

    glow_draw.ellipse(
        (
            x - radius,
            y - radius,
            x + radius,
            y + radius,
        ),
        fill=(
            color[0],
            color[1],
            color[2],
            opacity,
        ),
    )

    glow = glow.filter(
        ImageFilter.GaussianBlur(
            radius // 2
        )
    )

    return Image.alpha_composite(
        image,
        glow,
    )


def _draw_shadow_panel(
    image,
    box,
    radius=40,
    shadow_offset=18,
    shadow_blur=28,
    fill=(10, 14, 24, 220),
):

    x1, y1, x2, y2 = box

    shadow = Image.new(
        "RGBA",
        image.size,
        (
            0,
            0,
            0,
            0,
        ),
    )

    shadow_draw = ImageDraw.Draw(
        shadow
    )

    shadow_draw.rounded_rectangle(
        (
            x1 + shadow_offset,
            y1 + shadow_offset,
            x2 + shadow_offset,
            y2 + shadow_offset,
        ),
        radius=radius,
        fill=(
            0,
            0,
            0,
            150,
        ),
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(
            shadow_blur
        )
    )

    image = Image.alpha_composite(
        image,
        shadow,
    )

    panel = Image.new(
        "RGBA",
        image.size,
        (
            0,
            0,
            0,
            0,
        ),
    )

    panel_draw = ImageDraw.Draw(
        panel
    )

    panel_draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=(
            255,
            255,
            255,
            20,
        ),
        width=2,
    )

    return Image.alpha_composite(
        image,
        panel,
    )


def _draw_image_card(
    image,
    source,
    box,
    radius=44,
):

    if source is None:
        return image

    x1, y1, x2, y2 = box

    card_width = x2 - x1
    card_height = y2 - y1

    fitted = ImageOps.fit(
        source,
        (
            card_width,
            card_height,
        ),
        method=Image.Resampling.LANCZOS,
    ).convert("RGBA")

    mask = Image.new(
        "L",
        (
            card_width,
            card_height,
        ),
        0,
    )

    mask_draw = ImageDraw.Draw(
        mask
    )

    mask_draw.rounded_rectangle(
        (
            0,
            0,
            card_width,
            card_height,
        ),
        radius=radius,
        fill=255,
    )

    shadow = Image.new(
        "RGBA",
        image.size,
        (
            0,
            0,
            0,
            0,
        ),
    )

    shadow_draw = ImageDraw.Draw(
        shadow
    )

    shadow_draw.rounded_rectangle(
        (
            x1 + 15,
            y1 + 20,
            x2 + 15,
            y2 + 20,
        ),
        radius=radius,
        fill=(
            0,
            0,
            0,
            155,
        ),
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(
            25
        )
    )

    image = Image.alpha_composite(
        image,
        shadow,
    )

    image.paste(
        fitted,
        (
            x1,
            y1,
        ),
        mask,
    )

    return image


# =========================================================
# FALLBACK BACKGROUND
# =========================================================

def _fallback_background(index):

    image = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT,
        ),
        BG + (255,),
    )

    image = _draw_glow(
        image,
        (
            850,
            300,
        ),
        300,
        GQ_BLUE,
        75,
    )

    image = _draw_glow(
        image,
        (
            150,
            1000,
        ),
        280,
        GQ_PURPLE,
        65,
    )

    return image


# =========================================================
# CAROUSEL BASE
# =========================================================

def _prepare_background(
    featured_image,
    index,
):

    background = _image_background(
        featured_image,
        index,
    )

    if background is None:

        return _fallback_background(
            index
        )

    background = background.convert(
        "RGBA"
    )

    background = _add_vignette(
        background
    )

    # Brand glow
    if index == 1:

        background = _draw_glow(
            background,
            (
                100,
                760,
            ),
            260,
            GQ_BLUE,
            65,
        )

    elif index == 2:

        background = _draw_glow(
            background,
            (
                900,
                900,
            ),
            280,
            GQ_PURPLE,
            55,
        )

    else:

        background = _draw_glow(
            background,
            (
                500,
                1120,
            ),
            320,
            GQ_BLUE,
            65,
        )

    return background


# =========================================================
# SLIDE NUMBER + FOOTER
# =========================================================

def _draw_slide_number(
    draw,
    index,
    total,
):

    font = _font(
        25,
        bold=True,
    )

    text = f"{index:02d}/{total:02d}"

    bbox = draw.textbbox(
        (
            0,
            0,
        ),
        text,
        font=font,
    )

    width = (
        bbox[2]
        - bbox[0]
    )

    draw.text(
        (
            WIDTH
            - SAFE_X
            - width,
            58,
        ),
        text,
        font=font,
        fill=(
            245,
            247,
            255,
        ),
    )


def _draw_progress(
    draw,
    index,
    total,
):

    start_x = (
        WIDTH
        - SAFE_X
        - total * 32
    )

    y = HEIGHT - 73

    for position in range(total):

        active = (
            position
            == index - 1
        )

        width = (
            28
            if active
            else 10
        )

        fill = (
            GQ_BLUE
            if active
            else (
                94,
                102,
                123,
            )
        )

        draw.rounded_rectangle(
            (
                start_x,
                y,
                start_x + width,
                y + 10,
            ),
            radius=5,
            fill=fill,
        )

        start_x += (
            width + 12
        )


def _draw_footer(
    draw,
    index,
    total,
):

    y = HEIGHT - 88

    draw.text(
        (
            SAFE_X,
            y,
        ),
        "gamerquestfr.com",
        font=_font(
            25,
            bold=True,
        ),
        fill=GQ_BLUE,
    )

    _draw_progress(
        draw,
        index,
        total,
    )


# =========================================================
# TEXT LAYOUT SETTINGS
# =========================================================

def _layout_text_settings(index):

    if index == 1:

        return {
            "title_y": 635,
            "max_width": 850,
            "title_size": 74,
            "body_size": 35,
        }

    if index == 2:

        return {
            "title_y": 755,
            "max_width": 840,
            "title_size": 61,
            "body_size": 35,
        }

    return {
        "title_y": 700,
        "max_width": 850,
        "title_size": 66,
        "body_size": 35,
    }


# =========================================================
# SLIDE 1
# HOOK
# =========================================================

def _render_slide_one(
    image,
    slide,
    total,
):

    # Large depth panel
    image = _draw_shadow_panel(
        image,
        (
            55,
            585,
            1025,
            1160,
        ),
        radius=48,
        fill=(
            6,
            10,
            18,
            205,
        ),
    )

    draw = ImageDraw.Draw(
        image
    )

    # Small category
    draw.rounded_rectangle(
        (
            SAFE_X,
            620,
            SAFE_X + 205,
            668,
        ),
        radius=22,
        fill=GQ_BLUE,
    )

    draw.text(
        (
            SAFE_X + 19,
            631,
        ),
        "GAMING NEWS",
        font=_font(
            21,
            bold=True,
        ),
        fill=WHITE,
    )

    settings = _layout_text_settings(
        1
    )

    title = str(
        slide.get(
            "title"
        )
        or ""
    ).strip()

    body = str(
        slide.get(
            "body"
        )
        or ""
    ).strip()

    title_y = 700

    title_end = _draw_wrapped(
        draw,
        title,
        (
            SAFE_X,
            title_y,
        ),
        _font(
            settings["title_size"],
            bold=True,
        ),
        WHITE,
        settings["max_width"],
        spacing=12,
        max_lines=3,
    )

    accent_y = title_end + 20

    draw.rounded_rectangle(
        (
            SAFE_X,
            accent_y,
            SAFE_X + 120,
            accent_y + 9,
        ),
        radius=5,
        fill=GQ_BLUE,
    )

    draw.rounded_rectangle(
        (
            SAFE_X + 120,
            accent_y,
            SAFE_X + 185,
            accent_y + 9,
        ),
        radius=5,
        fill=GQ_PURPLE,
    )

    body_y = accent_y + 38

    _draw_wrapped(
        draw,
        body,
        (
            SAFE_X,
            body_y,
        ),
        _font(
            settings["body_size"],
        ),
        MUTED,
        settings["max_width"],
        spacing=12,
        max_lines=3,
    )

    _draw_slide_number(
        draw,
        1,
        total,
    )

    _draw_footer(
        draw,
        1,
        total,
    )

    return image


# =========================================================
# SLIDE 2
# VALUE / INFORMATION
# =========================================================

def _render_slide_two(
    image,
    slide,
    total,
    source_image,
):

    # Darker base for separation
    dark_layer = Image.new(
        "RGBA",
        image.size,
        (
            5,
            8,
            15,
            70,
        ),
    )

    image = Image.alpha_composite(
        image,
        dark_layer,
    )

    # Floating image card
    if source_image is not None:

        image = _draw_image_card(
            image,
            source_image,
            (
                80,
                150,
                1000,
                690,
            ),
            radius=48,
        )

    # Information panel
    image = _draw_shadow_panel(
        image,
        (
            55,
            720,
            1025,
            1185,
        ),
        radius=46,
        fill=(
            9,
            14,
            26,
            225,
        ),
    )

    draw = ImageDraw.Draw(
        image
    )

    # Blue-purple accent
    draw.rounded_rectangle(
        (
            SAFE_X,
            760,
            SAFE_X + 150,
            771,
        ),
        radius=5,
        fill=GQ_BLUE,
    )

    draw.rounded_rectangle(
        (
            SAFE_X + 150,
            760,
            SAFE_X + 235,
            771,
        ),
        radius=5,
        fill=GQ_PURPLE,
    )

    settings = _layout_text_settings(
        2
    )

    title = str(
        slide.get(
            "title"
        )
        or ""
    ).strip()

    body = str(
        slide.get(
            "body"
        )
        or ""
    ).strip()

    title_end = _draw_wrapped(
        draw,
        title,
        (
            SAFE_X,
            805,
        ),
        _font(
            settings["title_size"],
            bold=True,
        ),
        WHITE,
        settings["max_width"],
        spacing=12,
        max_lines=3,
    )

    _draw_wrapped(
        draw,
        body,
        (
            SAFE_X,
            title_end + 28,
        ),
        _font(
            settings["body_size"],
        ),
        MUTED,
        settings["max_width"],
        spacing=13,
        max_lines=4,
    )

    _draw_slide_number(
        draw,
        2,
        total,
    )

    _draw_footer(
        draw,
        2,
        total,
    )

    return image


# =========================================================
# SLIDE 3
# CURIOSITY + CTA
# =========================================================

def _render_slide_three(
    image,
    slide,
    total,
):

    # Strong lower depth layer
    image = _draw_shadow_panel(
        image,
        (
            55,
            640,
            1025,
            1165,
        ),
        radius=50,
        fill=(
            6,
            10,
            18,
            225,
        ),
    )

    draw = ImageDraw.Draw(
        image
    )

    settings = _layout_text_settings(
        3
    )

    title = str(
        slide.get(
            "title"
        )
        or ""
    ).strip()

    body = str(
        slide.get(
            "body"
        )
        or ""
    ).strip()

    # Final slide label
    draw.text(
        (
            SAFE_X,
            685,
        ),
        "À RETENIR",
        font=_font(
            24,
            bold=True,
        ),
        fill=GQ_PURPLE,
    )

    title_end = _draw_wrapped(
        draw,
        title,
        (
            SAFE_X,
            730,
        ),
        _font(
            settings["title_size"],
            bold=True,
        ),
        WHITE,
        settings["max_width"],
        spacing=12,
        max_lines=3,
    )

    body_end = _draw_wrapped(
        draw,
        body,
        (
            SAFE_X,
            title_end + 25,
        ),
        _font(
            settings["body_size"],
        ),
        MUTED,
        settings["max_width"],
        spacing=13,
        max_lines=3,
    )

    # CTA button
    cta_y = min(
        body_end + 35,
        1080,
    )

    draw.rounded_rectangle(
        (
            SAFE_X,
            cta_y,
            SAFE_X + 440,
            cta_y + 75,
        ),
        radius=30,
        fill=GQ_BLUE,
    )

    draw.text(
        (
            SAFE_X + 28,
            cta_y + 20,
        ),
        "Voir la suite sur GamerQuest →",
        font=_font(
            25,
            bold=True,
        ),
        fill=WHITE,
    )

    _draw_slide_number(
        draw,
        3,
        total,
    )

    _draw_footer(
        draw,
        3,
        total,
    )

    return image


# =========================================================
# RENDER ONE SLIDE
# =========================================================

def render_slide(
    slide,
    index,
    total,
    output_path,
    featured_image=None,
):

    if total != 3:

        raise ValueError(
            "GamerQuest carousel requires exactly 3 slides."
        )

    if index not in (
        1,
        2,
        3,
    ):

        raise ValueError(
            "Slide index must be between 1 and 3."
        )

    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_image = (
        _load_featured_image(
            featured_image
        )
    )

    image = _prepare_background(
        featured_image,
        index,
    )

    if index == 1:

        image = _render_slide_one(
            image,
            slide,
            total,
        )

    elif index == 2:

        image = _render_slide_two(
            image,
            slide,
            total,
            source_image,
        )

    else:

        image = _render_slide_three(
            image,
            slide,
            total,
        )

    image = image.convert(
        "RGB"
    )

    image.save(
        output_path,
        format="PNG",
        optimize=True,
    )

    return output_path


# =========================================================
# RENDER CAROUSEL
# =========================================================

def render_carousel(
    carousel,
    output_dir,
    featured_image=None,
):

    if not isinstance(
        carousel,
        dict,
    ):

        raise ValueError(
            "Carousel must be a dictionary."
        )

    slides = carousel.get(
        "slides"
    )

    if (
        not isinstance(
            slides,
            list,
        )
        or len(slides) != 3
    ):

        raise ValueError(
            "Renderer requires exactly three slides."
        )

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    paths = []

    for index, slide in enumerate(
        slides,
        start=1,
    ):

        if not isinstance(
            slide,
            dict,
        ):

            raise ValueError(
                "Each slide must be a dictionary."
            )

        path = (
            output_dir
            / f"slide-{index:02d}.png"
        )

        render_slide(
            slide,
            index,
            3,
            path,
            featured_image=featured_image,
        )

        paths.append(
            path
        )

    return paths
