from io import BytesIO
from pathlib import Path
import urllib.request

from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
)


# =========================================================
# GAMERQUEST SOCIAL RENDERER
# =========================================================

WIDTH = 1080
HEIGHT = 1350

SAFE_X = 72

BG = (5, 8, 15)
PANEL = (12, 17, 29)

WHITE = (250, 250, 252)
MUTED = (196, 203, 218)

GQ_BLUE = (76, 141, 255)
GQ_PURPLE = (159, 79, 255)

LOGO_FILE = (
    Path(__file__).resolve().parent
    / "assets"
    / "gamerquest-logo.png"
)


# =========================================================
# FONT
# =========================================================

def _font(size, bold=False):
    candidates = [
        (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans-Bold.ttf"
            if bold
            else
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans.ttf"
        ),
        (
            "/usr/share/fonts/truetype/liberation2/"
            "LiberationSans-Bold.ttf"
            if bold
            else
            "/usr/share/fonts/truetype/liberation2/"
            "LiberationSans-Regular.ttf"
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
# TEXT HELPERS
# =========================================================

def _clean(value):
    return " ".join(
        str(value or "").split()
    )


def _wrap(
    draw,
    text,
    font,
    max_width,
):
    words = _clean(text).split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:
        candidate = (
            f"{current} {word}"
        )

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
        )

        width = (
            bbox[2]
            - bbox[0]
        )

        if width <= max_width:
            current = candidate

        else:
            lines.append(
                current
            )

            current = word

    lines.append(
        current
    )

    return lines


def _draw_wrapped(
    draw,
    text,
    xy,
    font,
    fill,
    max_width,
    spacing=12,
    max_lines=None,
):
    lines = _wrap(
        draw,
        text,
        font,
        max_width,
    )

    if max_lines:
        lines = (
            lines[:max_lines]
        )

    x, y = xy

    bbox = draw.textbbox(
        (0, 0),
        "Ag",
        font=font,
    )

    line_height = (
        bbox[3]
        - bbox[1]
    )

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
        )

        y += (
            line_height
            + spacing
        )

    return y


def _text_height(
    draw,
    text,
    font,
    max_width,
    spacing=12,
    max_lines=None,
):
    lines = _wrap(
        draw,
        text,
        font,
        max_width,
    )

    if max_lines:
        lines = lines[
            :max_lines
        ]

    if not lines:
        return 0

    bbox = draw.textbbox(
        (0, 0),
        "Ag",
        font=font,
    )

    line_height = (
        bbox[3]
        - bbox[1]
    )

    return (
        len(lines)
        * line_height
        + max(
            0,
            len(lines) - 1,
        )
        * spacing
    )


# =========================================================
# IMAGE LOADING
# =========================================================

def _load_featured_image(
    source,
):
    if not source:
        return None

    if isinstance(
        source,
        Image.Image,
    ):
        return (
            source
            .convert("RGB")
            .copy()
        )

    if isinstance(
        source,
        (
            bytes,
            bytearray,
        ),
    ):
        try:
            with Image.open(
                BytesIO(source)
            ) as image:
                return (
                    image
                    .convert("RGB")
                    .copy()
                )

        except Exception:
            return None

    try:
        path = Path(
            str(source)
        )

        if path.exists():
            with Image.open(
                path
            ) as image:
                return (
                    image
                    .convert("RGB")
                    .copy()
                )

    except Exception:
        pass

    text = str(
        source
    )

    if text.startswith(
        (
            "http://",
            "https://",
        )
    ):
        try:
            request = (
                urllib.request.Request(
                    text,
                    headers={
                        "User-Agent":
                            "GamerQuest-Social/1.0",
                    },
                )
            )

            with urllib.request.urlopen(
                request,
                timeout=20,
            ) as response:
                raw = response.read()

            with Image.open(
                BytesIO(raw)
            ) as image:
                return (
                    image
                    .convert("RGB")
                    .copy()
                )

        except Exception:
            return None

    return None


# =========================================================
# IMAGE ENHANCEMENT
# =========================================================

def _enhance_image(
    image,
):
    if image is None:
        return None

    image = image.convert(
        "RGB"
    )

    image = (
        ImageEnhance.Contrast(
            image
        ).enhance(
            1.08
        )
    )

    image = (
        ImageEnhance.Color(
            image
        ).enhance(
            1.06
        )
    )

    image = (
        ImageEnhance.Sharpness(
            image
        ).enhance(
            1.08
        )
    )

    return image


