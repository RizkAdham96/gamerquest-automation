from io import BytesIO
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import html as html_lib
import re
import urllib.request

from PIL import Image


MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
USER_AGENT = "GamerQuest-Social/1.0"

MIN_WIDTH = 700
MIN_HEIGHT = 400

MAX_IMAGES = 3

# Minimum contextual relevance required for additional
# images pulled from the original source page.
MIN_CONTEXT_SCORE = 2

CONTEXT_RADIUS = 1800


# =========================================================
# STOP WORDS
# =========================================================

STOP_WORDS = {
    "avec",
    "dans",
    "pour",
    "sans",
    "plus",
    "moins",
    "sera",
    "sont",
    "tout",
    "tous",
    "toute",
    "toutes",
    "cette",
    "comme",
    "mais",
    "aussi",
    "nouveau",
    "nouvelle",
    "nouveaux",
    "prochain",
    "prochaine",
    "arrive",
    "arrivee",
    "sortie",
    "sortira",
    "annonce",
    "annoncee",
    "officiel",
    "officielle",
    "gaming",
    "game",
    "games",
    "news",
    "jeu",
    "jeux",
    "gratuit",
    "gratuite",
    "gratuitement",
    "epic",
    "store",
    "gamerquest",
    "disponible",
    "actuellement",
    "pendant",
    "duree",
    "limitee",
    "the",
    "and",
    "with",
    "from",
    "this",
    "that",
    "your",
    "gameplay",
    "official",
}


# =========================================================
# BASIC HELPERS
# =========================================================

def _clean(value):
    if value is None:
        return ""

    return str(value).strip()


def _tokens(value):
    tokens = set()

    for token in re.findall(
        r"[a-zA-ZÀ-ÿ0-9]+",
        _clean(value).lower(),
    ):
        if len(token) < 4:
            continue

        if token in STOP_WORDS:
            continue

        tokens.add(token)

    return tokens


def _unique(values):
    output = []

    for value in values:
        if not value:
            continue

        if value not in output:
            output.append(value)

    return output


def _normalize_url(value, base_url=""):
    value = _clean(value)

    if not value:
        return ""

    value = html_lib.unescape(value)

    value = (
        value
        .replace("\\/", "/")
        .replace("\\u0026", "&")
        .replace("\\u003d", "=")
        .replace("\\u003f", "?")
    )

    if base_url:
        value = urljoin(
            base_url,
            value,
        )

    return value


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
            value = _clean(value)

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
            value = _clean(value)

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

        # -------------------------------------------------
        # META
        # -------------------------------------------------

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

        # -------------------------------------------------
        # IMG
        # -------------------------------------------------

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

        # -------------------------------------------------
        # PICTURE SOURCE
        # -------------------------------------------------

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
# HTTP
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
            "could not fetch source page: "
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
# SCRIPT / JSON CANDIDATES
# =========================================================

def _extract_script_candidates(
    raw_html,
    page_url,
):
    """
    Extract image URLs from JavaScript / JSON.

    Important:
    Each URL keeps the nearby text around it.
    That nearby text is later used to determine whether
    the image belongs to the selected game/story.
    """

    if not raw_html:
        return []

    text = html_lib.unescape(
        raw_html
    )

    text = (
        text
        .replace("\\/", "/")
        .replace("\\u0026", "&")
    )

    output = []

    pattern = re.compile(
        r'https?://'
        r'[^"\'<>\s\\]+',
        re.IGNORECASE,
    )

    for match in pattern.finditer(
        text
    ):
        raw_url = match.group(0)

        url = raw_url.rstrip(
            ".,);]}\"'"
        )

        lowered = url.lower()

        looks_like_image = (
            any(
                ext in lowered
                for ext in (
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
                    "landscape",
                    "carousel",
                )
            )
        )

        if not looks_like_image:
            continue

        if _bad_image_url(
            url
        ):
            continue

        start = max(
            0,
            match.start()
            - CONTEXT_RADIUS,
        )

        end = min(
            len(text),
            match.end()
            + CONTEXT_RADIUS,
        )

        context = text[
            start:end
        ]

        output.append(
            {
                "url":
                    _normalize_url(
                        url,
                        page_url,
                    ),
                "context":
                    context,
                "origin":
                    "script",
            }
        )

    return output


# =========================================================
# IMAGE CONTEXT RELEVANCE
# =========================================================

def _context_score(
    candidate,
    topic_tokens,
):
    """
    Count meaningful game/topic tokens found near
    the image inside the source page.

    Example:
    LEGO Skylines gallery image:
      context contains lego / skylines -> accepted

    Recommendation for another game:
      no LEGO/Skylines context -> rejected
    """

    if not topic_tokens:
        return 0

    url = (
        candidate.get(
            "url",
            ""
        )
        or ""
    ).lower()

    context = (
        candidate.get(
            "context",
            ""
        )
        or ""
    ).lower()

    score = 0

    for token in topic_tokens:
        if token in url:
            score += 3

        if token in context:
            score += 1

    return score


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
                    "https://www.google.com/",
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

    if ratio < 0.60:
        return False

    if ratio > 3.0:
        return False

    return True


