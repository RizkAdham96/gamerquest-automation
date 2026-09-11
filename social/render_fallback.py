import json
import shutil
from pathlib import Path

from social.render import clean_carousel_copy
from social.renderer import render_carousel


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


def main():
    carousel = load_ready_carousel()

    # Never mix stale images from a previous failed render with this run.
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("AI image generation unavailable; using free deterministic GamerQuest renderer.")
    print("No web-image lookup is used by this fallback.")

    rendered = render_carousel(
        carousel,
        OUTPUT_DIR,
    )

    rendered = [Path(path) for path in rendered]

    if len(rendered) != 3:
        raise RuntimeError(
            f"Fallback renderer produced {len(rendered)} slides; exactly 3 are required."
        )

    for path in rendered:
        if not path.exists() or path.suffix.lower() != ".png":
            raise RuntimeError(f"Invalid fallback render output: {path}")

    print("Fallback render success: 3 PNG slides created.")
    for path in rendered:
        print(f"- {path}")


if __name__ == "__main__":
    main()
