from io import BytesIO
from html.parser import HTMLParser
from urllib.parse import urljoin
import html as html_lib
import json
import re
import urllib.request

from PIL import Image


MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024

USER_AGENT = "GamerQuest-Social/1.0"

MIN_WIDTH = 700
MIN_HEIGHT = 400

MAX_IMAGES = 3


# =========================================================
# BASIC HELPERS
# =========================================================

def _clean(value):
    if value is None:
        return ""

    return str(value).strip()


def _tokens(value):
    return {
        token.lower()
        for token in re.findall(
            r"[a-zA-ZÀ-ÿ0-9]+",
            _clean(value),
        )
        if len(token) >= 4
    }


def _unique(values):
    output = []

    for value in values:
        if not value:
            continue

        if value not in output:
            output.append(value)

    return output


# =========================================================
# SOURCE URL EXTRACTION
# =========================================================

def get_source_urls(item):

    if not isinstance(item, dict):
        return []

    urls = []

    fields = (
        "source_url",
        "source",
        "article_url",
        "original_url",
        "external_url",
        "url",
        "link",
        "sources",
        "source_urls",
    )

    def append(value):

        if not value:
            return

        if isinstance(value, str):

            value = value.strip()

            if value.startswith(
                (
                    "http://",
                    "https://",
                )
            ):
                if value not in urls:
                    urls.append(value)

            return

        if isinstance(value, list):

            for child in value:
                append(child)

            return

        if isinstance(value, dict):

            for key in (
                "url",
                "link",
                "source_url",
                "href",
            ):
                append(
                    value.get(key)
                )

    for field in fields:
        append(
            item.get(field)
        )

    return urls


# =========================================================
# EXISTING GAMERQUEST IMAGES
# =========================================================

def get_existing_images(item):

    if not isinstance(item, dict):
        return []

    images = []

    fields = (
        "featured_image_url",
        "featured_image",
        "image_url",
        "image",
        "thumbnail_url",
        "thumbnail",
        "cover_image",
        "cover",
        "images",
        "gallery",
        "media",
        "screenshots",
        "article_images",
        "content_images",
        "image_urls",
    )

    def append(value):

        if not value:
            return

        if isinstance(value, str):

            value = value.strip()

            if (
                value.startswith(
                    (
                        "http://",
                        "https://",
                    )
                )
                or value.lower().endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                    )
                )
            ):

                if value not in images:
                    images.append(value)

            return

        if isinstance(value, list):

            for child in value:
                append(child)

            return

        if isinstance(value, dict):

            for key in (
                "url",
                "src",
                "source_url",
                "image_url",
                "featured_image_url",
                "original",
                "large",
                "medium",
            ):
                append(
                    value.get(key)
                )

    for field in fields:

        append(
            item.get(field)
        )

    return images


# =========================================================
# HTML PARSER
# =========================================================

class ImageHTMLParser(HTMLParser):

    def __init__(self):

        super().__init__()

        self.images = []
        self.meta_images = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):

        attrs = dict(attrs)

        tag = tag.lower()

        # =================================================
        # OPEN GRAPH / TWITTER
        # =================================================

        if tag == "meta":

            property_name = (
                attrs.get("property")
                or attrs.get("name")
                or ""
            ).lower()

            content = attrs.get(
                "content"
            )

            if property_name in (
                "og:image",
                "og:image:url",
                "og:image:secure_url",
                "twitter:image",
                "twitter:image:src",
            ):

                if content:
                    self.meta_images.append(
                        content
                    )

        # =================================================
        # IMG
        # =================================================

        if tag == "img":

            for key in (
                "src",
                "data-src",
                "data-lazy-src",
                "data-original",
                "data-image",
            ):

                value = attrs.get(key)

                if value:
                    self.images.append(
                        value
                    )

            srcset = (
                attrs.get("srcset")
                or attrs.get(
                    "data-srcset"
                )
            )

            if srcset:

                for part in srcset.split(","):

                    pieces = (
                        part.strip()
                        .split()
                    )

                    if pieces:

                        self.images.append(
                            pieces[0]
                        )

        # =================================================
        # PICTURE <source>
        # =================================================

        if tag == "source":

            srcset = (
                attrs.get("srcset")
                or attrs.get(
                    "data-srcset"
                )
            )

            if srcset:

                for part in srcset.split(","):

                    pieces = (
                        part.strip()
                        .split()
                    )

                    if pieces:

                        self.images.append(
                            pieces[0]
                        )


