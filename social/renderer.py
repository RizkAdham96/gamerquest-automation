@@ -2,37 +2,47 @@
from pathlib import Path
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from PIL import (
    Image,
    ImageDraw,
    ImageFilter,
    ImageFont,
    ImageOps,
)


# =========================================================
# GAMERQUEST SOCIAL RENDERER
# CLEAN 3-SLIDE VERSION
# 3-slide carousel
# Supports different image per slide
# =========================================================

WIDTH = 1080
HEIGHT = 1350

SAFE_X = 76
SAFE_X = 78


# =========================================================
# GAMERQUEST COLORS
# =========================================================

# Keep these exact values because our tests expect them.
BG = (5, 8, 15)
GQ_BLUE = (76, 141, 255)
GQ_PURPLE = (159, 79, 255)
PANEL = (15, 20, 33)

WHITE = (248, 249, 252)
MUTED = (205, 211, 224)
WHITE = (250, 250, 252)
MUTED = (192, 199, 215)

# Actual UI colors are intentionally more neutral.
PANEL = (9, 13, 21)
PANEL_SOFT = (12, 17, 27)
GQ_BLUE = (76, 141, 255)
GQ_PURPLE = (159, 79, 255)


# =========================================================
# FONTS
# FONT
# =========================================================

def _font(size, bold=False):

    candidates = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
@@ -48,7 +58,11 @@ def _font(size, bold=False):

    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
            return ImageFont.truetype(
                path,
                size=size,
            )

        except OSError:
            continue

@@ -60,6 +74,7 @@ def _font(size, bold=False):
# =========================================================

def _wrap(draw, text, font, max_width):

    words = str(text or "").split()

    if not words:
