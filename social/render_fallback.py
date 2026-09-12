import json
import re
import shutil
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from social.render import clean_carousel_copy
from social.renderer import render_carousel
from social.sources import get_all_content


OUTPUT_FILE = Path("social-output.json")
OUTPUT_DIR = Path("social-rendered")

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

        if tag != "img":
            return

        alt = attrs.get("alt", "")
        candidates = [
            attrs.get("src", ""),
            attrs.get("data-src", ""),
            attrs.get("data-original", ""),
        ]

        for srcset_key in ("srcset", "data-srcset"):
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
        absolute = urljoin(self.base_url, value)
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
            "the",
            "and",
            "sur",
            "avec",
            "pour",
            "date",
            "sortie",
            "remake",
            "game",
            "news",
        }
    }


def _canonical_url(url):
    parsed = urlparse(str(url or "").strip())
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/").lower()


def _looks_like_content_image(url, alt, keywords):
    text = f"{url} {alt}".lower()
    if any(hint in text for hint in _BLOCKED_IMAGE_HINTS):
        return False

    path = urlparse(url).path.lower()
    if not path.endswith((".jpg", ".jpeg", ".png", ".webp", ".avif")):
        return False

    # Source-article images with matching game/topic terms rank highest, but
    # generic editorial image URLs are still allowed after junk assets are removed.
    return True


def _score_image(url, alt, keywords):
    haystack = f"{url} {alt}".lower()
    overlap = sum(1 for term in keywords if term in haystack)
    score = overlap * 10
    if alt.strip():
        score += 3
    if any(word in haystack for word in ("gameplay", "trailer", "edition", "console", "switch", "zelda")):
        score += 4
    return score


def resolve_featured_images(source_id, content_items=None, page_fetcher=None):
    source_id = str(source_id or "").strip()
    if not source_id:
        raise RuntimeError("Fallback render has no selected source_id.")

    if content_items is None:
        content_items = get_all_content()

    selected_item = None
    for item in content_items:
        if isinstance(item, dict) and str(item.get("source_id", "")).strip() == source_id:
            selected_item = item
            break

    if selected_item is None:
        raise RuntimeError("Selected social source was not found in the content feed.")

    keywords = _terms(selected_item)
    candidates = []
    excluded_canonical = set()

    featured = selected_item.get("featured_image")
    if isinstance(featured, dict):
        featured_url = str(featured.get("url", "")).strip()
        source_image_url = str(featured.get("source_image_url", "")).strip()
        if featured_url:
            candidates.append((featured_url, "featured", 1000))
        # The GamerQuest featured image is derived from this source image, so
        # never count both as two distinct visuals.
        if source_image_url:
            excluded_canonical.add(_canonical_url(source_image_url))
    elif isinstance(featured, str) and featured.strip():
        candidates.append((featured.strip(), "featured", 1000))

    if not candidates:
        for key in ("image_url", "thumbnail", "cover_image"):
            value = str(selected_item.get(key, "")).strip()
            if value:
                candidates.append((value, key, 1000))
                break

    source = selected_item.get("source")
    source_url = ""
    if isinstance(source, dict):
        source_url = str(source.get("url", "")).strip()

    if source_url:
        fetcher = page_fetcher or _default_page_fetcher
        try:
            html = fetcher(source_url)
            parser = _ImageCollector(source_url)
            parser.feed(str(html or ""))
            for url, alt in parser.images:
                canonical = _canonical_url(url)
                if canonical in excluded_canonical:
                    continue
                if not _looks_like_content_image(url, alt, keywords):
                    continue
                candidates.append((url, alt, _score_image(url, alt, keywords)))
        except Exception as exc:
            print(f"WARNING: could not inspect source article images: {exc}")

    # Highest relevance first, preserving the GamerQuest featured image as slide 1.
    candidates.sort(key=lambda item: item[2], reverse=True)

    unique = []
    seen = set()
    for url, _label, _score in candidates:
        canonical = _canonical_url(url)
        if not canonical or canonical in seen or canonical in excluded_canonical:
            continue
        seen.add(canonical)
        unique.append(url)
        if len(unique) == 3:
            break

    if len(unique) != 3:
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
    featured_images = resolve_featured_images(source_id)

    # Never mix stale images from a previous failed render with this run.
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