# =========================================================
# FETCH HTML
# =========================================================

def _fetch_html(url):

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    USER_AGENT,

                "Accept":
                    "text/html,"
                    "application/xhtml+xml,"
                    "application/json",

                "Accept-Language":
                    "en-US,en;q=0.9",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=15,
        ) as response:

            raw = response.read(
                8 * 1024 * 1024
            )

        return raw.decode(
            "utf-8",
            errors="ignore",
        )

    except Exception as error:

        print(
            "Image finder: "
            f"could not fetch source page: "
            f"{error}"
        )

        return ""


# =========================================================
# BAD IMAGE FILTER
# =========================================================

def _bad_image_url(url):

    lowered = url.lower()

    bad_words = (
        "logo",
        "favicon",
        "avatar",
        "emoji",
        "icon",
        "sprite",
        "profile",
        "author",
        "advert",
        "advertisement",
        "tracking",
        "pixel",
        "badge",
        "button",
        "placeholder",
        "newsletter",
        "social-icon",
        "facebook",
        "twitter",
        "instagram",
        "youtube",
        "rating",
        "esrb",
        "pegi",
        "payment",
        "store-logo",
        "epic-logo",
    )

    return any(
        word in lowered
        for word in bad_words
    )


# =========================================================
# SCRIPT / JSON IMAGE EXTRACTION
# =========================================================

def _extract_script_image_urls(
    raw_html,
    page_url,
):

    """
    Modern stores such as Epic often store gallery
    images inside JSON / JavaScript instead of <img> tags.

    This extracts those URLs as well.
    """

    if not raw_html:
        return []

    text = html_lib.unescape(
        raw_html
    )

    # JSON often escapes /
    text = text.replace(
        "\\/",
        "/",
    )

    # Also decode escaped unicode ampersands.
    text = text.replace(
        "\\u0026",
        "&",
    )

    candidates = []

    # =====================================================
    # 1. STANDARD ABSOLUTE URLs
    # =====================================================

    absolute_pattern = re.compile(
        r'https?://'
        r'[^"\'<>\s\\]+',
        re.IGNORECASE,
    )

    for match in absolute_pattern.findall(
        text
    ):

        url = match.rstrip(
            ".,);]}\"'"
        )

        lowered = url.lower()

        # Known image extensions OR CDN/image asset patterns.
        looks_like_image = (
            any(
                extension in lowered
                for extension in (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".avif",
                )
            )
            or any(
                marker in lowered
                for marker in (
                    "image",
                    "images",
                    "screenshot",
                    "screenshots",
                    "gallery",
                    "media",
                    "cdn",
                    "asset",
                    "assets",
                    "offer",
                    "landscape",
                    "portrait",
                    "carousel",
                )
            )
        )

        if not looks_like_image:
            continue

        if _bad_image_url(url):
            continue

        candidates.append(
            url
        )

    # =====================================================
    # 2. JSON IMAGE VALUES
    # =====================================================

    json_patterns = (
        r'"url"\s*:\s*"([^"]+)"',
        r'"image"\s*:\s*"([^"]+)"',
        r'"imageUrl"\s*:\s*"([^"]+)"',
        r'"image_url"\s*:\s*"([^"]+)"',
        r'"src"\s*:\s*"([^"]+)"',
        r'"original"\s*:\s*"([^"]+)"',
        r'"landscape"\s*:\s*"([^"]+)"',
        r'"portrait"\s*:\s*"([^"]+)"',
    )

    for pattern in json_patterns:

        for value in re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            value = (
                value
                .replace("\\/", "/")
                .replace("\\u0026", "&")
            )

            url = urljoin(
                page_url,
                value,
            )

            lowered = url.lower()

            if _bad_image_url(
                url
            ):
                continue

            if (
                any(
                    extension in lowered
                    for extension in (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".avif",
                    )
                )
                or any(
                    marker in lowered
                    for marker in (
                        "cdn",
                        "asset",
                        "image",
                        "media",
                        "screenshot",
                    )
                )
            ):
                candidates.append(
                    url
                )

    return _unique(
        candidates
    )