# =========================================================
# BACKGROUND
# =========================================================

def _image_background(
    featured_image,
    index,
):
    source = (
        _load_featured_image(
            featured_image
        )
    )

    if source is None:
        return None

    source = (
        _enhance_image(
            source
        )
    )

    if index == 1:
        centering = (
            0.50,
            0.40,
        )

    elif index == 2:
        centering = (
            0.50,
            0.43,
        )

    else:
        centering = (
            0.50,
            0.42,
        )

    return ImageOps.fit(
        source,
        (
            WIDTH,
            HEIGHT,
        ),
        method=(
            Image.Resampling.LANCZOS
        ),
        centering=centering,
    )


# =========================================================
# FALLBACK BACKGROUND
# =========================================================

def _fallback_background(
    index,
):
    image = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT,
        ),
        BG + (255,),
    )

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

    draw = ImageDraw.Draw(
        glow
    )

    if index == 1:
        color = (
            GQ_BLUE
        )

        center = (
            800,
            350,
        )

    elif index == 2:
        color = (
            GQ_PURPLE
        )

        center = (
            250,
            500,
        )

    else:
        color = (
            GQ_BLUE
        )

        center = (
            820,
            750,
        )

    radius = 430

    draw.ellipse(
        (
            center[0] - radius,
            center[1] - radius,
            center[0] + radius,
            center[1] + radius,
        ),
        fill=(
            color[0],
            color[1],
            color[2],
            95,
        ),
    )

    glow = glow.filter(
        ImageFilter.GaussianBlur(
            180
        )
    )

    return Image.alpha_composite(
        image,
        glow,
    )


# =========================================================
# DARK GRADIENT
# =========================================================

