import json
import re
import shutil
import urllib.request
from io import BytesIO
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from PIL import Image, ImageOps

from social.render import clean_carousel_copy
from social.renderer import render_carousel
from social.sources import get_all_content


OUTPUT_FILE = Path("social-output.json")
OUTPUT_DIR = Path("social-rendered")

MIN_SOURCE_WIDTH = 900
MIN_SOURCE_HEIGHT = 500
MIN_SOURCE_PIXELS = 700_000
DUPLICATE_HASH_DISTANCE = 7

_BLOCKED_IMAGE_HINTS = (
    "logo",
    "icon",
    "avatar",
    "sprite",
    "emoji",
    "badge",
    "tracking",
    "pixel",
    "advert",
    "newsletter",
    "social-share",
)


def _upgrade_image_url(url):
    """Upgrade known CDN thumbnails to a production-size image URL."""
    text = str(url or "").strip()
    parsed = urlparse(text)
    host = parsed.netloc.lower()
    path = parsed.path

    if host == "images.nintendolife.com":
        path = re.sub(
            r"/\d{2,4}x\d{2,4}\.(?:jpe?g|png|webp|avif)$",
            "/large.jpg",
            path,
            flags=re.IGNORECASE,
        )
        return parsed._replace(path=path, query="", fragment="").geturl()

    # WordPress and many gaming CDNs expose the original asset by removing
    # generated thumbnail dimensions from the filename.
    path = re.sub(
        r"-\d{2,4}x\d{2,4}(?=\.(?:jpe?g|png|webp|avif)$)",
        "",
        path,
        flags=re.IGNORECASE,
    )

    # Drop common resize-only query arguments while preserving unrelated
    # signed/version parameters. This lets us validate the original artwork
    # instead of rejecting a small CDN rendition.
    resize_keys = {
        "w", "width", "h", "height", "resize", "crop", "fit",
    }
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in resize_keys
        ],
        doseq=True,
    )

    return parsed._replace(path=path, query=query, fragment="").geturl()


class _ImageCollector(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = {str(k).lower(): str(v or "") for k, v in attrs}
        tag = tag.lower()

        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key in {"og:image", "twitter:image", "twitter:image:src"}:
                self._add(attrs.get("content", ""), attrs.get("content", ""))
            return

        if tag == "source":
            for srcset_key in ("srcset", "data-srcset", "data-lazy-srcset"):
                srcset = attrs.get(srcset_key, "")
                if srcset:
                    for part in srcset.split(","):
                        self._add(part.strip().split(" ")[0], "")
            return

        if tag != "img":
            return

        alt = attrs.get("alt", "")
        candidates = [
            attrs.get("src", ""),
            attrs.get("data-src", ""),
            attrs.get("data-original", ""),
            attrs.get("data-original-src", ""),
            attrs.get("data-lazy-src", ""),
        ]

        for srcset_key in ("srcset", "data-srcset", "data-lazy-srcset"):
            srcset = attrs.get(srcset_key, "")
            if srcset:
                for part in srcset.split(","):
                    candidates.append(part.strip().split(" ")[0])

        for candidate in candidates:
            self._add(candidate, alt)

    def _add(self, value, alt):
        value = str(value or "").strip()
        if not value or value.startswith(("data:", "blob:")):
            return
        absolute = _upgrade_image_url(urljoin(self.base_url, value))
        if absolute.startswith(("http://", "https://")):
            self.images.append((absolute, str(alt or "")))


def load_ready_carousel(output_file=OUTPUT_FILE):
    if not output_file.exists():
        raise RuntimeError("social-output.json does not exist.")

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("social-output.json must contain a JSON object.")
    if payload.get("status") != "ready":
        raise RuntimeError("Social content is not ready for rendering.")
    if "fact_checked" in payload and payload.get("fact_checked") is not True:
        raise RuntimeError("Refusing fallback render: carousel was not fact-checked.")

    carousel = payload.get("carousel")
    if not isinstance(carousel, dict):
        raise RuntimeError("Missing carousel payload.")
    slides = carousel.get("slides")
    if not isinstance(slides, list) or len(slides) != 3:
        raise RuntimeError("Fallback renderer requires exactly three slides.")
    return clean_carousel_copy(carousel)


def load_source_id(output_file=OUTPUT_FILE):
    payload = json.loads(Path(output_file).read_text(encoding="utf-8"))
    source_id = str(payload.get("source_id", "")).strip()
    if not source_id:
        raise RuntimeError("Fallback render has no selected source_id.")
    return source_id


def _default_page_fetcher(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; GamerQuestFR/1.0; "
                "+https://gamerquestfr.com/)"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def _terms(item):
    text_parts = [str(item.get("title", ""))]
    tags = item.get("tags")
    if isinstance(tags, list):
        text_parts.extend(str(tag) for tag in tags)
    text = " ".join(text_parts).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text)
        if token not in {
            "the", "and", "sur", "avec", "pour", "date", "sortie",
            "remake", "game", "news",
        }
    }