# =========================================================
# VISUAL DUPLICATE DETECTION
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
# URL IMAGE SCORE
# =========================================================

def _image_score(
    url,
    topic_tokens,
):
    lowered = url.lower()

    score = 0

    for token in topic_tokens:
        if token in lowered:
            score += 10

    for marker in (
        "screenshot",
        "screenshots",
        "gallery",
        "gameplay",
        "carousel",
    ):
        if marker in lowered:
            score += 12

    for marker in (
        "media",
        "asset",
        "assets",
        "cdn",
        "landscape",
        "hero",
    ):
        if marker in lowered:
            score += 4

    return score


# =========================================================
# EXTRACT SOURCE PAGE CANDIDATES
# =========================================================

def extract_page_candidates(
    page_url,
    topic="",
):
    raw_html = _fetch_html(
        page_url
    )

    if not raw_html:
        return []

    topic_tokens = _tokens(
        topic
    )

    parser = ImageHTMLParser()

    try:
        parser.feed(
            raw_html
        )
    except Exception:
        pass

    candidates = []

    # -----------------------------------------------------
    # META IMAGES
    #
    # OG image is strongly connected with the page itself.
    # -----------------------------------------------------

    for value in parser.meta_images:
        url = _normalize_url(
            value,
            page_url,
        )

        if not url:
            continue

        if _bad_image_url(
            url
        ):
            continue

        candidates.append(
            {
                "url":
                    url,
                "context":
                    topic,
                "origin":
                    "meta",
                "context_score":
                    999,
            }
        )

    # -----------------------------------------------------
    # NORMAL HTML IMAGES
    #
    # HTML images are not automatically trusted because
    # recommendation widgets also use normal <img> tags.
    # -----------------------------------------------------

    raw_lower = raw_html.lower()

    for value in parser.images:
        url = _normalize_url(
            value,
            page_url,
        )

        if not url:
            continue

        if _bad_image_url(
            url
        ):
            continue

        search_value = (
            _clean(value)
            .lower()
        )

        position = (
            raw_lower.find(
                search_value
            )
            if search_value
            else -1
        )

        if position >= 0:
            start = max(
                0,
                position
                - CONTEXT_RADIUS,
            )

            end = min(
                len(raw_html),
                position
                + len(search_value)
                + CONTEXT_RADIUS,
            )

            context = raw_html[
                start:end
            ]

        else:
            context = ""

        candidate = {
            "url":
                url,
            "context":
                context,
            "origin":
                "html",
        }

        candidate[
            "context_score"
        ] = _context_score(
            candidate,
            topic_tokens,
        )

        candidates.append(
            candidate
        )

    # -----------------------------------------------------
    # SCRIPT / JSON IMAGES
    # -----------------------------------------------------

    for candidate in (
        _extract_script_candidates(
            raw_html,
            page_url,
        )
    ):
        candidate[
            "context_score"
        ] = _context_score(
            candidate,
            topic_tokens,
        )

        candidates.append(
            candidate
        )

    # -----------------------------------------------------
    # DEDUP URL
    # -----------------------------------------------------

    deduplicated = {}
    
    for candidate in candidates:
        url = candidate.get(
            "url"
        )

        if not url:
            continue

        previous = (
            deduplicated.get(
                url
            )
        )

        if previous is None:
            deduplicated[
                url
            ] = candidate

            continue

        # Keep whichever occurrence has stronger context.
        if candidate.get(
            "context_score",
            0,
        ) > previous.get(
            "context_score",
            0,
        ):
            deduplicated[
                url
            ] = candidate

    candidates = list(
        deduplicated.values()
    )

    # -----------------------------------------------------
    # SORT
    # -----------------------------------------------------

    candidates.sort(
        key=lambda item: (
            item.get(
                "context_score",
                0,
            ),
            _image_score(
                item.get(
                    "url",
                    "",
                ),
                topic_tokens,
            ),
        ),
        reverse=True,
    )

    print(
        "Image finder: "
        f"{len(candidates)} "
        "raw source candidate(s) found."
    )

    return candidates


def extract_page_images(
    page_url,
    topic="",
):
    """
    Kept for compatibility with any existing callers.
    """

    candidates = (
        extract_page_candidates(
            page_url,
            topic,
        )
    )

    return [
        candidate["url"]
        for candidate in candidates
        if candidate.get("url")
    ]


# =========================================================
# SAME MEDIA FAMILY
# =========================================================

def _media_family(url):
    """
    Builds a loose CDN/path family identifier.

    Gallery images from the same game often share the same
    hostname and asset folder. Recommendation images often
    come from a different folder.
    """

    try:
        parsed = urlparse(
            url
        )

        path_parts = [
            part
            for part
            in parsed.path.split("/")
            if part
        ]

        useful_parts = (
            path_parts[:3]
        )

        return (
            parsed.netloc.lower(),
            tuple(
                part.lower()
                for part
                in useful_parts
            ),
        )

    except Exception:
        return (
            "",
            (),
        )