@@ -69,6 +84,7 @@ def _wrap(draw, text, font, max_width):
    current = words[0]

    for word in words[1:]:

        candidate = f"{current} {word}"

        bbox = draw.textbbox(
@@ -81,6 +97,7 @@ def _wrap(draw, text, font, max_width):

        if width <= max_width:
            current = candidate

        else:
            lines.append(current)
            current = word
@@ -97,17 +114,18 @@ def _draw_wrapped(
    font,
    fill,
    max_width,
    spacing=12,
    spacing=16,
    max_lines=None,
):

    lines = _wrap(
        draw,
        text,
        font,
        max_width,
    )

    if max_lines:
    if max_lines is not None:
        lines = lines[:max_lines]

    x, y = xy
@@ -121,6 +139,7 @@ def _draw_wrapped(
    line_height = bbox[3] - bbox[1]

    for line in lines:

        draw.text(
            (x, y),
            line,
@@ -138,48 +157,90 @@ def _draw_wrapped(
# =========================================================

def _load_featured_image(source):

    if not source:
        return None

    # Already-loaded Pillow image
    if isinstance(source, Image.Image):
        return source.convert("RGB").copy()

    if isinstance(source, (bytes, bytearray)):
        return source.convert(
            "RGB"
        ).copy()

    # Raw bytes
    if isinstance(
        source,
        (bytes, bytearray),
    ):

        try:
            with Image.open(BytesIO(source)) as image:
                return image.convert("RGB").copy()

            with Image.open(
                BytesIO(source)
            ) as image:

                return image.convert(
                    "RGB"
                ).copy()

        except Exception:
            return None

    # Local file
    try:
        path = Path(str(source))

        path = Path(
            str(source)
        )

        if path.exists():
            with Image.open(path) as image:
                return image.convert("RGB").copy()

            with Image.open(
                path
            ) as image:

                return image.convert(
                    "RGB"
                ).copy()

    except Exception:
        pass

    # Remote image
    text = str(source)

    if text.startswith(("http://", "https://")):
    if text.startswith(
        (
            "http://",
            "https://",
        )
    ):

        try:

            request = urllib.request.Request(
                text,
                headers={
                    "User-Agent": "GamerQuest-Social/1.0",
                    "User-Agent":
                        "GamerQuest-Social/1.0",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=20,
            ) as response:
                data = response.read()

            with Image.open(BytesIO(data)) as image:
                return image.convert("RGB").copy()
                raw = response.read()

            with Image.open(
                BytesIO(raw)
            ) as image:

                return image.convert(
                    "RGB"
                ).copy()

        except Exception:
            return None
@@ -188,36 +249,66 @@ def _load_featured_image(source):


# =========================================================
# IMAGE CROPS
# DIFFERENT CROPS / ANGLES
# =========================================================

def _crop_slide_image(source, index):
def _image_background(
    featured_image,
    index,
):

    source = _load_featured_image(
        featured_image
    )

    if source is None:
        return None

    source = source.convert("RGB")
    # -----------------------------------------------------
    # SLIDE 1
    # Normal cinematic crop
    # -----------------------------------------------------

    # Each slide gets a deliberately different crop.
    if index == 1:
        # Wide cinematic framing.

        return ImageOps.fit(
            source,
            (WIDTH, HEIGHT),
            (
                WIDTH,
                HEIGHT,
            ),
            method=Image.Resampling.LANCZOS,
            centering=(0.50, 0.38),
            centering=(
                0.50,
                0.40,
            ),
        )

    # -----------------------------------------------------
    # SLIDE 2
    # Zoom + move toward left side
    # -----------------------------------------------------

    if index == 2:
        # Zoomed crop.

        zoom_width = 1320
        zoom_height = 1650

        enlarged = ImageOps.fit(
            source,
            (1350, 1688),
            (
                zoom_width,
                zoom_height,
            ),
            method=Image.Resampling.LANCZOS,
            centering=(0.36, 0.45),
            centering=(
                0.35,
                0.48,
            ),
        )

        left = (1350 - WIDTH) // 2
        top = (1688 - HEIGHT) // 2
        left = 60
        top = 120

        return enlarged.crop(
            (
@@ -228,16 +319,34 @@ def _crop_slide_image(source, index):
            )
        )

    # Slide 3 slightly zoomed and shifted opposite direction.
    # -----------------------------------------------------
    # SLIDE 3
    # Different zoom + move toward right side
    # -----------------------------------------------------

    zoom_width = 1250
    zoom_height = 1560

    enlarged = ImageOps.fit(
        source,
        (1240, 1550),
        (
            zoom_width,
            zoom_height,
        ),
        method=Image.Resampling.LANCZOS,
        centering=(0.64, 0.40),
        centering=(
            0.68,
            0.43,
        ),
    )

    left = (
        zoom_width
        - WIDTH
        - 35
    )

    left = (1240 - WIDTH) // 2
    top = (1550 - HEIGHT) // 2
    top = 90

    return enlarged.crop(
        (
@@ -250,99 +359,79 @@ def _crop_slide_image(source, index):


# =========================================================
# BACKGROUND
# DEPTH EFFECTS
# =========================================================

def _fallback_background():
    image = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        BG + (255,),
    )

    glow = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(glow)

    draw.ellipse(
        (650, -100, 1250, 500),
        fill=GQ_BLUE + (45,),
    )

    glow = glow.filter(
        ImageFilter.GaussianBlur(150)
    )

    return Image.alpha_composite(
        image,
        glow,
    )

def _add_vignette(image):

def _prepare_background(featured_image, index):
    source = _load_featured_image(
        featured_image
    )

    cropped = _crop_slide_image(
        source,
        index,
    )

    if cropped is None:
        return _fallback_background()

    image = cropped.convert("RGBA")

    # Slight overall darkening.
    overlay = Image.new(
        "RGBA",
        image.size,
        (4, 7, 13, 45),
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

    return Image.alpha_composite(
        image,
        overlay,
    draw = ImageDraw.Draw(
        overlay
    )

    # Top gradient
    for i in range(380):

# =========================================================
# GRADIENTS
# =========================================================

def _bottom_gradient(
    image,
    start_y,
    max_alpha=235,
):
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )
        alpha = int(
            145
            * (
                1
                - i / 380
            )
        )

    draw = ImageDraw.Draw(overlay)
        draw.line(
            (
                0,
                i,
                WIDTH,
                i,
            ),
            fill=(
                BG[0],
                BG[1],
                BG[2],
                alpha,
            ),
        )

    distance = HEIGHT - start_y
    # Bottom gradient
    for i in range(620):

    for y in range(start_y, HEIGHT):
        progress = (
            (y - start_y)
            / max(1, distance)
        y = (
            HEIGHT
            - i
            - 1
        )

        alpha = int(
            max_alpha
            * progress
            215
            * (
                1
                - i / 620
            )
        )

        draw.line(
            (0, y, WIDTH, y),
            (
                0,
                y,
                WIDTH,
                y,
            ),
            fill=(
                BG[0],
                BG[1],
@@ -352,59 +441,84 @@ def _bottom_gradient(
        )

    return Image.alpha_composite(
        image,
        image.convert("RGBA"),
        overlay,
    )


def _top_gradient(
def _draw_glow(
    image,
    height=180,
    center,
    radius,
    color,
    opacity=70,
):
    overlay = Image.new(

    glow = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
        (
            0,
            0,
            0,
            0,
        ),
    )

    draw = ImageDraw.Draw(overlay)
    draw = ImageDraw.Draw(
        glow
    )

    for y in range(height):
        progress = 1 - (
            y / max(1, height)
        )
    x, y = center

        alpha = int(
            125 * progress
        )
    draw.ellipse(
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

        draw.line(
            (0, y, WIDTH, y),
            fill=(0, 0, 0, alpha),
    glow = glow.filter(
        ImageFilter.GaussianBlur(
            radius // 2
        )
    )

    return Image.alpha_composite(
        image,
        overlay,
        glow,
    )


# =========================================================
# SOFT PANEL
# =========================================================

def _soft_panel(
def _draw_shadow_panel(
    image,
    box,
    radius=32,
    opacity=185,
    radius=40,
    shadow_offset=18,
    shadow_blur=28,
    fill=(10, 14, 24, 220),
):

    x1, y1, x2, y2 = box

    # Shadow
    shadow = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
        (
            0,
            0,
            0,
            0,
        ),
    )

    shadow_draw = ImageDraw.Draw(
@@ -413,28 +527,41 @@ def _soft_panel(

    shadow_draw.rounded_rectangle(
        (
            x1 + 8,
            y1 + 12,
            x2 + 8,
            y2 + 12,
            x1 + shadow_offset,
            y1 + shadow_offset,
            x2 + shadow_offset,
            y2 + shadow_offset,
        ),
        radius=radius,
        fill=(0, 0, 0, 95),
        fill=(
            0,
            0,
            0,
            145,
        ),
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(20)
        ImageFilter.GaussianBlur(
            shadow_blur
        )
    )

    image = Image.alpha_composite(
        image,
        shadow,
    )

    # Panel
    panel = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
        (
            0,
            0,
            0,
            0,
        ),
    )

    panel_draw = ImageDraw.Draw(
@@ -444,19 +571,14 @@ def _soft_panel(
    panel_draw.rounded_rectangle(
        box,
        radius=radius,
        fill=(
            PANEL[0],
            PANEL[1],
            PANEL[2],
            opacity,
        ),
        fill=fill,
        outline=(
            255,
            255,
            255,
            16,
            20,
        ),
        width=1,
        width=2,
    )

    return Image.alpha_composite(
@@ -466,252 +588,439 @@ def _soft_panel(


# =========================================================
# SHARED UI
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

    if index == 1:

        image = _draw_glow(
            image,
            (
                850,
                300,
            ),
            300,
            GQ_BLUE,
            60,
        )

    elif index == 2:

        image = _draw_glow(
            image,
            (
                180,
                350,
            ),
            320,
            GQ_PURPLE,
            50,
        )

    else:

        image = _draw_glow(
            image,
            (
                800,
                900,
            ),
            330,
            GQ_BLUE,
            55,
        )

    return image


# =========================================================
# BACKGROUND PREPARATION
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

    # Very subtle GamerQuest lighting
    if index == 1:

        background = _draw_glow(
            background,
            (
                100,
                760,
            ),
            250,
            GQ_BLUE,
            45,
        )

    elif index == 2:

        background = _draw_glow(
            background,
            (
                900,
                850,
            ),
            260,
            GQ_PURPLE,
            35,
        )

    else:

        background = _draw_glow(
            background,
            (
                500,
                1080,
            ),
            280,
            GQ_BLUE,
            40,
        )

    return background


# =========================================================
# SLIDE NUMBER
# =========================================================

def _draw_slide_number(
    draw,
    index,
    total,
):
    text = f"{index:02d}/{total:02d}"

    font = _font(
        24,
        25,
        bold=True,
    )

    text = (
        f"{index:02d}/{total:02d}"
    )

    bbox = draw.textbbox(
        (0, 0),
        (
            0,
            0,
        ),
        text,
        font=font,
    )

    width = bbox[2] - bbox[0]
    width = (
        bbox[2]
        - bbox[0]
    )