# =========================================================
# DOWNLOAD IMAGE
# =========================================================

def _download_image(url):

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    USER_AGENT,

                "Accept":
                    "image/avif,"
                    "image/webp,"
                    "image/png,"
                    "image/jpeg,"
                    "*/*",

                "Referer":
                    "https://store.epicgames.com/",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=15,
        ) as response:

            raw = response.read(
                MAX_DOWNLOAD_BYTES
            )

        with Image.open(
            BytesIO(raw)
        ) as image:

            return image.convert(
                "RGB"
            ).copy()

    except Exception:

        return None


# =========================================================
# IMAGE VALIDATION
# =========================================================

def _valid_image(image):

    if image is None:
        return False

    width, height = image.size

    if width < MIN_WIDTH:
        return False

    if height < MIN_HEIGHT:
        return False

    ratio = (
        width
        / max(
            height,
            1,
        )
    )

    # Reject extreme banners / vertical ads.
    if ratio < 0.60:
        return False

    if ratio > 3.0:
        return False

    return True


# =========================================================
# VISUAL DUPLICATE HASH
# =========================================================

def _visual_hash(image):

    if image is None:
        return None

    small = (
        image
        .convert("L")
        .resize(
            (
                16,
                16,
            )
        )
    )

    pixels = list(
        small.getdata()
    )

    average = (
        sum(pixels)
        / len(pixels)
    )

    return "".join(
        "1"
        if value >= average
        else "0"
        for value in pixels
    )


def _hash_distance(
    first,
    second,
):

    if (
        not first
        or not second
    ):
        return 999

    return sum(
        a != b
        for a, b in zip(
            first,
            second,
        )
    )


# =========================================================
# IMAGE SCORE
# =========================================================

def _image_score(
    url,
    topic_tokens,
):

    lowered = url.lower()

    score = 0

    # =====================================================
    # TOPIC RELEVANCE
    # =====================================================

    for token in topic_tokens:

        if token in lowered:
            score += 10

    # =====================================================
    # STRONG GAMING IMAGE MARKERS
    # =====================================================

    strong_markers = (
        "screenshot",
        "screenshots",
        "gallery",
        "gameplay",
        "carousel",
    )

    for marker in strong_markers:

        if marker in lowered:
            score += 12

    # =====================================================
    # GENERAL ASSET MARKERS
    # =====================================================

    asset_markers = (
        "media",
        "asset",
        "assets",
        "cdn",
        "offer",
        "landscape",
        "hero",
    )

    for marker in asset_markers:

        if marker in lowered:
            score += 4

    # Epic game asset CDN preference.
    if "epicgames" in lowered:
        score += 5

    if "spt-assets" in lowered:
        score += 10

    return score


# =========================================================
# EXTRACT SOURCE PAGE IMAGES
# =========================================================