# =========================================================
# MAIN
# =========================================================

def find_images_for_article(
    item,
    topic="",
    limit=MAX_IMAGES,
):
    """
    Return up to three relevant images for the exact story.

    Rules:

    1. Keep the GamerQuest featured image.
    2. Look only at the original source page.
    3. Reject recommendation/related-story artwork when
       its surrounding page context does not match the game.
    4. Reject duplicate images.
    5. Prefer multiple assets from the same relevant
       source gallery.
    """

    if not isinstance(
        item,
        dict,
    ):
        return []

    selected_urls = []
    selected_hashes = []

    accepted_source_families = []

    # =====================================================
    # ADD IMAGE
    # =====================================================

    def try_add(
        url,
        label="image",
        context_score=None,
        source_candidate=False,
    ):
        if not url:
            return False

        if url in selected_urls:
            return False

        if _bad_image_url(
            url
        ):
            return False

        # -------------------------------------------------
        # STRICT RELEVANCE FILTER
        # -------------------------------------------------

        if source_candidate:
            if (
                context_score is not None
                and context_score
                < MIN_CONTEXT_SCORE
            ):
                family = _media_family(
                    url
                )

                # Allow weak-context image ONLY when it comes
                # from the same gallery/media family as an
                # already accepted relevant source image.
                if (
                    family
                    not in
                    accepted_source_families
                ):
                    print(
                        "Image finder rejected "
                        "low-relevance source image: "
                        f"{url}"
                    )

                    return False

        image = _download_image(
            url
        )

        if not _valid_image(
            image
        ):
            return False

        image_hash = (
            _visual_hash(
                image
            )
        )

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

        if source_candidate:
            family = _media_family(
                url
            )

            if (
                family
                not in
                accepted_source_families
            ):
                accepted_source_families.append(
                    family
                )

        print(
            "Image finder accepted "
            f"{label} "
            f"#{len(selected_urls)}: "
            f"{url}"
        )

        if context_score is not None:
            print(
                "Image finder relevance score: "
                f"{context_score}"
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

        if len(
            selected_urls
        ) >= limit:
            return selected_urls[
                :limit
            ]

    # =====================================================
    # 2. BUILD PRECISE GAME TOPIC
    # =====================================================

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

    precise_topic = " ".join(
        part
        for part in (
            game_name,
            topic,
            title,
        )
        if part
    )

    topic_tokens = _tokens(
        precise_topic
    )

    print(
        "Image finder topic: "
        f"{precise_topic}"
    )

    print(
        "Image finder core tokens: "
        + ", ".join(
            sorted(
                topic_tokens
            )
        )
    )

    # =====================================================
    # 3. ORIGINAL SOURCE
    # =====================================================

    source_urls = (
        get_source_urls(
            item
        )
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

        candidates = (
            extract_page_candidates(
                source_url,
                precise_topic,
            )
        )

        # =================================================
        # PASS A
        #
        # Strongly relevant images only.
        # =================================================

        for candidate in candidates:
            score = candidate.get(
                "context_score",
                0,
            )

            if score < MIN_CONTEXT_SCORE:
                continue

            try_add(
                candidate.get(
                    "url"
                ),
                "relevant source image",
                context_score=score,
                source_candidate=True,
            )

            if len(
                selected_urls
            ) >= limit:
                return selected_urls[
                    :limit
                ]

        # =================================================
        # PASS B
        #
        # If fewer than 3, allow gallery siblings sharing
        # the same media family as an accepted source image.
        #
        # This lets us obtain screenshots whose individual
        # URL has no game title while still blocking random
        # recommendation images.
        # =================================================

        if accepted_source_families:
            for candidate in candidates:
                url = candidate.get(
                    "url"
                )

                family = _media_family(
                    url
                )

                if (
                    family
                    not in
                    accepted_source_families
                ):
                    continue

                try_add(
                    url,
                    "same-gallery source image",
                    context_score=
                        candidate.get(
                            "context_score",
                            0,
                        ),
                    source_candidate=True,
                )

                if len(
                    selected_urls
                ) >= limit:
                    return selected_urls[
                        :limit
                    ]

    # =====================================================
    # FINAL
    # =====================================================

    print(
        "Image finder final result: "
        f"{len(selected_urls)} "
        "unique relevant image(s)."
    )

    if len(selected_urls) == 1:
        print(
            "Image finder fallback: "
            "renderer will reuse the valid image "
            "instead of using an unrelated game."
        )

    elif len(selected_urls) == 2:
        print(
            "Image finder fallback: "
            "renderer will use the two relevant images "
            "and reuse one rather than accepting "
            "an unrelated third image."
        )

    return selected_urls[
        :limit
    ]
