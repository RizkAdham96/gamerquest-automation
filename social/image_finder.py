from io import BytesIO
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import (
    urljoin,
    urlparse,
)
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


# =========================================================
# SOURCE URL EXTRACTION
# =========================================================

def get_source_urls(item):
    """
    Find source/article URLs from the matched GamerQuest item.

    Supports several possible field names because the
    GamerQuest news/deals schemas may differ.
    """

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
# IMAGE FIELDS ALREADY STORED IN GAMERQUEST
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
# HTML IMAGE PARSER
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

        # -------------------------------------------------
        # OG / TWITTER IMAGES
        # -------------------------------------------------

        if tag.lower() == "meta":

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
                "twitter:image",
                "twitter:image:src",
            ):
                if content:
                    self.meta_images.append(
                        content
                    )

        # -------------------------------------------------
        # NORMAL IMG
        # -------------------------------------------------

        if tag.lower() == "img":

            for key in (
                "src",
                "data-src",
                "data-lazy-src",
                "data-original",
            ):
                value = attrs.get(key)

                if value:
                    self.images.append(
                        value
                    )

            # srcset often contains higher-quality images
            srcset = (
                attrs.get("srcset")
                or attrs.get(
                    "data-srcset"
                )
            )

            if srcset:

                candidates = []

                for part in srcset.split(","):

                    part = part.strip()

                    if not part:
                        continue

                    pieces = part.split()

                    if pieces:
                        candidates.append(
                            pieces[0]
                        )

                # Usually the last srcset item is largest.
                for candidate in reversed(
                    candidates
                ):
                    self.images.append(
                        candidate
                    )


# =========================================================
# FETCH HTML
# =========================================================

def _fetch_html(url):
    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept":
                    "text/html,application/xhtml+xml",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=12,
        ) as response:

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                )
                or ""
            ).lower()

            if (
                "html"
                not in content_type
            ):
                return ""

            raw = response.read(
                4 * 1024 * 1024
            )

        return raw.decode(
            "utf-8",
            errors="ignore",
        )

    except Exception:
        return ""


# =========================================================
# FILTER OBVIOUSLY BAD IMAGE URLS
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
    )

    return any(
        word in lowered
        for word in bad_words
    )


# =========================================================
# DOWNLOAD IMAGE FOR VALIDATION
# =========================================================

def _download_image(url):

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept":
                    "image/avif,image/webp,image/png,image/jpeg,*/*",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=12,
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
        width / max(
            height,
            1,
        )
    )

    # Reject ultra-wide banners and portrait ads.
    if ratio < 0.65:
        return False

    if ratio > 2.7:
        return False

    return True


# =========================================================
# SIMPLE VISUAL HASH
# =========================================================

def _visual_hash(image):
    """
    Detect same image served through different CDN URLs.

    Example:
    image.jpg?w=1200
    image.jpg?w=800

    Both should count as one image.
    """

    if image is None:
        return None

    small = image.convert(
        "L"
    ).resize(
        (
            12,
            12,
        )
    )

    pixels = list(
        small.getdata()
    )

    average = sum(
        pixels
    ) / len(pixels)

    bits = "".join(
        "1"
        if value >= average
        else "0"
        for value in pixels
    )

    return bits


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
# SCORE IMAGE RELEVANCE
# =========================================================

def _image_score(
    url,
    topic_tokens,
):
    lowered = url.lower()

    score = 0

    for token in topic_tokens:

        if token in lowered:
            score += 8

    # Prefer common screenshot/image filenames.
    if any(
        marker in lowered
        for marker in (
            "screen",
            "screenshot",
            "gameplay",
            "media",
            "gallery",
            "hero",
            "news",
        )
    ):
        score += 4

    return score


# =========================================================
# EXTRACT IMAGE URLS FROM SOURCE PAGE
# =========================================================

def extract_page_images(
    page_url,
    topic="",
):
    html = _fetch_html(
        page_url
    )

    if not html:
        return []

    parser = ImageHTMLParser()

    try:
        parser.feed(
            html
        )
    except Exception:
        pass

    candidates = []

    # OG image first.
    raw_candidates = (
        parser.meta_images
        + parser.images
    )

    for value in raw_candidates:

        value = _clean(
            value
        )

        if not value:
            continue

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

    return sorted(
        candidates,
        key=lambda url: _image_score(
            url,
            topic_tokens,
        ),
        reverse=True,
    )


# =========================================================
# MAIN FUNCTION
# =========================================================

def find_images_for_article(
    item,
    topic="",
    limit=MAX_IMAGES,
):
    """
    Build a clean set of up to 3 images.

    Priority:

    1. Existing exact GamerQuest article image.
    2. Other images stored inside exact article.
    3. Images from the ORIGINAL source page of this article.

    NEVER:
    - images from unrelated GamerQuest articles
    - images from another game
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

    def try_add(url):

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

        # Detect duplicate or almost-identical image.
        for existing_hash in selected_hashes:

            if _hash_distance(
                image_hash,
                existing_hash,
            ) <= 10:

                return False

        selected_urls.append(
            url
        )

        selected_hashes.append(
            image_hash
        )

        return True

    # =====================================================
    # 1. EXISTING GAMERQUEST ARTICLE IMAGES
    # =====================================================

    for url in get_existing_images(
        item
    ):

        try_add(
            url
        )

        if len(
            selected_urls
        ) >= limit:

            return selected_urls[
                :limit
            ]

    # =====================================================
    # 2. ORIGINAL ARTICLE SOURCE
    # =====================================================

    source_urls = get_source_urls(
        item
    )

    title = _clean(
        item.get("title")
    )

    combined_topic = (
        f"{topic} {title}"
    )

    for source_url in source_urls:

        page_images = (
            extract_page_images(
                source_url,
                combined_topic,
            )
        )

        for image_url in page_images:

            try_add(
                image_url
            )

            if len(
                selected_urls
            ) >= limit:

                return selected_urls[
                    :limit
                ]

    return selected_urls[
        :limit
    ]
