import json
from pathlib import Path

from social.renderer import render_carousel
from social.sources import get_all_content

DEFAULT_INPUT = Path("social-output.json")
DEFAULT_OUTPUT_DIR = Path("social-rendered")


def _norm(value):
    return str(value or "").strip().lower()


def _image_url(item):
    featured = item.get("featured_image") if isinstance(item, dict) else None
    if isinstance(featured, dict):
        return featured.get("url") or featured.get("source_image_url")
    if isinstance(featured, str):
        return featured
    return None


def find_featured_image_url(carousel, content=None):
    if not isinstance(carousel, dict):
        return None
    content = get_all_content() if content is None else content
    topic = _norm(carousel.get("topic"))
    hook = _norm(carousel.get("hook"))
    if not topic and not hook:
        return None

    best = None
    best_score = 0
    topic_tokens = [token for token in topic.replace("-", " ").split() if len(token) > 2]

    for item in content:
        if not isinstance(item, dict):
            continue
        image_url = _image_url(item)
        if not image_url:
            continue
        title = _norm(item.get("title"))
        slug = _norm(item.get("slug")).replace("-", " ")
        haystack = f"{title} {slug}"
        score = 0
        if topic and topic in haystack:
            score += 100
        if hook and hook in haystack:
            score += 30
        score += sum(8 for token in topic_tokens if token in haystack)
        if score > best_score:
            best_score = score
            best = image_url

    return best if best_score > 0 else None


def render_from_output(input_path=DEFAULT_INPUT, output_dir=DEFAULT_OUTPUT_DIR):
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        return {"status": "skipped", "reason": "missing_social_output"}

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "skipped", "reason": "invalid_social_output", "error": str(error)}

    if payload.get("status") != "ready" or payload.get("fact_checked") is not True:
        return {"status": "skipped", "reason": "not_ready_or_fact_checked"}

    carousel = payload.get("carousel")
    if not isinstance(carousel, dict):
        return {"status": "skipped", "reason": "missing_carousel"}

    featured_image = find_featured_image_url(carousel)
    paths = render_carousel(carousel, output_dir, featured_image=featured_image)

    manifest = {
        "status": "rendered",
        "slides": [path.name for path in paths],
        "featured_image": featured_image,
        "caption": carousel.get("caption", ""),
        "cta": carousel.get("cta", ""),
        "hashtags": carousel.get("hashtags", []),
        "website_url": carousel.get("website_url", "https://gamerquest.fr"),
    }

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main():
    result = render_from_output()
    print(f"Social renderer status: {result.get('status')}")
    if result.get("reason"):
        print(f"Reason: {result['reason']}")
    if result.get("status") == "rendered":
        print(f"Rendered slides: {len(result.get('slides', []))}")
        print(f"Featured image: {result.get('featured_image') or 'fallback'}")


if __name__ == "__main__":
    main()
