import json
from pathlib import Path

from social.renderer import render_carousel

DEFAULT_INPUT = Path("social-output.json")
DEFAULT_OUTPUT_DIR = Path("social-rendered")


def render_from_output(
    input_path=DEFAULT_INPUT,
    output_dir=DEFAULT_OUTPUT_DIR,
):
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        return {
            "status": "skipped",
            "reason": "missing_social_output",
        }

    try:
        payload = json.loads(
            input_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        return {
            "status": "skipped",
            "reason": "invalid_social_output",
            "error": str(error),
        }

    if (
        payload.get("status") != "ready"
        or payload.get("fact_checked") is not True
    ):
        return {
            "status": "skipped",
            "reason": "not_ready_or_fact_checked",
        }

    carousel = payload.get("carousel")
    if not isinstance(carousel, dict):
        return {
            "status": "skipped",
            "reason": "missing_carousel",
        }

    paths = render_carousel(carousel, output_dir)

    manifest = {
        "status": "rendered",
        "slides": [path.name for path in paths],
        "caption": carousel.get("caption", ""),
        "cta": carousel.get("cta", ""),
        "hashtags": carousel.get("hashtags", []),
        "website_url": carousel.get(
            "website_url",
            "https://gamerquest.fr",
        ),
    }

    (output_dir / "manifest.json").write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return manifest


def main():
    result = render_from_output()
    print(
        f"Social renderer status: {result.get('status')}"
    )

    if result.get("reason"):
        print(f"Reason: {result['reason']}")

    if result.get("status") == "rendered":
        print(
            f"Rendered slides: {len(result.get('slides', []))}"
        )


if __name__ == "__main__":
    main()
