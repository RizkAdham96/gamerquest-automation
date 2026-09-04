import json
from pathlib import Path

from social.prepare_publish import (
    prepare_carousel_for_publish,
)


OUTPUT_FILE = Path("social-output.json")
RENDERED_DIR = Path("social-rendered")
PUBLISHED_ROOT = Path("social-published")


def load_social_output():
    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "social-output.json does not exist."
        )

    with OUTPUT_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise RuntimeError(
            "social-output.json must contain "
            "a JSON object."
        )

    return payload


def get_source_id(payload):
    source_id = str(
        payload.get("source_id", "")
    ).strip()

    if source_id:
        return source_id

    selected = payload.get(
        "selected",
        {}
    )

    if isinstance(selected, dict):
        source_id = str(
            selected.get(
                "source_id",
                ""
            )
        ).strip()

    if not source_id:
        raise RuntimeError(
            "No source_id found in "
            "social-output.json."
        )

    return source_id


def main():
    payload = load_social_output()

    source_id = get_source_id(
        payload
    )

    result = prepare_carousel_for_publish(
        source_id=source_id,
        rendered_dir=RENDERED_DIR,
        published_root=PUBLISHED_ROOT,
    )

    print(
        "Carousel prepared for publishing."
    )

    print(
        f"Source ID: {result['source_id']}"
    )

    print(
        f"Folder: {result['folder_name']}"
    )

    print("Images:")

    for image_path in result[
        "image_paths"
    ]:
        print(
            f"- {image_path}"
        )

    print(
        f"Manifest: {result['manifest']}"
    )


if __name__ == "__main__":
    main()