def extract_page_images(
    page_url,
    topic="",
):

    raw_html = _fetch_html(
        page_url
    )

    if not raw_html:
        return []

    parser = ImageHTMLParser()

    try:
        parser.feed(
            raw_html
        )

    except Exception:
        pass

    raw_candidates = []

    # =====================================================
    # STANDARD HTML
    # =====================================================

    raw_candidates.extend(
        parser.meta_images
    )

    raw_candidates.extend(
        parser.images
    )

    # =====================================================
    # JAVASCRIPT / JSON
    #
    # This is the important new part for Epic.
    # =====================================================

    script_images = (
        _extract_script_image_urls(
            raw_html,
            page_url,
        )
    )

    raw_candidates.extend(
        script_images
    )

    candidates = []

    for value in raw_candidates:

        value = _clean(
            value
        )

        if not value:
            continue

        value = (
            value
            .replace("\\/", "/")
            .replace("\\u0026", "&")
        )

        url = urljoin(
            page_url,
            value,
        )

        if not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            continue

        if _bad_image_url(
            url
        ):
            continue

        if url not in candidates:
            candidates.append(
                url
            )

    topic_tokens = _tokens(
        topic
    )

    candidates.sort(
        key=lambda url: _image_score(
            url,
            topic_tokens,
        ),
        reverse=True,
    )

    print(
        "Image finder: "
        f"{len(candidates)} "
        "raw source image candidate(s) found."
    )

    return candidates


# =========================================================
# MAIN FUNCTION
# =========================================================

def find_images_for_article(
    item,
    topic="",
    limit=MAX_IMAGES,
):

    """
    Return up to 3 REAL images connected to the
    exact selected GamerQuest story.

    Priority:

    1. GamerQuest's existing featured image.
    2. Other images already stored with that story.
    3. Gallery/screenshots from the ORIGINAL source page.

    Never search other GamerQuest articles.
    """

    if not isinstance(
        item,
        dict,
    ):
        return []

    selected_urls = []
    selected_hashes = []

    # =====================================================
    # ADD + VALIDATE
    # =====================================================

    def try_add(
        url,
        label="image",
    ):

        if not url:
            return False

        if url in selected_urls:
            return False

        if _bad_image_url(
            url
        ):
            return False

        image = _download_image(
            url
        )

        if not _valid_image(
            image
        ):
            return False

        image_hash = _visual_hash(
            image
        )

        # Reject duplicate or nearly identical versions.
        for existing_hash in (
            selected_hashes
        ):

            if _hash_distance(
                image_hash,
                existing_hash,
            ) <= 18:

                return False

        selected_urls.append(
            url
        )

        selected_hashes.append(
            image_hash
        )

        print(
            "Image finder accepted "
            f"{label} "
            f"#{len(selected_urls)}: "
            f"{url}"
        )

        return True

    # =====================================================
    # 1. EXISTING EXACT GAMERQUEST IMAGE
    # =====================================================

    existing_images = (
        get_existing_images(
            item
        )
    )

    for url in existing_images:

        try_add(
            url,
            "GamerQuest image",
        )

        if len(selected_urls) >= limit:

            return selected_urls[
                :limit
            ]

    # =====================================================
    # 2. ORIGINAL SOURCE PAGE
    # =====================================================

    source_urls = (
        get_source_urls(
            item
        )
    )

    title = _clean(
        item.get("title")
    )

    deal = item.get(
        "deal",
        {}
    )

    game_name = ""

    if isinstance(
        deal,
        dict,
    ):
        game_name = _clean(
            deal.get("game")
        )

    combined_topic = " ".join(
        part
        for part in (
            topic,
            game_name,
            title,
        )
        if part
    )

    print(
        "Image finder topic: "
        f"{combined_topic}"
    )

    print(
        "Image finder source URL(s): "
        f"{len(source_urls)}"
    )

    for source_url in source_urls:

        print(
            "Image finder scanning source: "
            f"{source_url}"
        )

        page_images = (
            extract_page_images(
                source_url,
                combined_topic,
            )
        )

        for image_url in page_images:

            try_add(
                image_url,
                "source image",
            )

            if len(
                selected_urls
            ) >= limit:

                return selected_urls[
                    :limit
                ]

    print(
        "Image finder final result: "
        f"{len(selected_urls)} "
        "unique usable image(s)."
    )

    return selected_urls[
        :limit
    ]