def _canonical_url(url):
    parsed = urlparse(str(url or "").strip())
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/").lower()


def _visual_key(url):
    parsed = urlparse(str(url or "").strip())
    path = parsed.path.lower().rstrip("/")
    parts = path.split("/")
    if parts:
        basename = parts[-1]
        if re.fullmatch(
            r"(?:\d{2,4}x\d{2,4}|large|medium|small|original)\.(?:jpe?g|png|webp|avif)",
            basename,
        ):
            path = "/".join(parts[:-1])
    return f"{parsed.netloc.lower()}{path}"


def _resolution_area(url):
    match = re.search(
        r"/(\d{2,4})x(\d{2,4})\.(?:jpe?g|png|webp|avif)(?:$|\?)",
        str(url).lower(),
    )
    if not match:
        return 0
    width, height = int(match.group(1)), int(match.group(2))
    return width * height


def _looks_like_content_image(url, alt, keywords):
    text = f"{url} {alt}".lower()
    if any(hint in text for hint in _BLOCKED_IMAGE_HINTS):
        return False

    path = urlparse(url).path.lower()
    if not path.endswith((".jpg", ".jpeg", ".png", ".webp", ".avif")):
        return False

    # Source pages often contain high-resolution but unrelated sidebar,
    # promo, newsletter, or cross-article images. Require at least one
    # article-specific term in the URL or alt text before the image can
    # enter the ranking pool. This keeps hashed CDN URLs valid when their
    # alt text describes the actual game/topic.
    if keywords and not any(term in text for term in keywords):
        return False

    return True


def _score_image(url, alt, keywords):
    haystack = f"{url} {alt}".lower()
    overlap = sum(1 for term in keywords if term in haystack)
    score = overlap * 10
    if alt.strip():
        score += 3
    if any(
        word in haystack
        for word in ("gameplay", "trailer", "edition", "console", "switch", "zelda")
    ):
        score += 4

    area = _resolution_area(url)
    if area:
        score += min(area / 50000, 30)
        if area < 300000:
            score -= 20
    elif any(size_word in url.lower() for size_word in ("/large.", "/original.")):
        score += 20
    return score


