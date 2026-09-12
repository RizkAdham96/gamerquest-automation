import json
import shutil
from pathlib import Path

from social.render import clean_carousel_copy
from social.renderer import render_carousel
from social.sources import get_all_content


OUTPUT_FILE = Path("social-output.json")
OUTPUT_DIR = Path("social-rendered")


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


def resolve_featured_image(source_id, content_items=None):
    source_id = str(source_id or "").strip()
    if not source_id:
        raise RuntimeError("Fallback render has no selected source_id.")

    if content_items is None:
        content_items = get_all_content()

    for item in content_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("source_id", "")).strip() != source_id:
            continue

        featured = item.get("featured_image")
        if isinstance(featured, dict):
            # Prefer the GamerQuest-hosted article image because it is stable
            # and already tied to this exact article. If unavailable, use the
            # original source image URL recorded by the news pipeline.
            for key in ("url", "source_image_url"):
                value = str(featured.get(key, "")).strip()
                if value:
                    return value

        if isinstance(featured, str) and featured.strip():
            return featured.strip()

        for key in ("image_url", "thumbnail", "cover_image"):
            value = str(item.get(key, "")).strip()
            if value:
                return value

        break

    raise RuntimeError(
        "Selected social source has no relevant featured image; "
        "refusing gradient-only carousel."
    )


def main():
    carousel = load_ready_carousel()
    source_id = load_source_id()
    featured_image = resolve_featured_image(source_id)

    # Never mix stale images from a previous failed render with this run.
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("AI image generation unavailable; using free deterministic GamerQuest renderer.")
    print(f"Using exact article featured image for source_id: {source_id}")

    rendered = render_carousel(
        carousel,
        OUTPUT_DIR,
        featured_image=featured_image,
    )

    rendered = [Path(path) for path in rendered]

    if len(rendered) != 3:
        raise RuntimeError(
            f"Fallback renderer produced {len(rendered)} slides; exactly 3 are required."
        )

    for path in rendered:
        if not path.exists() or path.suffix.lower() != ".png":
            raise RuntimeError(f"Invalid fallback render output: {path}")

    print("Fallback render success: 3 PNG slides created with article imagery.")
    for path in rendered:
        print(f"- {path}")


if __name__ == "__main__":
    main()