def _dark_gradient(
    image,
    start_y,
    strength=230,
):
    overlay = Image.new(
        "RGBA",
        image.size,
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

    available = (
        HEIGHT
        - start_y
    )

    if available <= 0:
        return image

    for y in range(
        start_y,
        HEIGHT,
    ):
        ratio = (
            (y - start_y)
            / available
        )

        alpha = int(
            strength
            * ratio
        )

        draw.line(
            (
                0,
                y,
                WIDTH,
                y,
            ),
            fill=(
                BG[0],
                BG[1],
                BG[2],
                alpha,
            ),
        )

    return Image.alpha_composite(
        image,
        overlay,
    )


def _top_gradient(
    image,
):
    overlay = Image.new(
        "RGBA",
        image.size,
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

    height = 190

    for y in range(
        height
    ):
        ratio = (
            1
            - y / height
        )

        alpha = int(
            135
            * ratio
        )

        draw.line(
            (
                0,
                y,
                WIDTH,
                y,
            ),
            fill=(
                0,
                0,
                0,
                alpha,
            ),
        )

    return Image.alpha_composite(
        image,
        overlay,
    )


# =========================================================
# BRAND LIGHTING
# =========================================================

def _brand_glow(
    image,
    index,
):
    layer = Image.new(
        "RGBA",
        image.size,
        (
            0,
            0,
            0,
            0,
        ),
    )

    draw = ImageDraw.Draw(
        layer
    )

    if index == 1:
        center = (
            110,
            960,
        )

        color = (
            GQ_PURPLE
        )

    elif index == 2:
        center = (
            850,
            970,
        )

        color = (
            GQ_BLUE
        )

    else:
        center = (
            180,
            1050,
        )

        color = (
            GQ_PURPLE
        )

    radius = 300

    draw.ellipse(
        (
            center[0] - radius,
            center[1] - radius,
            center[0] + radius,
            center[1] + radius,
        ),
        fill=(
            color[0],
            color[1],
            color[2],
            38,
        ),
    )

    layer = layer.filter(
        ImageFilter.GaussianBlur(
            130
        )
    )

    return Image.alpha_composite(
        image,
        layer,
    )


# =========================================================
# BACKGROUND PREPARATION
# =========================================================

def _prepare_background(
    featured_image,
    index,
):
    background = (
        _image_background(
            featured_image,
            index,
        )
    )

    if background is None:
        background = (
            _fallback_background(
                index
            )
        )

    else:
        background = (
            background.convert(
                "RGBA"
            )
        )

    background = (
        _top_gradient(
            background
        )
    )

    background = (
        _brand_glow(
            background,
            index,
        )
    )

    if index == 1:
        background = (
            _dark_gradient(
                background,
                620,
                strength=245,
            )
        )

    else:
        background = (
            _dark_gradient(
                background,
                720,
                strength=220,
            )
        )

    return background


# =========================================================
# LOGO
# =========================================================

def _draw_brand_logo(
    image,
    large=False,
):
    if not LOGO_FILE.exists():
        return image

    try:
        with Image.open(
            LOGO_FILE
        ) as logo_source:
            logo = (
                logo_source
                .convert("RGBA")
                .copy()
            )

    except Exception:
        return image

    if large:
        size = 92
    else:
        size = 56

    logo.thumbnail(
        (
            size,
            size,
        ),
        Image.Resampling.LANCZOS,
    )

    x = SAFE_X
    y = 42

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

    shadow_logo = (
        logo.copy()
    )

    shadow_logo = (
        shadow_logo.filter(
            ImageFilter.GaussianBlur(
                10
            )
        )
    )

    shadow.alpha_composite(
        shadow_logo,
        (
            x + 3,
            y + 6,
        ),
    )

    image = (
        Image.alpha_composite(
            image,
            shadow,
        )
    )

    image.alpha_composite(
        logo,
        (
            x,
            y,
        ),
    )

    draw = ImageDraw.Draw(
        image
    )

    text_x = (
        x
        + logo.width
        + 16
    )

    text_y = (
        y
        + max(
            0,
            (
                logo.height
                - 30
            )
            // 2
        )
    )

    draw.text(
        (
            text_x,
            text_y,
        ),
        "GAMERQUEST FR",
        font=_font(
            28 if large else 23,
            bold=True,
        ),
        fill=WHITE,
    )

    return image


# =========================================================
# SLIDE NUMBER
# =========================================================

def _draw_slide_number(
    draw,
    index,
    total,
):
    font = _font(
        27,
        bold=True,
    )

    text = (
        f"{index}/{total}"
    )

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    width = (
        bbox[2]
        - bbox[0]
    )

    x = (
        WIDTH
        - SAFE_X
        - width
    )

    draw.text(
        (
            x,
            56,
        ),
        text,
        font=font,
        fill=WHITE,
    )


# =========================================================
# CATEGORY BADGE
# =========================================================

def _draw_badge(
    draw,
    text,
    x,
    y,
):
    text = (
        _clean(text)
        .upper()
    )

    if not text:
        text = "GAMING"

    font = _font(
        22,
        bold=True,
    )

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    text_width = (
        bbox[2]
        - bbox[0]
    )

    width = (
        text_width
        + 34
    )

    height = 45

    draw.rounded_rectangle(
        (
            x,
            y,
            x + width,
            y + height,
        ),
        radius=9,
        fill=(
            GQ_PURPLE[0],
            GQ_PURPLE[1],
            GQ_PURPLE[2],
            235,
        ),
    )

    draw.text(
        (
            x + 17,
            y + 10,
        ),
        text,
        font=font,
        fill=WHITE,
    )

    return (
        x + width
    )


# =========================================================
# ACCENT LINE
# =========================================================

def _draw_accent_line(
    draw,
    x,
    y,
    width=125,
):
    first = int(
        width * 0.56
    )

    draw.rounded_rectangle(
        (
            x,
            y,
            x + first,
            y + 7,
        ),
        radius=4,
        fill=GQ_BLUE,
    )

    draw.rounded_rectangle(
        (
            x + first + 7,
            y,
            x + width,
            y + 7,
        ),
        radius=4,
        fill=GQ_PURPLE,
    )


# =========================================================
# INFO PANEL
# =========================================================

def _draw_panel(
    image,
    box,
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

    shadow_draw = (
        ImageDraw.Draw(
            shadow
        )
    )

    shadow_draw.rounded_rectangle(
        (
            x1 + 12,
            y1 + 18,
            x2 + 12,
            y2 + 18,
        ),
        radius=34,
        fill=(
            0,
            0,
            0,
            150,
        ),
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(
            25
        )
    )

    image = (
        Image.alpha_composite(
            image,
            shadow,
        )
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

    draw = ImageDraw.Draw(
        panel
    )

    draw.rounded_rectangle(
        box,
        radius=34,
        fill=(
            PANEL[0],
            PANEL[1],
            PANEL[2],
            224,
        ),
        outline=(
            255,
            255,
            255,
            22,
        ),
        width=2,
    )

    # Blue/purple top accent.
    accent_width = (
        x2 - x1
    )

    split = (
        x1
        + int(
            accent_width
            * 0.55
        )
    )

    draw.rounded_rectangle(
        (
            x1,
            y1,
            split,
            y1 + 8,
        ),
        radius=4,
        fill=GQ_BLUE + (255,),
    )

    draw.rounded_rectangle(
        (
            split,
            y1,
            x2,
            y1 + 8,
        ),
        radius=4,
        fill=GQ_PURPLE + (255,),
    )

    return Image.alpha_composite(
        image,
        panel,
    )


# =========================================================
# FOOTER
# =========================================================

def _draw_footer(
    draw,
    index,
):
    font = _font(
        23,
        bold=True,
    )

    draw.text(
        (
            SAFE_X,
            HEIGHT - 60,
        ),
        "gamerquestfr.com",
        font=font,
        fill=GQ_BLUE,
    )

    if index == 3:
        text = "LIRE LA SUITE →"

        bbox = draw.textbbox(
            (0, 0),
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
                HEIGHT - 60,
            ),
            text,
            font=font,
            fill=GQ_PURPLE,
        )


# =========================================================
# LAYOUT SETTINGS
#
# Kept because existing tests depend on it.
# =========================================================

def _layout_text_settings(
    index,
):
    if index == 1:
        return {
            "title_y": 790,
            "max_width": 900,
            "title_size": 72,
            "body_size": 31,
        }

    if index == 2:
        return {
            "title_y": 820,
            "max_width": 800,
            "title_size": 54,
            "body_size": 31,
        }

    return {
        "title_y": 800,
        "max_width": 800,
        "title_size": 54,
        "body_size": 31,
    }


# =========================================================
# COVER SLIDE
# =========================================================

def _render_cover(
    slide,
    image,
    index,
    total,
    category,
):
    image = (
        _draw_brand_logo(
            image,
            large=True,
        )
    )

    draw = ImageDraw.Draw(
        image
    )

    _draw_slide_number(
        draw,
        index,
        total,
    )

    settings = (
        _layout_text_settings(
            1
        )
    )

    x = SAFE_X
    y = (
        settings[
            "title_y"
        ]
    )

    badge = (
        slide.get(
            "label"
        )
        or slide.get(
            "category"
        )
        or category
        or "NEWS"
    )

    _draw_badge(
        draw,
        badge,
        x,
        y - 76,
    )

    title = _clean(
        slide.get(
            "title"
        )
    )

    body = _clean(
        slide.get(
            "body"
        )
    )

    title_font = _font(
        settings[
            "title_size"
        ],
        bold=True,
    )

    y = _draw_wrapped(
        draw,
        title,
        (
            x,
            y,
        ),
        title_font,
        WHITE,
        settings[
            "max_width"
        ],
        spacing=4,
        max_lines=4,
    )

    # Purple emphasis bar under title.
    _draw_accent_line(
        draw,
        x,
        y + 17,
        135,
    )

    y += 52

    if body:
        y = _draw_wrapped(
            draw,
            body,
            (
                x,
                y,
            ),
            _font(
                settings[
                    "body_size"
                ]
            ),
            MUTED,
            790,
            spacing=8,
            max_lines=3,
        )

    _draw_footer(
        draw,
        index,
    )

    return image


# =========================================================
# EXPLANATION SLIDE
# =========================================================

def _render_explanation(
    slide,
    image,
    index,
    total,
):
    image = (
        _draw_brand_logo(
            image,
            large=False,
        )
    )

    draw = ImageDraw.Draw(
        image
    )

    _draw_slide_number(
        draw,
        index,
        total,
    )

    settings = (
        _layout_text_settings(
            index
        )
    )

    title = _clean(
        slide.get(
            "title"
        )
    )

    body = _clean(
        slide.get(
            "body"
        )
    )

    title_font = _font(
        settings[
            "title_size"
        ],
        bold=True,
    )

    body_font = _font(
        settings[
            "body_size"
        ]
    )

    content_width = 790

    title_height = (
        _text_height(
            draw,
            title,
            title_font,
            content_width,
            spacing=5,
            max_lines=3,
        )
    )

    body_height = (
        _text_height(
            draw,
            body,
            body_font,
            content_width,
            spacing=8,
            max_lines=5,
        )
    )

    panel_height = (
        68
        + title_height
        + 36
        + body_height
        + 72
    )

    panel_height = max(
        340,
        min(
            panel_height,
            510,
        ),
    )

    panel_bottom = (
        HEIGHT
        - 105
    )

    panel_top = (
        panel_bottom
        - panel_height
    )

    panel_box = (
        SAFE_X,
        panel_top,
        WIDTH - SAFE_X,
        panel_bottom,
    )

    image = _draw_panel(
        image,
        panel_box,
    )

    draw = ImageDraw.Draw(
        image
    )

    x = (
        SAFE_X
        + 42
    )

    y = (
        panel_top
        + 48
    )

    # Slide descriptor.
    small_label = (
        "À RETENIR"
        if index == 2
        else "POURQUOI ÇA COMPTE"
    )

    draw.text(
        (
            x,
            y,
        ),
        small_label,
        font=_font(
            20,
            bold=True,
        ),
        fill=GQ_BLUE,
    )

    y += 42

    y = _draw_wrapped(
        draw,
        title,
        (
            x,
            y,
        ),
        title_font,
        WHITE,
        content_width,
        spacing=5,
        max_lines=3,
    )

    _draw_accent_line(
        draw,
        x,
        y + 15,
        105,
    )

    y += 49

    if body:
        _draw_wrapped(
            draw,
            body,
            (
                x,
                y,
            ),
            body_font,
            MUTED,
            content_width,
            spacing=8,
            max_lines=5,
        )

    _draw_footer(
        draw,
        index,
    )

    return image


# =========================================================
# SINGLE SLIDE
# =========================================================

def render_slide(
    slide,
    index,
    total,
    output_path,
    featured_image=None,
    category="",
):
    """
    Render one GamerQuest carousel slide.

    Slide 1:
        cinematic cover

    Slide 2:
        explanation

    Slide 3:
        explanation + CTA
    """

    if index not in (
        1,
        2,
        3,
    ):
        raise ValueError(
            "GamerQuest carousel "
            "supports exactly 3 slides."
        )

    image = (
        _prepare_background(
            featured_image,
            index,
        )
    )

    if index == 1:
        image = _render_cover(
            slide,
            image,
            index,
            total,
            category,
        )

    else:
        image = (
            _render_explanation(
                slide,
                image,
                index,
                total,
            )
        )

    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image.convert(
        "RGB"
    ).save(
        output_path,
        format="PNG",
        optimize=True,
    )

    return output_path


# =========================================================
# IMAGE NORMALIZATION
# =========================================================

def _normalize_featured_images(
    featured_image=None,
    featured_images=None,
):
    images = []

    if isinstance(
        featured_images,
        (
            list,
            tuple,
        ),
    ):
        for item in (
            featured_images
        ):
            if item:
                images.append(
                    item
                )

    if (
        featured_image
        and not images
    ):
        images.append(
            featured_image
        )

    if not images:
        return [
            None,
            None,
            None,
        ]

    if len(images) == 1:
        return [
            images[0],
            images[0],
            images[0],
        ]

    if len(images) == 2:
        return [
            images[0],
            images[1],
            images[0],
        ]

    return images[:3]


# =========================================================
# FULL CAROUSEL
# =========================================================

def render_carousel(
    carousel,
    output_dir,
    featured_image=None,
    featured_images=None,
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
            "Carousel must contain "
            "exactly 3 slides."
        )

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    images = (
        _normalize_featured_images(
            featured_image=
                featured_image,
            featured_images=
                featured_images,
        )
    )

    category = (
        carousel.get(
            "category"
        )
        or carousel.get(
            "content_type"
        )
        or carousel.get(
            "type"
        )
        or "NEWS"
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
                "Each slide must "
                "be a dictionary."
            )

        output_path = (
            output_dir
            / (
                f"slide-"
                f"{index:02d}.png"
            )
        )

        path = render_slide(
            slide=slide,
            index=index,
            total=3,
            output_path=
                output_path,
            featured_image=
                images[
                    index - 1
                ],
            category=category,
        )

        paths.append(
            path
        )

    return paths