def _default_image_fetcher(url):
    request = urllib.request.Request(
        str(url),
        headers={"User-Agent": "GamerQuest-Social/1.0"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def _visual_signature(image, hash_size=8):
    rgb = image.convert("RGB")
    sample = ImageOps.fit(
        rgb.convert("L"),
        (hash_size, hash_size),
        method=Image.Resampling.LANCZOS,
    )
    pixels = list(sample.getdata())
    average = sum(pixels) / len(pixels)
    bits = 0
    for value in pixels:
        bits = (bits << 1) | int(value >= average)

    color_sample = rgb.resize((1, 1), Image.Resampling.LANCZOS)
    average_color = color_sample.getpixel((0, 0))
    return bits, average_color


def _hamming_distance(left, right):
    return (int(left) ^ int(right)).bit_count()


def _color_distance(left, right):
    return sum(
        (int(a) - int(b)) ** 2
        for a, b in zip(left, right)
    ) ** 0.5


def validate_source_images(image_urls, image_fetcher=None):
    """Select three genuinely different, publication-quality source images."""
    if not isinstance(image_urls, (list, tuple)) or len(image_urls) < 3:
        raise RuntimeError("At least three source image candidates are required.")

    fetcher = image_fetcher or _default_image_fetcher
    validated = []
    signatures = []
    rejected = []

    for url in image_urls:
        try:
            raw = fetcher(url)
            with Image.open(BytesIO(raw)) as image:
                image.load()
                width, height = image.size
                pixels = width * height
                if (
                    width < MIN_SOURCE_WIDTH
                    or height < MIN_SOURCE_HEIGHT
                    or pixels < MIN_SOURCE_PIXELS
                ):
                    rejected.append(
                        f"too small {width}x{height} ({url})"
                    )
                    continue
                signature = _visual_signature(image)
        except Exception as exc:
            rejected.append(
                f"could not validate {url} ({exc})"
            )
            continue

        visual_hash, average_color = signature
        duplicated = any(
            _hamming_distance(visual_hash, previous_hash)
            <= DUPLICATE_HASH_DISTANCE
            and _color_distance(average_color, previous_color) <= 45
            for previous_hash, previous_color in signatures
        )
        if duplicated:
            rejected.append(
                f"visually duplicated artwork ({url})"
            )
            continue

        signatures.append(signature)
        validated.append(str(url))

        if len(validated) == 3:
            return validated

    detail = "; ".join(rejected[:6])
    raise RuntimeError(
        "Could not find three publication-quality distinct images. "
        f"{detail}"
    )


def resolve_publishable_images(
    source_id,
    content_items=None,
    page_fetcher=None,
    image_fetcher=None,
):
    images = resolve_featured_images(
        source_id,
        content_items=content_items,
        page_fetcher=page_fetcher,
        max_images=12,
        require_three=True,
    )
    return validate_source_images(
        images,
        image_fetcher=image_fetcher,
    )


def resolve_featured_images(
    source_id,
    content_items=None,
    page_fetcher=None,
    max_images=3,
    require_three=True,
):
    source_id = str(source_id or "").strip()
    if not source_id:
        raise RuntimeError("Fallback render has no selected source_id.")

    if content_items is None:
        content_items = get_all_content()

    selected_item = next(
        (
            item
            for item in content_items
            if isinstance(item, dict)
            and str(item.get("source_id", "")).strip() == source_id
        ),
        None,
    )
    if selected_item is None:
        raise RuntimeError("Selected social source was not found in the content feed.")

    keywords = _terms(selected_item)
    candidates = []
    excluded_visuals = set()

    featured = selected_item.get("featured_image")
    if isinstance(featured, dict):
        featured_url = str(featured.get("url", "")).strip()
        source_image_url = str(featured.get("source_image_url", "")).strip()
        if featured_url:
            candidates.append((featured_url, "featured", 1000.0))
        if source_image_url:
            excluded_visuals.add(_visual_key(_upgrade_image_url(source_image_url)))
    elif isinstance(featured, str) and featured.strip():
        candidates.append((featured.strip(), "featured", 1000.0))

    if not candidates:
        for key in ("image_url", "thumbnail", "cover_image"):
            value = str(selected_item.get(key, "")).strip()
            if value:
                candidates.append((_upgrade_image_url(value), key, 1000.0))
                break

    source = selected_item.get("source")
    source_urls = []

    if isinstance(source, dict):
        source_url = str(source.get("url", "")).strip()
        if source_url:
            source_urls.append(source_url)

    top_level_source_url = str(selected_item.get("source_url", "")).strip()
    if top_level_source_url:
        source_urls.append(top_level_source_url)

    official_source = selected_item.get("official_source")
    if isinstance(official_source, dict):
        official_url = str(official_source.get("url", "")).strip()
        if official_url:
            source_urls.append(official_url)
    elif isinstance(official_source, str) and official_source.strip():
        source_urls.append(official_source.strip())

    fetcher = page_fetcher or _default_page_fetcher
    for source_url in dict.fromkeys(source_urls):
        try:
            html = fetcher(source_url)
            parser = _ImageCollector(source_url)
            parser.feed(str(html or ""))
            for url, alt in parser.images:
                if _visual_key(url) in excluded_visuals:
                    continue
                if not _looks_like_content_image(url, alt, keywords):
                    continue
                candidates.append((url, alt, _score_image(url, alt, keywords)))
        except Exception as exc:
            print(
                "WARNING: could not inspect source article images "
                f"from {source_url}: {exc}"
            )

    best_by_visual = {}
    for candidate in candidates:
        url, _label, score = candidate
        key = _visual_key(url)
        if not key or key in excluded_visuals:
            continue
        current = best_by_visual.get(key)
        if current is None or score > current[2]:
            best_by_visual[key] = candidate

    ranked = sorted(best_by_visual.values(), key=lambda item: item[2], reverse=True)
    limit = max(3, int(max_images or 3))
    unique = [url for url, _label, _score in ranked[:limit]]

    if require_three and len(unique) < 3:
        raise RuntimeError(
            "Selected social source does not provide three unique relevant images; "
            "refusing to publish a repeated-image or gradient carousel."
        )

    return unique


def resolve_featured_image(source_id, content_items=None):
    """Backward-compatible helper for callers/tests that only need slide 1."""
    images = resolve_featured_images(source_id, content_items=content_items)
    return images[0]


def main():
    carousel = load_ready_carousel()
    source_id = load_source_id()
    featured_images = resolve_publishable_images(source_id)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("AI image generation unavailable; using free deterministic GamerQuest renderer.")
    print(f"Using 3 distinct source visuals for source_id: {source_id}")
    for index, image_url in enumerate(featured_images, start=1):
        print(f"Slide {index} source image: {image_url}")

    rendered = render_carousel(
        carousel,
        OUTPUT_DIR,
        featured_images=featured_images,
    )
    rendered = [Path(path) for path in rendered]

    if len(rendered) != 3:
        raise RuntimeError(
            f"Fallback renderer produced {len(rendered)} slides; exactly 3 are required."
        )
    for path in rendered:
        if not path.exists() or path.suffix.lower() != ".png":
            raise RuntimeError(f"Invalid fallback render output: {path}")

    print("Fallback render success: 3 PNG slides created with 3 distinct visuals.")
    for path in rendered:
        print(f"- {path}")


if __name__ == "__main__":
    main()
